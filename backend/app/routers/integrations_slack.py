from __future__ import annotations

import json
import hmac
import hashlib
import time
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request

from ..observability.logging import get_logger
from ..settings import settings
from ..services.proposals_repo import list_proposals
from ..services.rfp_upload_jobs_repo import get_job
from ..services.rfps_repo import get_rfp_by_id, list_rfps
from ..services.slack_secrets import get_secret_str
from ..services.slack_web import is_slack_configured, post_message


router = APIRouter(tags=["integrations"])
log = get_logger("integrations_slack")

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


def _upload_url() -> str:
    return str(settings.frontend_base_url or "").rstrip("/") + "/rfps/upload"


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


@router.post("/slack/events")
async def slack_events(request: Request):
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
        ev = payload.get("event") or {}
        ev_type = str(ev.get("type") or "").strip()

        # Minimal starter: respond to app mentions with a help hint.
        if ev_type == "app_mention" and is_slack_configured():
            channel = str(ev.get("channel") or "").strip() or None
            try:
                # Post into the channel (threaded if possible).
                # Slack threading uses "thread_ts" in payload; chat.postMessage supports it,
                # but we keep it simple: include a plain response for now.
                post_message(
                    text="Try `/polaris help` to see available commands.",
                    channel=channel,
                )
            except Exception:
                pass

        log.info("slack_event_received", event_type=ev_type or None)
        return {"ok": True}

    return {"ok": True}


@router.post("/slack/commands")
async def slack_commands(request: Request):
    body = await _require_slack_request(request)

    # Slack sends application/x-www-form-urlencoded for slash commands.
    form = parse_qs(body.decode("utf-8", errors="ignore"))
    text = str((form.get("text") or [""])[0] or "").strip()

    # Common fields (kept for future use)
    user_id = str((form.get("user_id") or [""])[0] or "").strip() or None
    channel_id = str((form.get("channel_id") or [""])[0] or "").strip() or None

    parts = [p for p in text.split() if p.strip()]
    sub = (parts[0].lower() if parts else "help").strip()
    args = parts[1:]

    if sub in ("help", "h", "?"):
        return {
            "response_type": "ephemeral",
            "text": "\n".join(
                [
                    "*Polaris RFP Slack commands*",
                    "- `/polaris help`",
                    "- `/polaris recent [n]` (list latest RFPs)",
                    "- `/polaris search <keywords>` (search title/client/type)",
                    "- `/polaris rfp <rfpId>` (returns a link)",
                    "- `/polaris open <keywords>` (first search result)",
                    "- `/polaris job <jobId>` (RFP upload job status)",
                ]
            ),
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
            return {"response_type": "ephemeral", "text": "No RFPs found."}
        lines = [f"*Latest {min(n, len(items))} RFPs*"] + [_format_rfp_line(r) for r in items[:n]]
        return {"response_type": "ephemeral", "text": "\n".join(lines)}

    if sub in ("search", "find"):
        if not args:
            return {"response_type": "ephemeral", "text": "Usage: `/polaris search <keywords>`"}
        q = " ".join(args).strip()
        hits = _search_rfps(q, max_results=10)
        if not hits:
            return {"response_type": "ephemeral", "text": f"No matches for: `{q}`"}
        lines = [f"*Search results for:* `{q}`"] + [_format_rfp_line(r) for r in hits]
        return {"response_type": "ephemeral", "text": "\n".join(lines)}

    if sub == "open":
        if not args:
            return {"response_type": "ephemeral", "text": "Usage: `/polaris open <keywords>`"}
        q = " ".join(args).strip()
        hits = _search_rfps(q, max_results=1)
        if not hits:
            return {"response_type": "ephemeral", "text": f"No matches for: `{q}`"}
        r = hits[0]
        rid = str(r.get("_id") or "").strip()
        if not rid:
            return {"response_type": "ephemeral", "text": "Match found but missing rfpId."}
        title = str(r.get("title") or "RFP").strip()
        client = str(r.get("clientName") or "").strip()
        extra = f" ({client})" if client else ""
        return {"response_type": "ephemeral", "text": f"<{_rfp_url(rid)}|{title}>{extra}"}

    if sub == "rfp":
        if not args:
            return {"response_type": "ephemeral", "text": "Usage: `/polaris rfp <rfpId>`"}
        rfp_id = str(args[0]).strip()
        rfp = get_rfp_by_id(rfp_id)
        if not rfp:
            return {"response_type": "ephemeral", "text": f"RFP not found: `{rfp_id}`"}
        url = _rfp_url(rfp_id)
        title = str(rfp.get("title") or "RFP").strip()
        client = str(rfp.get("clientName") or "").strip()
        extra = f" ({client})" if client else ""
        return {"response_type": "ephemeral", "text": f"<{url}|{title}>{extra}"}

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

    # Minimal, safe default: acknowledge and provide a hint.
    # We can expand this to real actions (e.g., "summarize", "move stage", "mark checklist")
    # once buttons are added to Slack messages.
    log.info(
        "slack_interaction_received",
        interaction_type=ptype,
        user_id=user_id,
        channel_id=channel_id,
    )

    return {
        "response_type": "ephemeral",
        "text": "Got it. (Interactive actions are wired up; next we’ll add buttons/menus to messages.)",
    }
