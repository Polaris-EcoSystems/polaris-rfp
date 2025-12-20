from __future__ import annotations

import json
import hmac
import hashlib
import time
from urllib.parse import parse_qs
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from ..observability.logging import get_logger
from ..settings import settings
from ..services.rfp_analyzer import analyze_rfp
from ..services.proposals_repo import list_proposals
from ..services.rfp_upload_jobs_repo import get_job
from ..services.rfps_repo import create_rfp_from_analysis, get_rfp_by_id, list_rfps
from ..services.slack_agent import run_slack_agent_question
from ..services.slack_operator_agent import run_slack_operator_for_mention
from ..services.slack_surfaces.dispatcher import handle_event_callback, handle_interactivity
from ..services.slack_surfaces.workflows import handle_workflow_step_execute
from ..services.slack_action_executor import execute_action
from ..services.slack_actions_repo import get_action, mark_action_done
from ..services.slack_actions_repo import create_action
from ..services.slack_rate_limiter import allow as slack_allow
from ..services.slack_response_url import respond as respond_via_response_url
from ..services.slack_secrets import get_secret_str
from ..services.slack_actor_context import resolve_actor_context
from ..services.slack_web import (
    download_slack_file,
    get_bot_token,
    is_slack_configured,
    list_recent_channel_pdfs,
    post_message_result,
    chat_post_message_result,
    slack_api_get,
)
from ..services.slack_pending_thread_links_repo import create_pending_link, get_pending_link, consume_pending_link
from ..services.slack_thread_bindings_repo import set_binding
from ..services.agent_events_repo import append_event


router = APIRouter(tags=["integrations"])
log = get_logger("integrations_slack")

def _extract_action_error(result: dict[str, Any]) -> str:
    """
    Normalize action execution errors into a single string.

    `execute_action` often returns:
      {"ok": bool, "action": str, "result": {"ok": bool, "error": "..."}}
    while other call sites might return:
      {"ok": bool, "error": "..."}
    """
    try:
        e1 = str(result.get("error") or "").strip()
        if e1:
            return e1
        inner = result.get("result")
        if isinstance(inner, dict):
            e2 = str(inner.get("error") or "").strip()
            if e2:
                return e2
        return "unknown_error"
    except Exception:
        return "unknown_error"

def _command_response_type(subcommand: str) -> str:
    # Per request: make all commands public except `job` which can contain
    # operational details and is typically user-specific.
    sub = str(subcommand or "").strip().lower()
    if sub in ("job", "upload", "ingest", "channel", "chan", "whereami", "link-thread", "linkthread", "where"):
        return "ephemeral"
    return "in_channel"


