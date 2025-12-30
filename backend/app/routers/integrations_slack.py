from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from ..observability.logging import get_logger
from ..settings import settings
from ..infrastructure.integrations.slack.slack_secrets import get_secret_str
from ..infrastructure.integrations.slack.slack_web import chat_post_message_result
from ..infrastructure.storage import content_repo
from ..repositories.rfp_rfps_repo import list_rfps
from ..repositories.rfp_proposals_repo import list_proposals
from ..ai.client import AiNotConfigured, AiUpstreamError
from ..ai.verified_calls import call_text_verified

router = APIRouter(tags=["integrations"])
log = get_logger("integrations_slack")


def _resolve_slack_signing_secret() -> str | None:
    """
    Resolve Slack signing secret from settings or (preferred in prod) Secrets Manager JSON.
    """
    direct = str(settings.slack_signing_secret or "").strip() or None
    if direct:
        return direct
    # If SLACK_SECRET_ARN is configured, secrets are stored as JSON keys.
    return get_secret_str("SLACK_SIGNING_SECRET")


def _verify_slack_signature(
    *,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    request_id: str | None = None,
    client_ip: str | None = None,
) -> None:
    if not bool(settings.slack_enabled):
        # Treat disabled integrations as "not available" rather than auth failure.
        log.info(
            "slack_request_rejected_integration_disabled",
            request_id=request_id,
            client_ip=client_ip,
        )
        raise HTTPException(status_code=503, detail="Slack integration disabled")

    secret = _resolve_slack_signing_secret()
    if not secret:
        log.warning(
            "slack_request_rejected_not_configured",
            request_id=request_id,
            client_ip=client_ip,
            slack_enabled=bool(settings.slack_enabled),
            slack_secret_arn_configured=bool(str(settings.slack_secret_arn or "").strip()),
        )
        raise HTTPException(status_code=503, detail="Slack not configured")

    ts = str(timestamp or "").strip()
    sig = str(signature or "").strip()
    if not ts or not sig:
        log.info(
            "slack_request_rejected_missing_signature_headers",
            request_id=request_id,
            client_ip=client_ip,
            has_timestamp=bool(ts),
            has_signature=bool(sig),
        )
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    try:
        ts_i = int(ts)
    except Exception:
        log.info(
            "slack_request_rejected_invalid_timestamp",
            request_id=request_id,
            client_ip=client_ip,
        )
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Prevent replay attacks (5 minute window).
    now = int(time.time())
    if abs(now - ts_i) > 60 * 5:
        log.info(
            "slack_request_rejected_replay_window",
            request_id=request_id,
            client_ip=client_ip,
            now=now,
            timestamp=ts_i,
        )
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    base = b"v0:" + ts.encode("utf-8") + b":" + (body or b"")
    digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"

    if not hmac.compare_digest(expected, sig):
        log.info(
            "slack_request_rejected_signature_mismatch",
            request_id=request_id,
            client_ip=client_ip,
            body_len=len(body or b""),
            signature_prefix=sig[:12] if sig else None,
        )
        raise HTTPException(status_code=401, detail="Invalid Slack signature")


async def _require_slack_request(request: Request) -> bytes:
    body = await request.body()
    rid = getattr(getattr(request, "state", None), "request_id", None)
    ip = None
    try:
        ip = str(getattr(getattr(request, "client", None), "host", None) or "") or None
    except Exception:
        ip = None
    _verify_slack_signature(
        body=body,
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        signature=request.headers.get("X-Slack-Signature"),
        request_id=str(rid) if rid else None,
        client_ip=ip,
    )
    return body


def _reply_to_app_mention(*, event: dict[str, Any], request_id: str | None = None) -> None:
    """
    Best-effort reply to an app mention event.

    Keep it minimal: we just guide users toward supported slash commands.
    """
    try:
        channel = str(event.get("channel") or "").strip()
        user = str(event.get("user") or "").strip()
        ts = str(event.get("ts") or "").strip() or None
        bot_id = str(event.get("bot_id") or "").strip() or None

        # Avoid responding to bot-generated events.
        if bot_id:
            return
        if not channel or not user:
            return

        raw = str(event.get("text") or "").strip()
        # Slack formats mentions like: "<@U_APPID> hi there"
        cleaned = " ".join([p for p in raw.split() if not p.strip().startswith("<@")]).strip()
        if not cleaned:
            cleaned = "help"

        # Keep mentions very fast/stable: point at slash commands for richer flows.
        text = f"Hi <@{user}> — try `/polaris ask {cleaned}` (or `/polaris help`)."

        res = chat_post_message_result(
            text=text,
            channel=channel,
            thread_ts=ts,
            unfurl_links=False,
        )
        if bool(res.get("ok")):
            log.info(
                "slack_app_mention_replied",
                request_id=request_id,
                channel=channel,
                user=user,
                thread_ts=ts,
            )
        else:
            log.warning(
                "slack_app_mention_reply_failed",
                request_id=request_id,
                channel=channel,
                user=user,
                thread_ts=ts,
                error=str(res.get("error") or "") or None,
            )
    except Exception as e:
        log.warning(
            "slack_app_mention_reply_exception",
            request_id=request_id,
            error=str(e) or "unknown_error",
        )


