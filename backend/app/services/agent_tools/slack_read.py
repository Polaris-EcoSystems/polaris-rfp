from __future__ import annotations

from typing import Any

from ...settings import settings
from ..slack_web import slack_api_get, slack_api_post
from .allowlist import parse_csv, uniq, is_allowed_exact


def _allowed_channels() -> list[str]:
    return uniq(parse_csv(settings.agent_allowed_slack_channels))


def _require_allowed_channel(channel: str) -> str:
    ch = str(channel or "").strip()
    if not ch:
        raise ValueError("missing_channel")
    allowed = _allowed_channels()
    # If configured, enforce strict allowlist; otherwise allow (Slack token scopes still apply).
    if allowed and not is_allowed_exact(ch, allowed):
        raise ValueError("slack_channel_not_allowed")
    return ch


def list_recent_messages(*, channel: str, limit: int = 15) -> dict[str, Any]:
    ch = _require_allowed_channel(channel)
    lim = max(1, min(25, int(limit or 15)))
    resp = slack_api_get(method="conversations.history", params={"channel": ch, "limit": lim})
    msgs = resp.get("messages") if isinstance(resp, dict) else None
    out: list[dict[str, Any]] = []
    for m in (msgs if isinstance(msgs, list) else [])[:lim]:
        if not isinstance(m, dict):
            continue
        txt = str(m.get("text") or "")
        out.append(
            {
                "ts": m.get("ts"),
                "user": m.get("user"),
                "text": (txt[:2000] + "…") if len(txt) > 2000 else txt,
            }
        )
    return {"ok": True, "channel": ch, "messages": out}


def get_thread(*, channel: str, thread_ts: str, limit: int = 25) -> dict[str, Any]:
    ch = _require_allowed_channel(channel)
    ts = str(thread_ts or "").strip()
    if not ts:
        raise ValueError("missing_thread_ts")
    lim = max(1, min(50, int(limit or 25)))
    resp = slack_api_get(method="conversations.replies", params={"channel": ch, "ts": ts, "limit": lim})
    msgs = resp.get("messages") if isinstance(resp, dict) else None
    out: list[dict[str, Any]] = []
    for m in (msgs if isinstance(msgs, list) else [])[:lim]:
        if not isinstance(m, dict):
            continue
        txt = str(m.get("text") or "")
        out.append(
            {
                "ts": m.get("ts"),
                "user": m.get("user"),
                "text": (txt[:2000] + "…") if len(txt) > 2000 else txt,
            }
        )
    return {"ok": True, "channel": ch, "threadTs": ts, "messages": out}


def create_canvas(*, channel: str, title: str, markdown: str) -> dict[str, Any]:
    """
    Create a Slack canvas in a channel.
    
    Args:
        channel: Channel ID where the canvas should be created
        title: Title for the canvas
        markdown: Markdown content for the canvas (supports Slack canvas markdown format)
    
    Returns:
        dict with ok status and canvas_id if successful
    """
    ch = _require_allowed_channel(channel)
    t = str(title or "").strip()
    if not t:
        raise ValueError("missing_title")
    md = str(markdown or "").strip()
    if not md:
        raise ValueError("missing_markdown")
    
    payload: dict[str, Any] = {
        "channel_id": ch,
        "title": t,
        "document_content": {
            "type": "markdown",
            "markdown": md,
        },
    }
    
    resp = slack_api_post(method="conversations.canvases.create", json=payload)
    
    if resp.get("ok"):
        return {
            "ok": True,
            "channel": ch,
            "canvas_id": resp.get("canvas_id"),
            "title": t,
        }
    else:
        error = resp.get("error") or "unknown_error"
        return {"ok": False, "error": error, "channel": ch}