def _rfp_url(rfp_id: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    rid = str(rfp_id or "").strip()
    return f"{base}/rfps/{rid}"


def _proposal_url(proposal_id: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    pid = str(proposal_id or "").strip()
    return f"{base}/proposals/{pid}"


def _pipeline_url() -> str:
    return str(settings.frontend_base_url or "").rstrip("/") + "/pipeline"


def _rfps_url() -> str:
    return str(settings.frontend_base_url or "").rstrip("/") + "/rfps"


def _proposals_url() -> str:
    return str(settings.frontend_base_url or "").rstrip("/") + "/proposals"


def _content_url() -> str:
    return str(settings.frontend_base_url or "").rstrip("/") + "/content"


def _templates_url() -> str:
    return str(settings.frontend_base_url or "").rstrip("/") + "/templates"

def _profile_url() -> str:
    return str(settings.frontend_base_url or "").rstrip("/") + "/profile"


def _upload_url() -> str:
    return str(settings.frontend_base_url or "").rstrip("/") + "/rfps/upload"


def _slack_upload_latest_pdfs_task(*, response_url: str, channel_id: str, n: int) -> None:
    """
    Background task: fetch latest PDFs from Slack channel and create RFPs.
    """
    try:
        want = max(1, min(5, int(n or 1)))
        ch = str(channel_id or "").strip()
        if not ch:
            respond_via_response_url(
                response_url=response_url,
                text="Upload failed: missing channel context.",
                response_type="ephemeral",
            )
            return

        files = list_recent_channel_pdfs(channel_id=ch, max_files=want, max_messages=80)
        if not files:
            respond_via_response_url(
                response_url=response_url,
                text=(
                    "No PDFs found in recent channel history.\n"
                    "Upload one or more PDFs into this channel, then run:\n"
                    "`/polaris upload` (or `/polaris upload 3`)"
                ),
                response_type="ephemeral",
            )
            return

        lines: list[str] = []
        ok = 0
        for f in files:
            name = str(f.get("name") or "upload.pdf").strip() or "upload.pdf"
            size = int(f.get("size") or 0)
            url = (
                str(f.get("url_private_download") or "").strip()
                or str(f.get("url_private") or "").strip()
            )
            if size and size > 60 * 1024 * 1024:
                lines.append(f"- `{name}`: skipped (file too large: {size} bytes)")
                continue
            if not url:
                lines.append(f"- `{name}`: skipped (missing download URL)")
                continue

            try:
                pdf = download_slack_file(url=url, max_bytes=60 * 1024 * 1024)
                analysis = analyze_rfp(pdf, name)
                saved = create_rfp_from_analysis(
                    analysis=analysis,
                    source_file_name=name,
                    source_file_size=len(pdf),
                )
                rid = str(saved.get("_id") or saved.get("rfpId") or "").strip()
                if rid:
                    ok += 1
                    lines.append(f"- Created: <{_rfp_url(rid)}|{name}> `{rid}`")
                else:
                    lines.append(f"- `{name}`: created, but missing rfpId in response")
            except Exception as e:
                msg = str(e) or "upload_failed"
                if len(msg) > 180:
                    msg = msg[:180] + "…"
                lines.append(f"- `{name}`: failed ({msg})")

        header = f"*Uploaded {ok}/{len(files)} PDF(s) to Polaris*"
        respond_via_response_url(
            response_url=response_url,
            text="\n".join([header] + lines),
            response_type="ephemeral",
        )
    except Exception:
        # Never fail silently; but keep response terse.
        try:
            respond_via_response_url(
                response_url=response_url,
                text="Upload failed (server error).",
                response_type="ephemeral",
            )
        except Exception:
            pass


def _format_rfp_line(rfp: dict) -> str:
    rid = str(rfp.get("_id") or rfp.get("rfpId") or "").strip()
    title = str(rfp.get("title") or "RFP").strip() or "RFP"
    client = str(rfp.get("clientName") or "").strip()
    ptype = str(rfp.get("projectType") or "").strip()
    deadline = str(rfp.get("submissionDeadline") or "").strip()

    meta_parts: list[str] = []
    if client:
        meta_parts.append(client)
    if ptype:
        meta_parts.append(ptype)
    if deadline:
        meta_parts.append(f"due {deadline}")
    meta = f" — {' · '.join(meta_parts)}" if meta_parts else ""

    if rid:
        return f"- <{_rfp_url(rid)}|{title}> `{rid}`{meta}"
    return f"- {title}{meta}"


def _format_proposal_line(p: dict) -> str:
    pid = str(p.get("_id") or p.get("proposalId") or "").strip()
    title = str(p.get("title") or "Proposal").strip() or "Proposal"
    status = str(p.get("status") or "").strip()
    rfp_id = str(p.get("rfpId") or "").strip()

    meta_parts: list[str] = []
    if status:
        meta_parts.append(status)
    if rfp_id:
        meta_parts.append(f"rfp {rfp_id}")
    meta = f" — {' · '.join(meta_parts)}" if meta_parts else ""

    if pid:
        return f"- <{_proposal_url(pid)}|{title}> `{pid}`{meta}"
    return f"- {title}{meta}"


def _days_until_submission(rfp: dict) -> int | None:
    try:
        dm = rfp.get("dateMeta")
        dates = (dm or {}).get("dates") if isinstance(dm, dict) else None
        sub = (dates or {}).get("submissionDeadline") if isinstance(dates, dict) else None
        du = sub.get("daysUntil") if isinstance(sub, dict) else None
        return int(du) if du is not None else None
    except Exception:
        return None


def _rfp_stage(rfp: dict, proposals_for_rfp: list[dict]) -> str:
    """
    Mirror the frontend pipeline stage logic (frontend/app/(app)/pipeline/page.tsx).
    """
    try:
        if bool(rfp.get("isDisqualified")):
            return "Disqualified"
        review = rfp.get("review") if isinstance(rfp.get("review"), dict) else {}
        decision = str((review or {}).get("decision") or "").strip().lower()
        if decision == "no_bid":
            return "NoBid"
        if decision != "bid":
            return "BidDecision"
        if not proposals_for_rfp:
            return "ProposalDraft"

        p = sorted(
            proposals_for_rfp,
            key=lambda x: str(x.get("updatedAt") or ""),
            reverse=True,
        )[0]
        status = str(p.get("status") or "").strip().lower()
        if status == "submitted":
            return "Submitted"
        if status == "ready_to_submit":
            return "ReadyToSubmit"
        if status in ("rework", "needs_changes"):
            return "Rework"
        if status == "in_review":
            return "ReviewRebuttal"
        return "ProposalDraft"
    except Exception:
        return "BidDecision"


def _build_rfp_summary_blocks(*, rfp: dict, proposals_count: int) -> tuple[str, list[dict[str, Any]]]:
    rid = str(rfp.get("_id") or "").strip()
    title = str(rfp.get("title") or "RFP").strip() or "RFP"
    client = str(rfp.get("clientName") or "").strip()
    ptype = str(rfp.get("projectType") or "").strip()
    due = str(rfp.get("submissionDeadline") or "").strip()
    du = _days_until_submission(rfp)
    fit = rfp.get("fitScore")
    review = rfp.get("review") if isinstance(rfp.get("review"), dict) else {}
    decision = str((review or {}).get("decision") or "").strip() or "unreviewed"

    fields: list[dict[str, str]] = []
    if client:
        fields.append({"type": "mrkdwn", "text": f"*Client*\n{client}"})
    if ptype:
        fields.append({"type": "mrkdwn", "text": f"*Type*\n{ptype}"})
    if due:
        due_line = f"{due}" + (f" (in {du}d)" if isinstance(du, int) else "")
        fields.append({"type": "mrkdwn", "text": f"*Due*\n{due_line}"})
    if isinstance(fit, (int, float)):
        fields.append({"type": "mrkdwn", "text": f"*Fit*\n{int(fit)}"})
    fields.append({"type": "mrkdwn", "text": f"*Bid decision*\n`{decision}`"})
    fields.append({"type": "mrkdwn", "text": f"*Proposals*\n{int(proposals_count)}"})

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
        {"type": "section", "fields": fields[:10]},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open RFP"},
                    "url": _rfp_url(rid),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Pipeline"},
                    "url": _pipeline_url(),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "List proposals"},
                    "action_id": "polaris_list_rfp_proposals",
                    "value": rid,
                },
            ],
        },
    ]
    text = f"{title} — {client}" if client else title
    return text, blocks


def _search_rfps(query: str, *, max_results: int = 10) -> list[dict]:
    q = str(query or "").strip().lower()
    if not q:
        return []
    resp = list_rfps(page=1, limit=200)
    data = resp.get("data") or []
    out: list[dict] = []
    for r in data:
        if not isinstance(r, dict):
            continue
        hay = f"{r.get('title') or ''} {r.get('clientName') or ''} {r.get('projectType') or ''}".lower()
        if q in hay:
            out.append(r)
        if len(out) >= max_results:
            break
    return out


def _recent_rfps(*, max_results: int = 10) -> list[dict]:
    resp = list_rfps(page=1, limit=max(1, min(50, int(max_results))))
    data = resp.get("data") or []
    return [r for r in data if isinstance(r, dict)]


def _recent_proposals(*, max_results: int = 10) -> list[dict]:
    resp = list_proposals(page=1, limit=max(1, min(50, int(max_results))))
    data = resp.get("data") or []
    return [p for p in data if isinstance(p, dict)]


def _search_proposals(query: str, *, max_results: int = 10) -> list[dict]:
    q = str(query or "").strip().lower()
    if not q:
        return []
    resp = list_proposals(page=1, limit=200)
    data = resp.get("data") or []
    out: list[dict] = []
    for p in data:
        if not isinstance(p, dict):
            continue
        hay = f"{p.get('title') or ''} {p.get('status') or ''} {p.get('rfpId') or ''}".lower()
        if q in hay:
            out.append(p)
        if len(out) >= max_results:
            break
    return out


