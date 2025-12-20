from __future__ import annotations

from typing import Any

from ...settings import settings
from ..slack_web import slack_api_get
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

