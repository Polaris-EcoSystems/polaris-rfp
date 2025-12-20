from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..observability.logging import get_logger
from ..settings import settings
from . import home as home_surface
from . import modals as modals_surface
from . import shortcuts as shortcuts_surface
from . import workflows as workflows_surface
from ..services.slack_events_repo import mark_seen as slack_event_mark_seen
from ..services.slack_rate_limiter import allow as slack_allow
from ..services.slack_reply_tools import ack_reaction
from ..services.slack_web import is_slack_configured
from ..services.slack_operator_agent import run_slack_operator_for_mention

log = get_logger("slack_dispatcher")


@dataclass(frozen=True)
class SlackDispatchResult:
    ok: bool
    # For interactive requests, returning a JSON payload to Slack is common.
    response_json: dict[str, Any] | None = None


def handle_event_callback(*, payload: dict[str, Any], background_tasks: Any) -> SlackDispatchResult:
    """
    Handle Slack event_callback payloads.
    This must be fast; do work asynchronously via background_tasks.
    """
    # Deduplicate by event_id to avoid Slack retry storms.
    ev_id = str(payload.get("event_id") or "").strip()
    if ev_id and not slack_event_mark_seen(event_id=ev_id, ttl_seconds=600):
        return SlackDispatchResult(ok=True, response_json={"ok": True})

    ev = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    ev_type = str(ev.get("type") or "").strip()

    # App Home surface
    if ev_type == "app_home_opened":
        background_tasks.add_task(home_surface.on_app_home_opened, payload=payload)
        return SlackDispatchResult(ok=True, response_json={"ok": True})

    # Thread/operator surface
    if ev_type == "app_mention" and is_slack_configured() and bool(settings.slack_agent_enabled):
        channel = str(ev.get("channel") or "").strip() or None
        user_id = str(ev.get("user") or "").strip() or None
        thread_ts = str(ev.get("thread_ts") or ev.get("ts") or "").strip() or None
        text = str(ev.get("text") or "").strip()
        text = re.sub(r"<@[^>]+>", "", text).strip()
        if not text:
            text = "help"

        # Rate limit by (user, channel) to avoid abuse.
        if user_id and not slack_allow(key=f"slack_agent_user:{user_id}", limit=8, per_seconds=60):
            return SlackDispatchResult(ok=True, response_json={"ok": True})
        if channel and not slack_allow(key=f"slack_agent_channel:{channel}", limit=25, per_seconds=60):
            return SlackDispatchResult(ok=True, response_json={"ok": True})

        if channel and thread_ts:
            background_tasks.add_task(ack_reaction, channel=channel, timestamp=thread_ts, emoji="eyes")

        # Operator agent runs in background and posts its own replies.
        background_tasks.add_task(
            run_slack_operator_for_mention,
            question=text,
            channel_id=channel or "",
            thread_ts=thread_ts or "",
            user_id=user_id,
            correlation_id=ev_id or thread_ts,
            max_steps=8,
        )
        return SlackDispatchResult(ok=True, response_json={"ok": True})

    # DM concierge (optional; keep off by default until we finalize UX)
    if ev_type == "message" and str(ev.get("channel_type") or "").strip() == "im":
        if bool(getattr(settings, "slack_dm_enabled", False)):
            background_tasks.add_task(workflows_surface.on_dm_message, payload=payload)
        return SlackDispatchResult(ok=True, response_json={"ok": True})

    return SlackDispatchResult(ok=True, response_json={"ok": True})


def handle_interactivity(*, payload: dict[str, Any], background_tasks: Any) -> SlackDispatchResult:
    """
    Handle Slack interactivity payloads (block_actions, shortcuts, view_submission, etc).
    """
    ptype = str(payload.get("type") or "").strip()

    # Shortcuts (message / global) arrive here.
    if ptype in ("message_action", "shortcut"):
        res = shortcuts_surface.handle_shortcut(payload=payload, background_tasks=background_tasks)
        return SlackDispatchResult(ok=True, response_json=res)

    # Modal submission/close
    if ptype in ("view_submission", "view_closed"):
        res = modals_surface.handle_view(payload=payload, background_tasks=background_tasks)
        return SlackDispatchResult(ok=True, response_json=res)

    # Block actions (buttons/selects)
    if ptype == "block_actions":
        res = modals_surface.handle_block_actions(payload=payload, background_tasks=background_tasks)
        return SlackDispatchResult(ok=True, response_json=res)

    return SlackDispatchResult(ok=True, response_json={"response_type": "ephemeral", "text": "Got it."})

