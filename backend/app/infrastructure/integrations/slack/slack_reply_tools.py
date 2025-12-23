from __future__ import annotations

from typing import Any

from ....observability.logging import get_logger
from ....repositories.agent.events_repo import append_event
from ....repositories.rfp.agent_journal_repo import append_entry
from ....repositories.rfp.opportunity_state_repo import patch_state
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


def post_compact_summary(
    *,
    rfp_id: str | None,
    channel: str,
    thread_ts: str | None,
    title: str,
    items: list[dict[str, Any]] | None = None,
    links: list[dict[str, str]] | None = None,
    status: str = "success",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Post a compact, structured summary using Slack blocks for reduced clutter.
    
    Args:
        rfp_id: Optional RFP ID
        channel: Slack channel ID
        thread_ts: Thread timestamp
        title: Summary title
        items: List of items to display (each with 'text' and optional 'emoji')
        links: List of links to display (each with 'text' and 'url')
        status: Status indicator ('success', 'warning', 'error', 'info')
        correlation_id: Optional correlation ID
    """
    ch = str(channel or "").strip()
    if not ch:
        return {"ok": False, "error": "missing_channel"}
    
    # Build blocks
    blocks: list[dict[str, Any]] = []
    
    # Status emoji
    status_emoji = {
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "info": "ℹ️",
    }.get(status, "ℹ️")
    
    # Header
    header_text = f"{status_emoji} {title}"
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": header_text,
            "emoji": True,
        },
    })
    
    # Items section
    if items:
        items_text = "\n".join([
            f"{item.get('emoji', '•')} {item.get('text', '')}"
            for item in items[:10]  # Limit to 10 items
        ])
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": items_text,
            },
        })
    
    # Links section
    if links:
        links_text = "\n".join([
            f"<{link.get('url', '')}|{link.get('text', 'Link')}>"
            for link in links[:5]  # Limit to 5 links
        ])
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": links_text,
            },
        })
    
    # Fallback text
    fallback_text = title
    if items:
        fallback_text += "\n" + "\n".join([item.get("text", "") for item in items[:5]])
    if links:
        fallback_text += "\n" + "\n".join([f"{link.get('text', 'Link')}: {link.get('url', '')}" for link in links[:3]])
    
    # Post summary if RFP ID provided, otherwise just post message
    if rfp_id:
        return post_summary(
            rfp_id=rfp_id,
            channel=ch,
            thread_ts=thread_ts,
            text=fallback_text,
            blocks=blocks,
            correlation_id=correlation_id,
        )
    else:
        return chat_post_message_result(
            text=fallback_text,
            channel=ch,
            blocks=blocks,
            unfurl_links=False,
            thread_ts=str(thread_ts).strip() if thread_ts else None,
        )


def post_batched_update(
    *,
    rfp_id: str | None,
    channel: str,
    thread_ts: str | None,
    operation: str,
    count: int,
    details: list[str] | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Post a batched update message for multiple operations.
    
    Example: "Completed 3 file uploads to Financial folder"
    """
    ch = str(channel or "").strip()
    if not ch:
        return {"ok": False, "error": "missing_channel"}
    
    text = f"✅ {operation}"
    if count > 0:
        text += f" ({count} item{'s' if count != 1 else ''})"
    
    if details and len(details) > 0:
        # Show first few details
        details_text = "\n".join(details[:5])
        if len(details) > 5:
            details_text += f"\n... and {len(details) - 5} more"
        text += f"\n\n{details_text}"
    
    if rfp_id:
        return post_summary(
            rfp_id=rfp_id,
            channel=ch,
            thread_ts=thread_ts,
            text=text,
            blocks=None,
            correlation_id=correlation_id,
        )
    else:
        return chat_post_message_result(
            text=text,
            channel=ch,
            blocks=None,
            unfurl_links=False,
            thread_ts=str(thread_ts).strip() if thread_ts else None,
        )

