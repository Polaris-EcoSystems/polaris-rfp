from __future__ import annotations

from typing import Any

import httpx

from ..observability.logging import get_logger
from ..settings import settings
from .slack_secrets import get_secret_str


log = get_logger("slack")


def get_bot_token() -> str | None:
    """
    Resolve the Slack bot token from settings or Secrets Manager.

    Note: `is_slack_configured()` requires *both* token and a default channel,
    but some operations (like fetching files) only need the token.
    """
    if not bool(settings.slack_enabled):
        return None
    return (
        (str(settings.slack_bot_token or "").strip() or None)
        or get_secret_str("SLACK_ACCESS_TOKEN")
        or get_secret_str("SLACK_BOT_TOKEN")
    )


def is_slack_configured() -> bool:
    """
    Slack is considered "configured" if the integration is enabled and we have a bot token.

    Note: a default channel is NOT required here because many call sites pass
    an explicit channel (e.g. rfp-machine notifications).
    """
    if not bool(settings.slack_enabled):
        return False
    return bool(get_bot_token())


def slack_api_get(*, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Call a Slack Web API GET endpoint, returning its decoded JSON payload.
    """
    token = get_bot_token()
    if not token:
        return {"ok": False, "error": "slack_not_configured"}

    m = str(method or "").strip().lstrip("/")
    if not m:
        return {"ok": False, "error": "invalid_method"}

    try:
        resp = httpx.get(
            f"https://slack.com/api/{m}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=20.0,
        )
        data = resp.json() if resp.content else {}
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid_response"}
        return data  # includes ok/error
    except Exception as e:
        log.warning("slack_api_get_exception", method=m, error=str(e) or "unknown_error")
        return {"ok": False, "error": "request_failed"}


def list_recent_channel_pdfs(*, channel_id: str, max_files: int = 1, max_messages: int = 50) -> list[dict[str, Any]]:
    """
    Best-effort: scan recent channel history and return up to N PDF file objects.

    Requires Slack scopes:
      - conversations.history (public channels) OR groups.history (private channels)
      - files:read
    """
    ch = str(channel_id or "").strip()
    if not ch:
        return []

    want = max(1, min(5, int(max_files or 1)))
    max_msgs = max(5, min(200, int(max_messages or 50)))

    resp = slack_api_get(method="conversations.history", params={"channel": ch, "limit": max_msgs})
    if not bool(resp.get("ok")):
        return []

    msgs = resp.get("messages")
    messages = msgs if isinstance(msgs, list) else []

    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        files = m.get("files")
        fs = files if isinstance(files, list) else []
        for f in fs:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name") or "").strip()
            mimetype = str(f.get("mimetype") or "").strip().lower()
            filetype = str(f.get("filetype") or "").strip().lower()
            is_pdf = (
                mimetype == "application/pdf"
                or filetype == "pdf"
                or name.lower().endswith(".pdf")
            )
            if not is_pdf:
                continue
            out.append(f)
            if len(out) >= want:
                return out
    return out


def download_slack_file(*, url: str, max_bytes: int = 60 * 1024 * 1024) -> bytes:
    """
    Download a Slack-hosted file using the bot token.
    """
    token = get_bot_token()
    if not token:
        raise RuntimeError("Slack integration not configured")

    u = str(url or "").strip()
    if not u:
        raise RuntimeError("Missing file URL")

    # Prefer streaming to enforce max_bytes.
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        with client.stream(
            "GET",
            u,
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            r.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in r.iter_bytes():
                if not chunk:
                    continue
                total += len(chunk)
                if total > int(max_bytes):
                    raise RuntimeError("File too large")
                chunks.append(chunk)
            return b"".join(chunks)


def post_message(
    *,
    text: str,
    channel: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
    unfurl_links: bool = False,
) -> bool:
    """
    Best-effort Slack message post.

    Returns:
      True if Slack accepted the message, else False.
    """
    token = get_bot_token() or ""
    ch = (
        (str(channel or "").strip() or None)
        or (str(settings.slack_default_channel or "").strip() or None)
        or get_secret_str("SLACK_DEFAULT_CHANNEL")
    )
    if not bool(settings.slack_enabled) or not token or not ch:
        return False

    payload: dict[str, Any] = {
        "channel": ch,
        "text": str(text or "").strip() or "(no text)",
        "unfurl_links": bool(unfurl_links),
        "unfurl_media": bool(unfurl_links),
    }
    if blocks:
        payload["blocks"] = blocks

    def _send(p: dict[str, Any]) -> tuple[bool, str | None, int]:
        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json=p,
            timeout=10.0,
        )
        data = resp.json() if resp.content else {}
        ok = bool(data.get("ok"))
        err = str(data.get("error") or "").strip() or None
        return ok, err, int(resp.status_code)

    try:
        ok, err, status = _send(payload)
        if ok:
            return True

        # Common misconfig: channel name without '#'. Try once with '#'.
        if err in ("channel_not_found", "not_in_channel") and isinstance(ch, str):
            if not ch.startswith(("#", "C", "G")):
                payload2 = dict(payload)
                payload2["channel"] = "#" + ch
                ok2, err2, status2 = _send(payload2)
                if ok2:
                    return True
                err = err2 or err
                status = status2 or status

        log.warning(
            "slack_post_message_failed",
            status_code=status,
            error=err,
            channel=str(ch) if ch else None,
        )
        return False
    except Exception as e:
        log.warning(
            "slack_post_message_exception",
            error=str(e) or "unknown_error",
            channel=str(ch) if ch else None,
        )
        return False