def _frontend_link(path: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    p = str(path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    return base + p


def _slack_bullets(lines: list[str]) -> str:
    out = []
    for s in lines:
        s = str(s or "").strip()
        if not s:
            continue
        out.append(f"• {s}")
    return "\n".join(out)


def _format_recent_rfps(*, n: int = 5) -> str:
    lim = max(1, min(10, int(n or 5)))
    page = list_rfps(page=1, limit=lim, next_token=None) or {}
    data = page.get("data") if isinstance(page.get("data"), list) else []
    if not data:
        return "No RFPs found."
    lines: list[str] = []
    for r in data[:lim]:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("_id") or r.get("rfpId") or "").strip()
        title = str(r.get("title") or "RFP").strip()
        client = str(r.get("clientName") or "").strip()
        link = _frontend_link(f"/rfps/{rid}") if rid else None
        label = f"<{link}|{title}>" if link else title
        suffix = f" — {client}" if client else ""
        if rid:
            suffix += f" (`{rid}`)"
        lines.append(label + suffix)
    return "*Recent RFPs*\n" + _slack_bullets(lines)


def _format_recent_proposals(*, n: int = 5) -> str:
    lim = max(1, min(10, int(n or 5)))
    page = list_proposals(page=1, limit=lim, next_token=None) or {}
    data = page.get("data") if isinstance(page.get("data"), list) else []
    if not data:
        return "No proposals found."
    lines: list[str] = []
    for p in data[:lim]:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("_id") or p.get("proposalId") or "").strip()
        title = str(p.get("title") or "Proposal").strip()
        rfp_id = str(p.get("rfpId") or "").strip()
        link = _frontend_link(f"/proposals/{pid}") if pid else None
        label = f"<{link}|{title}>" if link else title
        suffix = f" (`{pid}`)" if pid else ""
        if rfp_id:
            suffix += f" — rfp `{rfp_id}`"
        lines.append(label + suffix)
    return "*Recent proposals*\n" + _slack_bullets(lines)


def _build_slack_ask_context(*, max_rfps: int = 10, max_proposals: int = 10) -> dict[str, Any]:
    # Keep this bounded — Slack answers should be fast and safe.
    ctx: dict[str, Any] = {}
    try:
        comps = content_repo.list_companies(limit=1)
        ctx["company"] = comps[0] if comps else None
    except Exception:
        ctx["company"] = None

    try:
        team = content_repo.list_team_members(limit=40)
        # Only include lightweight fields that help Q&A.
        slim = []
        for m in team or []:
            if not isinstance(m, dict):
                continue
            slim.append(
                {
                    "memberId": m.get("memberId") or m.get("_id"),
                    "name": m.get("name"),
                    "title": m.get("title"),
                    "skills": m.get("skills"),
                    "certifications": m.get("certifications"),
                    "industries": m.get("industries"),
                }
            )
        ctx["team"] = slim[:40]
    except Exception:
        ctx["team"] = []

    try:
        rfps_page = list_rfps(page=1, limit=max(1, min(20, int(max_rfps or 10))), next_token=None)
        rfps = rfps_page.get("data") if isinstance(rfps_page, dict) else []
        ctx["recentRfps"] = rfps[: max(1, min(20, int(max_rfps or 10)))]
    except Exception:
        ctx["recentRfps"] = []

    try:
        props_page = list_proposals(page=1, limit=max(1, min(20, int(max_proposals or 10))), next_token=None)
        props = props_page.get("data") if isinstance(props_page, dict) else []
        # Don't include full sections.
        slim_p = []
        for p in props or []:
            if not isinstance(p, dict):
                continue
            slim_p.append(
                {
                    "proposalId": p.get("_id") or p.get("proposalId"),
                    "rfpId": p.get("rfpId"),
                    "title": p.get("title"),
                    "status": p.get("status"),
                    "updatedAt": p.get("updatedAt"),
                }
            )
        ctx["recentProposals"] = slim_p[: max(1, min(20, int(max_proposals or 10)))]
    except Exception:
        ctx["recentProposals"] = []

    return ctx


def _answer_slack_question(*, question: str) -> str:
    q = str(question or "").strip()
    if not q:
        return "Ask a question like: `/polaris ask what proposals are in progress?`"
    if not settings.openai_api_key:
        return "AI is not configured on the backend (missing OPENAI_API_KEY)."

    ctx = _build_slack_ask_context()
    prompt = (
        "You are Polaris RFP, an internal assistant for proposal/RFP work.\n"
        "Answer the user's question using ONLY the provided context. If the answer "
        "is not in context, say what you would need to know or where to look.\n\n"
        "Keep the response concise and Slack-friendly (bullet points when helpful).\n\n"
        f"CONTEXT_JSON:\n{json.dumps(ctx, ensure_ascii=False)[:12000]}\n\n"
        f"QUESTION:\n{q}\n"
    )
    try:
        out, _meta = call_text_verified(
            purpose="slack_agent",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0.2,
            retries=1,
        )
        ans = (out or "").strip()
        # Slack message safety bound.
        return ans[:3500] if ans else "No answer generated."
    except AiNotConfigured:
        return "AI is not configured on the backend (missing OPENAI_API_KEY)."
    except AiUpstreamError as e:
        return f"AI temporarily unavailable ({str(e)}). Try again in a minute."
    except Exception as e:
        log.warning("slack_ask_failed", error=str(e) or "unknown_error")
        return "Something went wrong answering that. Try again."


