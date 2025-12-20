from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger
from .agent_events_repo import append_event
from .agent_journal_repo import append_entry
from .opportunity_state_repo import patch_state
from .slack_web import chat_post_message_result, slack_api_post


log = get_logger("slack_reply_tools")


def _normalize_emoji(name: str) -> str:
    s = str(name or "").strip()
    if not s:
        return ""
    # Slack API expects name without colons.
    if s.startswith(":") and s.endswith(":") and len(s) > 2:
        s = s[1:-1]
    return s.strip()


def ack_reaction(*, channel: str, timestamp: str, emoji: str = "eyes") -> dict[str, Any]:
    """
    Immediate ACK for Slack events (reaction).
    """
    ch = str(channel or "").strip()
    ts = str(timestamp or "").strip()
    em = _normalize_emoji(emoji)
    if not ch or not ts or not em:
        return {"ok": False, "error": "missing_params"}
    return slack_api_post(method="reactions.add", json={"channel": ch, "timestamp": ts, "name": em})


def post_summary(
    *,
    rfp_id: str,
    channel: str,
    thread_ts: str | None,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Post a summary to Slack and enforce the “state before talk” rule by:
    - patching OpportunityState.comms
    - appending Journal + Event entries
    """
    rid = str(rfp_id or "").strip()
    ch = str(channel or "").strip()
    if not rid or not ch:
        return {"ok": False, "error": "missing_rfp_or_channel"}

    now = None
    try:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        now = None

    # State update first (durable artifact).
    try:
        patch_state(
            rfp_id=rid,
            patch={"comms": {"lastSlackSummaryAt": now}},
            updated_by_user_sub=None,
            create_snapshot=False,
        )
    except Exception:
        # Never block Slack post on state write.
        pass

    # Journal narrative (best-effort).
    try:
        append_entry(
            rfp_id=rid,
            topics=["slack", "summary"],
            agent_intent="post_summary",
            what_changed="Posted a Slack summary",
            sources=[],
            meta={"channel": ch, "threadTs": thread_ts},
        )
    except Exception:
        pass

    # Append event log (best-effort).
    try:
        append_event(
            rfp_id=rid,
            type="slack_post_summary",
            tool="slack_post_summary",
            payload={"channel": ch, "threadTs": thread_ts, "textLen": len(str(text or ""))},
            correlation_id=correlation_id,
        )
    except Exception:
        pass

    return chat_post_message_result(
        text=str(text or "").strip() or "(no text)",
        channel=ch,
        blocks=blocks,
        unfurl_links=False,
        thread_ts=str(thread_ts).strip() if thread_ts else None,
    )


def ask_clarifying_question(
    *,
    rfp_id: str,
    channel: str,
    thread_ts: str | None,
    question: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "error": "missing_question"}
    return post_summary(
        rfp_id=rfp_id,
        channel=channel,
        thread_ts=thread_ts,
        text=q,
        blocks=None,
        correlation_id=correlation_id,
    )

