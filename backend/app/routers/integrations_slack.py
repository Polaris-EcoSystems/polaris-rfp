from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qs
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..observability.logging import get_logger
from ..settings import settings
from ..infrastructure.integrations.slack.slack_secrets import get_secret_str

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