def _verify_slack_signature(*, body: bytes, timestamp: str | None, signature: str | None) -> None:
    """
    Verify Slack request signature.
    https://api.slack.com/authentication/verifying-requests-from-slack
    """
    secret = (
        str(settings.slack_signing_secret or "").strip()
        or (get_secret_str("SLACK_SIGNING_SECRET") or "")
    )
    if not secret:
        # Misconfiguration - fail closed.
        raise HTTPException(status_code=503, detail="Slack integration not configured")

    ts = str(timestamp or "").strip()
    sig = str(signature or "").strip()
    if not ts or not sig:
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    try:
        ts_i = int(ts)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Prevent replay attacks (5 minutes window).
    now = int(time.time())
    if abs(now - ts_i) > 60 * 5:
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    base = b"v0:" + ts.encode("utf-8") + b":" + (body or b"")
    digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"

    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")


async def _require_slack_request(request: Request) -> bytes:
    body = await request.body()
    _verify_slack_signature(
        body=body,
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        signature=request.headers.get("X-Slack-Signature"),
    )
    return body


def _slack_agent_answer_task(
    *,
    question: str,
    response_url: str | None,
    channel_id: str | None,
    user_id: str | None,
    thread_ts: str | None,
) -> None:
    """
    Background: run Slack agent and respond either via response_url (slash command)
    or via chat.postMessage (app mention).
    """
    try:
        # Unified identity enrichment + memory injection.
        ctx = resolve_actor_context(slack_user_id=user_id, slack_team_id=None, slack_enterprise_id=None)
        display_name = ctx.display_name
        email = ctx.email
        user_profile = ctx.user_profile

        ans = run_slack_agent_question(
            question=question,
            user_id=user_id,
            user_display_name=display_name,
            user_email=email,
            user_profile=user_profile,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )
        txt = str(ans.text or "").strip() or "No answer."

        if response_url:
            respond_via_response_url(
                response_url=response_url,
                text=txt,
                response_type="ephemeral",
                blocks=ans.blocks,
            )
            return

        # App mention reply: post into thread (best-effort).
        if channel_id and is_slack_configured():
            chat_post_message_result(
                text=txt,
                channel=channel_id,
                blocks=ans.blocks,
                unfurl_links=False,
                thread_ts=thread_ts,
            )
    except Exception as e:
        msg = str(e) or "agent_failed"
        if response_url:
            try:
                respond_via_response_url(
                    response_url=response_url,
                    text=f"Sorry — I couldn’t answer that ({msg}).",
                    response_type="ephemeral",
                )
            except Exception:
                pass
        else:
            try:
                if channel_id and is_slack_configured():
                    chat_post_message_result(
                        text="Sorry — I couldn’t answer that (server error).",
                        channel=channel_id,
                        unfurl_links=False,
                        thread_ts=thread_ts,
                    )
            except Exception:
                pass


def _slack_operator_mention_task(
    *,
    question: str,
    channel_id: str | None,
    user_id: str | None,
    thread_ts: str | None,
    correlation_id: str | None = None,
) -> None:
    """
    Background: operator-style agent for app mentions.

    This agent prefers tool-based replies and durable state updates.
    """
    ch = str(channel_id or "").strip() or None
    th = str(thread_ts or "").strip() or None
    if not ch or not th:
        return
    # If the user recently ran `/polaris link-thread <rfpId>`, bind that RFP to this thread.
    try:
        uid = str(user_id or "").strip() or None
        if uid:
            pend = consume_pending_link(channel_id=ch, slack_user_id=uid)
            if isinstance(pend, dict) and str(pend.get("rfpId") or "").strip():
                rid = str(pend.get("rfpId") or "").strip()
                set_binding(channel_id=ch, thread_ts=th, rfp_id=rid, bound_by_slack_user_id=uid)
    except Exception:
        pass
    try:
        run_slack_operator_for_mention(
            question=question,
            channel_id=ch,
            thread_ts=th,
            user_id=user_id,
            correlation_id=correlation_id,
            max_steps=8,
        )
    except Exception:
        # Best-effort fallback message (keep terse).
        try:
            chat_post_message_result(
                text="Sorry — I hit an error while working on that.",
                channel=ch,
                thread_ts=th,
                unfurl_links=False,
            )
        except Exception:
            pass