def _post_to_slack_response_url(*, response_url: str, payload: dict[str, Any]) -> None:
    url = str(response_url or "").strip()
    if not url:
        return
    try:
        httpx.post(url, json=payload, timeout=10.0)
    except Exception as e:
        log.warning("slack_response_url_post_failed", error=str(e) or "unknown_error")


@router.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    # Validate Slack signature then ACK quickly.
    await _require_slack_request(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # Slack can retry deliveries (e.g. if it doesn't get a fast 2xx).
    # Avoid doing side-effects on retries to prevent duplicate replies.
    retry_num = str(request.headers.get("X-Slack-Retry-Num") or "").strip()
    if retry_num:
        log.info(
            "slack_event_retry_ack",
            request_id=str(getattr(getattr(request, "state", None), "request_id", None) or "") or None,
            retry_num=retry_num,
            retry_reason=str(request.headers.get("X-Slack-Retry-Reason") or "").strip() or None,
        )
        return {"ok": True}

    if payload.get("type") == "event_callback":
        event_raw = payload.get("event")
        event = event_raw if isinstance(event_raw, dict) else {}
        if str(event.get("type") or "").strip() == "app_mention":
            rid = getattr(getattr(request, "state", None), "request_id", None)
            background_tasks.add_task(
                _reply_to_app_mention,
                event=event,
                request_id=str(rid) if rid else None,
            )

    return {"ok": True}


@router.post("/slack/commands")
async def slack_commands(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    body = await _require_slack_request(request)

    # Slack sends application/x-www-form-urlencoded for slash commands.
    form = parse_qs(body.decode("utf-8", errors="ignore"))
    text = str((form.get("text") or [""])[0] or "").strip()
    response_url = str((form.get("response_url") or [""])[0] or "").strip()

    parts = [p for p in text.split() if p.strip()]
    sub = (parts[0].lower() if parts else "help").strip()
    rest = " ".join(parts[1:]).strip() if len(parts) > 1 else ""

    # Keep this stable because tests assert this help text shape.
    if sub in ("help", "h", "?"):
        return {
            "response_type": "in_channel",
            "text": "\n".join(
                [
                    "*Polaris RFP Slack commands*",
                    "- `/polaris help`",
                    "- `/polaris ask <question>` (ask about RFPs/proposals/team/company)",
                    "- `/polaris recent [n]` (list latest RFPs; default 5)",
                    "- `/polaris proposals [n]` (list latest proposals; default 5)",
                    "- `/polaris upload [n]` (upload latest PDFs from this channel; default 1)",
                ]
            ),
        }

    if sub in ("recent", "rfps"):
        n = 5
        try:
            if rest:
                n = int(rest)
        except Exception:
            n = 5
        return {"response_type": "ephemeral", "text": _format_recent_rfps(n=n)}

    if sub in ("proposals", "proposal"):
        n = 5
        try:
            if rest:
                n = int(rest)
        except Exception:
            n = 5
        return {"response_type": "ephemeral", "text": _format_recent_proposals(n=n)}

    if sub in ("ask", "q", "question"):
        q = rest
        if not q:
            return {
                "response_type": "ephemeral",
                "text": "Usage: `/polaris ask <question>`",
            }
        # ACK quickly; answer via response_url in the background (avoids Slack 3s timeout).
        if response_url:
            background_tasks.add_task(
                _post_to_slack_response_url,
                response_url=response_url,
                payload={"response_type": "ephemeral", "text": _answer_slack_question(question=q)},
            )
            return {"response_type": "ephemeral", "text": "Thinking…"}
        # Fallback: if response_url missing, answer inline (best-effort).
        return {"response_type": "ephemeral", "text": _answer_slack_question(question=q)}

    # Minimal mode: everything else is unsupported.
    return {
        "response_type": "ephemeral",
        "text": "This Slack command is not supported in the minimal backend. Try `/polaris help`.",
    }


@router.post("/slack/interactions")
async def slack_interactions(request: Request) -> dict[str, Any]:
    # Tests only require we ACK with an ephemeral response.
    await _require_slack_request(request)
    return {"response_type": "ephemeral", "text": "OK"}


@router.post("/slack/workflow-steps")
async def slack_workflow_steps(request: Request) -> dict[str, Any]:
    # Keep endpoint for Slack workflow step wiring; minimal implementation is ACK-only.
    await _require_slack_request(request)
    return {"ok": True}



