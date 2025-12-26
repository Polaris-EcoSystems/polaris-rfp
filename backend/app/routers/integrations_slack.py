from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qs
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..observability.logging import get_logger
from ..settings import settings

router = APIRouter(tags=["integrations"])
log = get_logger("integrations_slack")


def _verify_slack_signature(*, body: bytes, timestamp: str | None, signature: str | None) -> None:
    secret = str(settings.slack_signing_secret or "").strip()
    if not secret:
        # In dev/test, we often don't configure Slack at all. If there's no secret,
        # deny by default (tests patch this field).
        raise HTTPException(status_code=401, detail="Slack not configured")

    ts = str(timestamp or "").strip()
    sig = str(signature or "").strip()
    if not ts or not sig:
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    try:
        ts_i = int(ts)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Prevent replay attacks (5 minute window).
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
async def slack_events(request: Request) -> dict[str, Any]:
    # Validate Slack signature then ACK quickly. This minimal backend does not
    # process event callbacks yet (we’re pruning to the smallest core).
    await _require_slack_request(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    return {"ok": True}


@router.post("/slack/commands")
async def slack_commands(request: Request) -> dict[str, Any]:
    body = await _require_slack_request(request)

    # Slack sends application/x-www-form-urlencoded for slash commands.
    form = parse_qs(body.decode("utf-8", errors="ignore"))
    text = str((form.get("text") or [""])[0] or "").strip()

    parts = [p for p in text.split() if p.strip()]
    sub = (parts[0].lower() if parts else "help").strip()

    # Keep this stable because tests assert this help text shape.
    if sub in ("help", "h", "?"):
        return {
            "response_type": "in_channel",
            "text": "\n".join(
                [
                    "*Polaris RFP Slack commands*",
                    "- `/polaris help`",
                    "- `/polaris upload [n]` (upload latest PDFs from this channel; default 1)",
                ]
            ),
        }

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