@router.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    await _require_slack_request(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # URL verification challenge (initial setup)
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # Event callbacks - respond quickly; best-effort handling only.
    if payload.get("type") == "event_callback":
        res = handle_event_callback(payload=payload if isinstance(payload, dict) else {}, background_tasks=background_tasks)
        return res.response_json or {"ok": bool(res.ok)}

    return {"ok": True}


@router.post("/slack/commands")
async def slack_commands(request: Request, background_tasks: BackgroundTasks):
    body = await _require_slack_request(request)

    # Slack sends application/x-www-form-urlencoded for slash commands.
    form = parse_qs(body.decode("utf-8", errors="ignore"))
    text = str((form.get("text") or [""])[0] or "").strip()
    response_url = str((form.get("response_url") or [""])[0] or "").strip() or None

    # Common fields (kept for future use)
    user_id = str((form.get("user_id") or [""])[0] or "").strip() or None
    channel_id = str((form.get("channel_id") or [""])[0] or "").strip() or None

    parts = [p for p in text.split() if p.strip()]
    sub = (parts[0].lower() if parts else "help").strip()
    args = parts[1:]
    rt = _command_response_type(sub)

    if sub in ("help", "h", "?"):
        return {
            "response_type": rt,
            "text": "\n".join(
                [
                    "*Polaris RFP Slack commands*",
                    "- `/polaris help`",
                    "- `/polaris ask <question>` (ask Polaris about RFPs/proposals/tasks/content)",
                    "- `/polaris link` (link your Slack user to your Polaris profile)",
                    "- `/polaris link-thread <rfpId>` (next @mention in a thread will bind that thread to the RFP)",
                    "- `/polaris where` (thread binding help)",
                    "- `/polaris remember <note>` (save a personal note/preferences; asks for confirmation)",
                    "- `/polaris forget memory` (clear saved memory; asks for confirmation)",
                    "- `/polaris recent [n]` (list latest RFPs)",
                    "- `/polaris search <keywords>` (search title/client/type)",
                    "- `/polaris upload [n]` (upload latest PDFs from this channel; default 1)",
                    "- `/polaris channel` (show this channel's ID; use for private rfp-machine config)",
                    "- `/polaris slacktest` (post a diagnostic message to rfp-machine)",
                    "- `/polaris due [days]` (submission deadlines due soon; default 7)",
                    "- `/polaris pipeline [stage]` (group RFPs by workflow stage)",
                    "- `/polaris proposals [n]` (list latest proposals)",
                    "- `/polaris proposal <keywords>` (search proposals)",
                    "- `/polaris summarize <keywords>` (RFP summary + links)",
                    "- `/polaris links` (quick links)",
                    "- `/polaris rfp <rfpId>` (returns a link)",
                    "- `/polaris open <keywords>` (first search result)",
                    "- `/polaris job <jobId>` (RFP upload job status)",
                ]
            ),
        }

    if sub in ("diag", "diagnostics"):
        # Lightweight health + permissions probe.
        token_present = bool(get_bot_token())
        auth = slack_api_get(method="auth.test", params={}) if token_present else {"ok": False, "error": "missing_token"}
        user_info = slack_api_get(method="users.info", params={"user": user_id}) if (token_present and user_id) else {"ok": False, "error": "missing_user_id"}
        # Attempt email presence if users.info worked.
        email = None
        try:
            if bool(user_info.get("ok")):
                u_raw = user_info.get("user")
                u: dict[str, Any] = u_raw if isinstance(u_raw, dict) else {}
                prof_raw = u.get("profile")
                prof: dict[str, Any] = prof_raw if isinstance(prof_raw, dict) else {}
                email = str(prof.get("email") or "").strip().lower() or None
        except Exception:
            email = None

        ctx = resolve_actor_context(slack_user_id=user_id, slack_team_id=None, slack_enterprise_id=None)

        lines = [
            "*Polaris Slack diagnostics*",
            f"- slack_enabled: `{bool(settings.slack_enabled)}`",
            f"- slack_agent_enabled: `{bool(settings.slack_agent_enabled)}`",
            f"- slack_agent_actions_enabled: `{bool(settings.slack_agent_actions_enabled)}`",
            f"- bot_token_present: `{token_present}`",
            "",
            "*Slack API*",
            f"- auth.test: `{bool(auth.get('ok'))}`" + (f" (error `{auth.get('error')}`)" if not auth.get("ok") else ""),
            f"- users.info: `{bool(user_info.get('ok'))}`" + (f" (error `{user_info.get('error')}`)" if not user_info.get("ok") else ""),
            f"- email_visible: `{bool(email)}`",
            "",
            "*Identity mapping*",
            f"- slack_user_id: `{user_id}`",
            f"- display_name: `{ctx.display_name or ''}`",
            f"- email: `{ctx.email or ''}`",
            f"- user_sub: `{ctx.user_sub or ''}`",
            f"- user_profile_resolved: `{bool(ctx.user_profile)}`",
            "",
            "*Tips*",
            "- If `users.info` fails with `missing_scope`, add `users:read` (and `users:read.email` for email mapping), then reinstall.",
            "- If posting fails with `not_in_channel`, invite the bot to the channel.",
        ]
        try:
            append_event(
                rfp_id="rfp_slack_agent",
                type="slack_diagnostics",
                payload={
                    "authOk": bool(auth.get("ok")),
                    "usersInfoOk": bool(user_info.get("ok")),
                    "emailVisible": bool(email),
                    "userSubResolved": bool(ctx.user_sub),
                },
                inputs_redacted={"channelId": channel_id, "slackUserId": user_id},
                created_by="slack_commands",
            )
        except Exception:
            pass
        return {"response_type": "ephemeral", "text": "\n".join([line for line in lines if line is not None])}

    if sub in ("link-thread", "linkthread"):
        if not user_id or not channel_id:
            return {"response_type": "ephemeral", "text": "Missing Slack user/channel context."}
        if not args:
            return {"response_type": "ephemeral", "text": "Usage: `/polaris link-thread <rfpId>`"}
        rid = str(args[0] or "").strip()
        if not rid.startswith("rfp_"):
            return {"response_type": "ephemeral", "text": "Usage: `/polaris link-thread <rfpId>` (example: `rfp_abc12345`)"} 
        create_pending_link(channel_id=channel_id, slack_user_id=user_id, rfp_id=rid, ttl_seconds=10 * 60)
        return {
            "response_type": "ephemeral",
            "text": (
                f"Got it. Next time you mention Polaris *in the target thread* in this channel, "
                f"I’ll bind that thread to `{rid}`.\n\n"
                "Tip: you can also do it directly in-thread with: `@polaris link <rfpId>`"
            ),
        }

    if sub == "where":
        if not user_id or not channel_id:
            return {"response_type": "ephemeral", "text": "Missing Slack user/channel context."}
        pend = get_pending_link(channel_id=channel_id, slack_user_id=user_id) or {}
        pend_rid = str((pend or {}).get("rfpId") or "").strip() or None
        lines = [
            "*Thread → RFP binding*",
            "- To bind a thread: in the thread, say `@polaris link rfp_...`",
            "- Or: run `/polaris link-thread rfp_...`, then @mention Polaris in the target thread within 10 minutes.",
        ]
        if pend_rid:
            lines.append(f"- Pending link for your next thread mention: `{pend_rid}`")
        return {"response_type": "ephemeral", "text": "\n".join(lines)}

    if sub == "link":
        if not user_id:
            return {"response_type": "ephemeral", "text": "Missing Slack user context."}
        txt = "\n".join(
            [
                "*Link Slack → Polaris*",
                f"- Your Slack user id: `{user_id}`",
                "",
                "To enable personalized memory/preferences, paste this into Polaris:",
                f"- Open: <{_profile_url()}|Profile>",
                "- Find the “Polaris profile” section",
                "- Paste the Slack user id and Save",
            ]
        )
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": txt}},
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Open Profile"}, "url": _profile_url()},
                ],
            },
        ]
        return {"response_type": "ephemeral", "text": f"Your Slack user id is `{user_id}`", "blocks": blocks}

    if sub in ("remember", "memory"):
        if not args:
            return {"response_type": "ephemeral", "text": "Usage: `/polaris remember <note>`"}
        if not user_id:
            return {"response_type": "ephemeral", "text": "Missing Slack user context."}
        note = " ".join(args).strip()
        if len(note) > 600:
            note = note[:600] + "…"
        saved = create_action(
            kind="update_user_profile",
            payload={
                "action": "update_user_profile",
                "args": {"aiMemoryAppend": note},
                "requestedBySlackUserId": user_id,
                "channelId": channel_id,
                "threadTs": None,
                "question": text,
            },
            ttl_seconds=900,
        )
        aid = str(saved.get("actionId") or "").strip()
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Save to memory?*\n"
                    f"- note: `{note}`\n\n"
                    "This will be used to personalize future responses.\n\nConfirm?",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Confirm"},
                        "style": "primary",
                        "action_id": "polaris_confirm_action",
                        "value": aid,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Cancel"},
                        "action_id": "polaris_cancel_action",
                        "value": aid,
                    },
                ],
            },
        ]
        return {
            "response_type": "ephemeral",
            "text": f"Proposed memory update: `{note}`",
            "blocks": blocks,
        }

    if sub == "forget":
        if not args:
            return {"response_type": "ephemeral", "text": "Usage: `/polaris forget memory`"}
        if not user_id:
            return {"response_type": "ephemeral", "text": "Missing Slack user context."}
        target = str(args[0] or "").strip().lower()
        if target not in ("memory", "mem"):
            return {"response_type": "ephemeral", "text": "Supported: `/polaris forget memory`"}
        saved = create_action(
            kind="update_user_profile",
            payload={
                "action": "update_user_profile",
                "args": {"clearMemory": True},
                "requestedBySlackUserId": user_id,
                "channelId": channel_id,
                "threadTs": None,
                "question": text,
            },
            ttl_seconds=900,
        )
        aid = str(saved.get("actionId") or "").strip()
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Clear saved memory?*\nConfirm?"}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Confirm"},
                        "style": "danger",
                        "action_id": "polaris_confirm_action",
                        "value": aid,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Cancel"},
                        "action_id": "polaris_cancel_action",
                        "value": aid,
                    },
                ],
            },
        ]
        return {"response_type": "ephemeral", "text": "Proposed: clear memory", "blocks": blocks}

    if sub in ("ask", "q"):
        if not bool(settings.slack_agent_enabled):
            return {"response_type": "ephemeral", "text": "Slack AI agent is disabled."}
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Usage: `/polaris ask <question>`",
            }
        if not response_url:
            return {
                "response_type": "ephemeral",
                "text": "Missing response_url from Slack (cannot reply asynchronously).",
            }
        question = " ".join(args).strip()
        # Rate limit by Slack user_id (best-effort).
        if user_id and not slack_allow(key=f"slack_cmd_user:{user_id}", limit=10, per_seconds=60):
            return {"response_type": "ephemeral", "text": "Slow down a bit and try again in a minute."}
        background_tasks.add_task(
            _slack_agent_answer_task,
            question=question,
            response_url=response_url,
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=None,
        )
        return {
            "response_type": "ephemeral",
            "text": "Thinking…",
        }

    if sub in ("channel", "chan", "whereami"):
        ch = channel_id or ""
        if not ch:
            return {
                "response_type": "ephemeral",
                "text": "Channel context missing (try running from a channel, not a DM).",
            }
        return {
            "response_type": "ephemeral",
            "text": "\n".join(
                [
                    f"*Channel ID:* `{ch}`",
                    "",
                    "For private `rfp-machine`, set `SLACK_RFP_MACHINE_CHANNEL` to this ID (starts with `G`).",
                    "Also ensure the bot user is invited to the private channel.",
                ]
            ),
        }

    if sub in ("slacktest", "slack-test", "testslack"):
        # Diagnostic: try posting to configured rfp-machine channel and report Slack error.
        target = (
            str(settings.slack_rfp_machine_channel or "").strip()
            or (get_secret_str("SLACK_RFP_MACHINE_CHANNEL") or "")
        ).strip()
        if not target:
            return {
                "response_type": "ephemeral",
                "text": "Missing `SLACK_RFP_MACHINE_CHANNEL` configuration.",
            }
        res = post_message_result(
            text="Polaris Slack test: rfp-machine notifications are configured.",
            channel=target,
            unfurl_links=False,
        )
        if res.get("ok"):
            return {
                "response_type": "ephemeral",
                "text": f"✅ Posted test message to `{target}`.",
            }
        return {
            "response_type": "ephemeral",
            "text": (
                "Failed to post test message.\n"
                f"- channel: `{target}`\n"
                f"- error: `{res.get('error')}`\n"
                f"- status: `{res.get('status_code')}`\n"
                "Common fixes: invite bot to the private channel; use the channel ID (C…/G…); ensure SLACK_ENABLED=true + token present."
            ),
        }

    if sub == "links":
        return {
            "response_type": rt,
            "text": "\n".join(
                [
                    "*Quick links*",
                    f"- <{_pipeline_url()}|Pipeline>",
                    f"- <{_rfps_url()}|RFPs>",
                    f"- <{_proposals_url()}|Proposals>",
                    f"- <{_upload_url()}|Upload RFP>",
                    f"- <{_templates_url()}|Templates>",
                    f"- <{_content_url()}|Content Library>",
                ]
            ),
        }

    if sub in ("upload", "ingest"):
        # Slash commands must respond within 3 seconds. We ack quickly and post
        # results later via response_url.
        if not bool(settings.slack_enabled) or not get_bot_token():
            return {
                "response_type": "ephemeral",
                "text": "Slack integration not configured on the server (missing bot token).",
            }
        if not channel_id or not response_url:
            return {
                "response_type": "ephemeral",
                "text": "Missing channel context. Try running the command from a channel, not a DM.",
            }
        n = 1
        if args:
            try:
                n = int(args[0])
            except Exception:
                n = 1
        n = max(1, min(5, n))

        background_tasks.add_task(
            _slack_upload_latest_pdfs_task,
            response_url=response_url,
            channel_id=channel_id,
            n=n,
        )
        return {
            "response_type": "ephemeral",
            "text": f"Uploading latest {n} PDF(s) from this channel…",
        }

    if sub in ("recent", "list", "rfps"):
        n = 8
        if args:
            try:
                n = int(args[0])
            except Exception:
                n = 8
        n = max(1, min(15, n))
        items = _recent_rfps(max_results=n)
        if not items:
            return {"response_type": rt, "text": "No RFPs found."}
        lines = [f"*Latest {min(n, len(items))} RFPs*"] + [_format_rfp_line(r) for r in items[:n]]
        return {"response_type": rt, "text": "\n".join(lines)}

    if sub in ("search", "find"):
        if not args:
            return {"response_type": rt, "text": "Usage: `/polaris search <keywords>`"}
        q = " ".join(args).strip()
        hits = _search_rfps(q, max_results=10)
        if not hits:
            return {"response_type": rt, "text": f"No matches for: `{q}`"}
        lines = [f"*Search results for:* `{q}`"] + [_format_rfp_line(r) for r in hits]
        return {"response_type": rt, "text": "\n".join(lines)}

    if sub == "open":
        if not args:
            return {"response_type": rt, "text": "Usage: `/polaris open <keywords>`"}
        q = " ".join(args).strip()
        hits = _search_rfps(q, max_results=1)
        if not hits:
            return {"response_type": rt, "text": f"No matches for: `{q}`"}
        r = hits[0]
        rid = str(r.get("_id") or "").strip()
        if not rid:
            return {"response_type": rt, "text": "Match found but missing rfpId."}
        title = str(r.get("title") or "RFP").strip()
        client = str(r.get("clientName") or "").strip()
        extra = f" ({client})" if client else ""
        return {"response_type": rt, "text": f"<{_rfp_url(rid)}|{title}>{extra}"}

    if sub in ("due", "deadlines"):
        days = 7
        if args:
            try:
                days = int(args[0])
            except Exception:
                days = 7
        days = max(1, min(30, days))
        items = _recent_rfps(max_results=200)
        due_hits: list[dict] = []
        for r in items:
            du = _days_until_submission(r)
            if du is None:
                continue
            if 0 <= du <= days:
                due_hits.append(r)

        due_hits.sort(
            key=lambda r: (
                _days_until_submission(r) if _days_until_submission(r) is not None else 9999,
                str(r.get("createdAt") or ""),
            )
        )
        if not due_hits:
            return {
                "response_type": rt,
                "text": f"No RFPs due in the next {days} days.",
            }
        lines = [f"*RFPs due in the next {days} days*"] + [
            _format_rfp_line(r) for r in due_hits[:12]
        ]
        if len(due_hits) > 12:
            lines.append(f"_Showing 12 of {len(due_hits)}._")
        return {"response_type": rt, "text": "\n".join(lines)}

    if sub == "pipeline":
        stage_filter = str(args[0] or "").strip().lower() if args else ""
        stage_map = {
            "bid": "BidDecision",
            "decision": "BidDecision",
            "draft": "ProposalDraft",
            "review": "ReviewRebuttal",
            "rebuttal": "ReviewRebuttal",
            "rework": "Rework",
            "ready": "ReadyToSubmit",
            "submit": "ReadyToSubmit",
            "submitted": "Submitted",
            "nobid": "NoBid",
            "no-bid": "NoBid",
            "disqualified": "Disqualified",
        }
        want = stage_map.get(stage_filter) if stage_filter else None

        rfps = _recent_rfps(max_results=200)
        props = _recent_proposals(max_results=200)
        by_rfp: dict[str, list[dict]] = {}
        for p in props:
            rid = str(p.get("rfpId") or "").strip()
            if not rid:
                continue
            by_rfp.setdefault(rid, []).append(p)

        order = [
            "BidDecision",
            "ProposalDraft",
            "ReviewRebuttal",
            "Rework",
            "ReadyToSubmit",
            "Submitted",
            "NoBid",
            "Disqualified",
        ]
        grouped: dict[str, list[dict]] = {k: [] for k in order}

        for r in rfps:
            rid = str(r.get("_id") or "").strip()
            stage = _rfp_stage(r, by_rfp.get(rid, []))
            if want and stage != want:
                continue
            grouped.setdefault(stage, []).append(r)

        if want and all(len(grouped.get(k, [])) == 0 for k in grouped.keys()):
            return {
                "response_type": rt,
                "text": f"No RFPs found in stage `{want}`.",
            }

        def _sort_key(r: dict):
            du = _days_until_submission(r)
            return (du if isinstance(du, int) else 9999, str(r.get("createdAt") or ""))

        for k in list(grouped.keys()):
            grouped[k].sort(key=_sort_key)

        pipeline_lines: list[str] = []
        pipeline_lines.append("*Pipeline*")
        pipeline_lines.append(f"<{_pipeline_url()}|Open Pipeline>")
        if want:
            pipeline_lines.append(f"_Filter:_ `{want}`")
        for k in order:
            if not grouped.get(k):
                continue
            pipeline_lines.append(f"\n*{k}* ({len(grouped[k])})")
            for r in grouped[k][:6]:
                pipeline_lines.append(_format_rfp_line(r))
            if len(grouped[k]) > 6:
                pipeline_lines.append(f"_…and {len(grouped[k]) - 6} more_")
        return {"response_type": rt, "text": "\n".join(pipeline_lines)}

    if sub in ("proposals", "proposal-list"):
        n = 8
        if args:
            try:
                n = int(args[0])
            except Exception:
                n = 8
        n = max(1, min(15, n))
        items = _recent_proposals(max_results=n)
        if not items:
            return {"response_type": rt, "text": "No proposals found."}
        lines = [f"*Latest {min(n, len(items))} proposals*"] + [
            _format_proposal_line(p) for p in items[:n]
        ]
        return {"response_type": rt, "text": "\n".join(lines)}

    if sub == "proposal":
        if not args:
            return {
                "response_type": rt,
                "text": "Usage: `/polaris proposal <keywords>`",
            }
        q = " ".join(args).strip()
        hits = _search_proposals(q, max_results=5)
        if not hits:
            return {"response_type": rt, "text": f"No proposal matches for: `{q}`"}
        if len(hits) == 1:
            p = hits[0]
            pid = str(p.get("_id") or "").strip()
            title = str(p.get("title") or "Proposal").strip()
            return {
                "response_type": rt,
                "text": f"<{_proposal_url(pid)}|{title}> `{pid}`",
            }
        lines = [f"*Proposal matches for:* `{q}`"] + [_format_proposal_line(p) for p in hits]
        return {"response_type": rt, "text": "\n".join(lines)}

    if sub in ("summarize", "summary"):
        if not args:
            return {
                "response_type": rt,
                "text": "Usage: `/polaris summarize <rfp keywords>`",
            }
        q = " ".join(args).strip()
        hits = _search_rfps(q, max_results=5)
        if not hits:
            return {"response_type": rt, "text": f"No RFP matches for: `{q}`"}

        r = hits[0]
        rid = str(r.get("_id") or "").strip()
        warnings = r.get("dateWarnings") if isinstance(r.get("dateWarnings"), list) else []
        reqs = r.get("keyRequirements") if isinstance(r.get("keyRequirements"), list) else []

        # Proposals count (cheap join)
        props = _recent_proposals(max_results=200)
        prop_count = sum(1 for p in props if str(p.get("rfpId") or "").strip() == rid)

        # Prefer blocks for a richer Slack UX.
        text0, blocks2 = _build_rfp_summary_blocks(rfp=r, proposals_count=prop_count)
        # Append warnings + requirements into plain text (keeps blocks clean).
        summary_lines: list[str] = []
        if warnings:
            summary_lines.append(f"*Date warnings:* {len(warnings)} (e.g. {str(warnings[0])})")
        if reqs:
            top = [str(x).strip() for x in reqs[:5] if str(x).strip()]
            if top:
                summary_lines.append("*Top requirements:*")
                summary_lines.extend([f"- {t}" for t in top])
        if len(hits) > 1:
            summary_lines.append("*Other matches:*")
            for alt in hits[1:4]:
                summary_lines.append(_format_rfp_line(alt))
        text = (text0 + ("\n" + "\n".join(summary_lines) if summary_lines else "")).strip()
        return {"response_type": rt, "text": text, "blocks": blocks2}

    if sub == "rfp":
        if not args:
            return {"response_type": rt, "text": "Usage: `/polaris rfp <rfpId>`"}
        rfp_id = str(args[0]).strip()
        rfp = get_rfp_by_id(rfp_id)
        if not rfp:
            return {"response_type": rt, "text": f"RFP not found: `{rfp_id}`"}
        url = _rfp_url(rfp_id)
        title = str(rfp.get("title") or "RFP").strip()
        client = str(rfp.get("clientName") or "").strip()
        extra = f" ({client})" if client else ""
        return {"response_type": rt, "text": f"<{url}|{title}>{extra}"}

    if sub == "job":
        if not args:
            return {"response_type": "ephemeral", "text": "Usage: `/polaris job <jobId>`"}
        job_id = str(args[0]).strip()
        job = get_job(job_id)
        if not job:
            return {"response_type": "ephemeral", "text": f"Job not found: `{job_id}`"}
        status = str(job.get("status") or "").strip() or "unknown"
        rfp_id = str(job.get("rfpId") or "").strip()
        if rfp_id:
            url = str(settings.frontend_base_url or "").rstrip("/") + f"/rfps/{rfp_id}"
            return {
                "response_type": "ephemeral",
                "text": f"Job `{job_id}` is *{status}*. RFP: <{url}|{rfp_id}>",
            }
        err = str(job.get("error") or "").strip()
        suffix = f" Error: {err}" if err else ""
        return {"response_type": "ephemeral", "text": f"Job `{job_id}` is *{status}*.{suffix}"}

    # Unknown subcommand
    log.info("slack_command_unknown", user_id=user_id, channel_id=channel_id, subcommand=sub)
    return {"response_type": "ephemeral", "text": f"Unknown command: `{sub}`. Try `/polaris help`."}


