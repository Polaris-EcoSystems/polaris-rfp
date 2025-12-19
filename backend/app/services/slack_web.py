from __future__ import annotations

from typing import Any

import httpx

from ..observability.logging import get_logger
from ..settings import settings
from .slack_secrets import get_secret_str


log = get_logger("slack")


def is_slack_configured() -> bool:
    if not bool(settings.slack_enabled):
        return False
    token = (
        (str(settings.slack_bot_token or "").strip() or None)
        or get_secret_str("SLACK_ACCESS_TOKEN")
        or get_secret_str("SLACK_BOT_TOKEN")
    )
    channel = (
        (str(settings.slack_default_channel or "").strip() or None)
        or get_secret_str("SLACK_DEFAULT_CHANNEL")
    )
    if not token or not channel:
        return False
    return True


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
    if not is_slack_configured():
        return False

    token = (
        (str(settings.slack_bot_token or "").strip() or None)
        or get_secret_str("SLACK_ACCESS_TOKEN")
        or get_secret_str("SLACK_BOT_TOKEN")
        or ""
    )
    ch = (
        (str(channel or settings.slack_default_channel or "").strip() or None)
        or get_secret_str("SLACK_DEFAULT_CHANNEL")
        or ""
    )
    if not token or not ch:
        return False

    payload: dict[str, Any] = {
        "channel": ch,
        "text": str(text or "").strip() or "(no text)",
        "unfurl_links": bool(unfurl_links),
        "unfurl_media": bool(unfurl_links),
    }
    if blocks:
        payload["blocks"] = blocks

    try:
        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=10.0,
        )
        data = resp.json() if resp.content else {}
        ok = bool(data.get("ok"))
        if not ok:
            log.warning(
                "slack_post_message_failed",
                status_code=int(resp.status_code),
                error=str(data.get("error") or "") or None,
            )
        return ok
    except Exception as e:
        log.warning("slack_post_message_exception", error=str(e) or "unknown_error")
        return False

