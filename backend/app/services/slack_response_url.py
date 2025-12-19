from __future__ import annotations

from typing import Any

import httpx

from ..observability.logging import get_logger


log = get_logger("slack_response_url")


def respond(
    *,
    response_url: str,
    text: str,
    response_type: str = "ephemeral",
    replace_original: bool | None = None,
    delete_original: bool | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Post a message to Slack via response_url (slash commands + interactivity).
    This does NOT require a bot token.
    """
    url = str(response_url or "").strip()
    if not url:
        return False

    payload: dict[str, Any] = {
        "response_type": response_type,
        "text": str(text or "").strip() or "(no text)",
    }
    if blocks:
        payload["blocks"] = blocks
    if replace_original is not None:
        payload["replace_original"] = bool(replace_original)
    if delete_original is not None:
        payload["delete_original"] = bool(delete_original)

    try:
        r = httpx.post(url, json=payload, timeout=10.0)
        if r.status_code >= 400:
            log.warning(
                "slack_response_url_failed",
                status_code=int(r.status_code),
            )
            return False
        return True
    except Exception as e:
        log.warning("slack_response_url_exception", error=str(e) or "unknown_error")
        return False