@router.post("/slack/interactions")
async def slack_interactions(request: Request):
    """
    Slack interactivity endpoint (Block Kit actions, buttons, selects, etc).

    Slack sends application/x-www-form-urlencoded with a single field:
      payload=<json>
    """
    body = await _require_slack_request(request)
    form = parse_qs(body.decode("utf-8", errors="ignore"))
    payload_raw = str((form.get("payload") or [""])[0] or "").strip()
    if not payload_raw:
        raise HTTPException(status_code=400, detail="Missing payload")

    try:
        payload = json.loads(payload_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload JSON")

    ptype = str(payload.get("type") or "").strip() or None
    user_id = str(((payload.get("user") or {}) if isinstance(payload.get("user"), dict) else {}).get("id") or "").strip() or None
    channel_id = str(((payload.get("channel") or {}) if isinstance(payload.get("channel"), dict) else {}).get("id") or "").strip() or None
    response_url = str(payload.get("response_url") or "").strip() or None

    # New dispatcher handles shortcuts + modals. We keep legacy block_actions handling below
    # until migrated, because it contains action execution + follow-up routing.
    if ptype in ("message_action", "shortcut", "view_submission", "view_closed"):
        res = handle_interactivity(payload=payload, background_tasks=None)
        return res.response_json or {"response_type": "ephemeral", "text": "Got it."}

    # Handle Block Kit actions quickly (<3s) then post details via response_url.
    if ptype == "block_actions":
        actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
        act = actions[0] if actions else {}
        action_id = str(act.get("action_id") or "").strip()
        value = str(act.get("value") or "").strip()
        msg_obj = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        msg_ts = str(msg_obj.get("ts") or "").strip() or None
        msg_thread_ts = str(msg_obj.get("thread_ts") or "").strip() or None
        # If the interactive prompt was posted in a thread, use the root thread ts.
        # If it was posted in-channel, prefer replying in a new thread off that message.
        default_thread_ts = msg_thread_ts or msg_ts
        is_prompt_in_channel = bool(msg_ts) and not bool(msg_thread_ts)

        if action_id == "polaris_list_rfp_proposals":
            # Ack immediately then post followup.
            if response_url:
                try:
                    resp = list_proposals(page=1, limit=200)
                    items = resp.get("data") or []
                    rid = value
                    hits = [
                        p for p in items
                        if isinstance(p, dict) and str(p.get("rfpId") or "").strip() == rid
                    ]
                    if not hits:
                        respond_via_response_url(
                            response_url=response_url,
                            text=f"No proposals found for RFP `{rid}`.",
                            response_type="ephemeral",
                        )
                    else:
                        lines = [f"*Proposals for* `{rid}`:"]
                        for p in hits[:12]:
                            lines.append(_format_proposal_line(p))
                        if len(hits) > 12:
                            lines.append(f"_Showing 12 of {len(hits)}._")
                        respond_via_response_url(
                            response_url=response_url,
                            text="\n".join(lines),
                            response_type="ephemeral",
                        )
                except Exception:
                    respond_via_response_url(
                        response_url=response_url,
                        text="Failed to list proposals (server error).",
                        response_type="ephemeral",
                    )
            return {"response_type": "ephemeral", "text": "Listing proposals…"}

        if action_id in ("polaris_confirm_action", "polaris_cancel_action"):
            if not response_url:
                return {"response_type": "ephemeral", "text": "Missing response_url."}
            if not bool(settings.slack_agent_actions_enabled):
                respond_via_response_url(
                    response_url=response_url,
                    text="Actions are currently disabled.",
                    response_type="ephemeral",
                )
                return {"response_type": "ephemeral", "text": "Actions disabled."}
            aid = value
            if not aid:
                return {"response_type": "ephemeral", "text": "Missing action id."}
            stored = get_action(aid)
            if not stored:
                respond_via_response_url(
                    response_url=response_url,
                    text="That action expired or was not found.",
                    response_type="ephemeral",
                )
                return {"response_type": "ephemeral", "text": "Action not found."}

            # Prefer the channel/thread captured at proposal time, but fall back to
            # the interactive payload (so results stay in the originating thread).
            stored_payload_raw = stored.get("payload")
            payload2: dict[str, Any] = stored_payload_raw if isinstance(stored_payload_raw, dict) else {}
            ch_post = str(payload2.get("channelId") or "").strip() or channel_id or None
            th_post = str(payload2.get("threadTs") or "").strip() or default_thread_ts or None

            if action_id == "polaris_cancel_action":
                try:
                    mark_action_done(action_id=aid, status="cancelled", result={"ok": True})
                except Exception:
                    pass
                # Replace the interactive prompt (remove buttons) instead of deleting it,
                # so the outcome stays in-thread and doesn't produce a separate follow-up
                # message in the parent channel UI.
                respond_via_response_url(
                    response_url=response_url,
                    # Avoid cluttering the main channel if the prompt was posted there.
                    text="Cancelled. (see thread)" if is_prompt_in_channel else "Cancelled.",
                    response_type="ephemeral",
                    replace_original=True,
                )
                if ch_post and th_post:
                    chat_post_message_result(text="Cancelled.", channel=ch_post, thread_ts=th_post, unfurl_links=False)
                return Response(status_code=200)

            # Confirm
            kind = str(stored.get("kind") or "").strip()
            args_raw = payload2.get("args")
            args2 = args_raw if isinstance(args_raw, dict) else {}
            args2 = args2 if isinstance(args2, dict) else {}
            # Inject actor + original requester to prevent action hijacking.
            if user_id:
                args2["_actorSlackUserId"] = user_id
                # Best-effort: also inject resolved user_sub to unlock "me" flows.
                try:
                    ctx = resolve_actor_context(slack_user_id=user_id, slack_team_id=None, slack_enterprise_id=None)
                    if ctx.user_sub:
                        args2["_actorUserSub"] = ctx.user_sub
                except Exception:
                    pass
            req_by = str(payload2.get("requestedBySlackUserId") or "").strip()
            if req_by:
                args2["_requestedBySlackUserId"] = req_by
                # Mirror for userSub if available
                try:
                    # If the proposer stored a userSub, keep it authoritative.
                    req_sub = str(payload2.get("requestedByUserSub") or "").strip()
                    if req_sub:
                        args2["_requestedByUserSub"] = req_sub
                except Exception:
                    pass
            # Inject Slack context for downstream tools (useful for follow-up posts).
            ch2 = str(payload2.get("channelId") or "").strip()
            th2 = str(payload2.get("threadTs") or "").strip()
            q2 = str(payload2.get("question") or "").strip()
            if ch2 and "channelId" not in args2:
                args2["channelId"] = ch2
            if th2 and "threadTs" not in args2:
                args2["threadTs"] = th2
            if q2 and "question" not in args2:
                args2["question"] = q2
            # Fall back to the interactive payload so execution follow-ups land in the thread.
            if ch_post and "channelId" not in args2:
                args2["channelId"] = ch_post
            if th_post and "threadTs" not in args2:
                args2["threadTs"] = th_post

            try:
                result = execute_action(action_id=aid, kind=kind, args=args2)
            except Exception as e:
                result = {"ok": False, "error": str(e) or "execution_failed"}

            try:
                mark_action_done(action_id=aid, status="done" if result.get("ok") else "failed", result=result)
            except Exception:
                pass

            if result.get("ok"):
                msg = "Done."
            else:
                err = _extract_action_error(result)
                msg = f"Failed: `{err}`"

            summary = "\n".join(
                [
                    msg,
                    f"- action: `{kind}`",
                    f"- action_id: `{aid}`",
                ]
            )
            prompt_text = (msg + " (see thread)") if is_prompt_in_channel else summary

            # Keep the outcome in the same thread by updating the interactive message,
            # and (optionally) posting a normal threaded follow-up message for visibility.
            respond_via_response_url(
                response_url=response_url,
                text=prompt_text,
                response_type="ephemeral",
                replace_original=True,
            )
            if ch_post and th_post:
                chat_post_message_result(text=summary, channel=ch_post, thread_ts=th_post, unfurl_links=False)
            return Response(status_code=200)

    log.info(
        "slack_interaction_received",
        interaction_type=ptype,
        user_id=user_id,
        channel_id=channel_id,
    )

    return {
        "response_type": "ephemeral",
        "text": "Got it.",
    }


@router.post("/slack/workflow-steps")
async def slack_workflow_steps(request: Request):
    """
    Slack Workflow Builder steps endpoint (Steps from Apps).
    Configure Slack to POST workflow step payloads here.
    """
    await _require_slack_request(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    ptype = str((payload or {}).get("type") or "").strip()
    if ptype == "workflow_step_execute":
        return handle_workflow_step_execute(payload=payload if isinstance(payload, dict) else {})
    return {"ok": True}
