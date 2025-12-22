"""
Temporal event memory management and pattern detection.

Handles time-indexed events, deadlines, and temporal pattern detection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .agent_memory_db import MemoryType, create_memory, list_memories_by_type
from .agent_memory_keywords import extract_keywords
from ...ai.context import clip_text
from ...observability.logging import get_logger

log = get_logger("agent_memory_temporal")


def add_temporal_event_memory(
    *,
    scope_id: str,
    content: str,
    event_at: str,  # ISO timestamp
    event_type: str | None = None,
    rfp_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    # Provenance fields
    cognito_user_id: str | None = None,
    slack_user_id: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    slack_team_id: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """
    Add a temporal event memory (deadline, milestone, scheduled event).
    
    Args:
        scope_id: Scope identifier (USER#{sub}, RFP#{id}, etc.)
        content: Description of the event
        event_at: ISO timestamp when the event occurs/occurred
        event_type: Type of event (e.g., "deadline", "milestone", "meeting", "review")
        rfp_id: RFP identifier if related to an RFP
        metadata: Additional metadata
        cognito_user_id: Cognito user identifier
        slack_user_id: Slack user ID
        slack_channel_id: Slack channel ID
        slack_thread_ts: Slack thread timestamp
        slack_team_id: Slack team ID
        source: Source system
    
    Returns:
        Created memory dict
    """
    if not scope_id or not content or not event_at:
        raise ValueError("scope_id, content, and event_at are required")
    
    # Extract keywords
    keywords = extract_keywords(content)
    if event_type:
        keywords.append(event_type)
    
    # Build tags
    tags = ["temporal", "event"]
    if event_type:
        tags.append(event_type)
    
    # Parse event timestamp to determine if past/future
    try:
        event_dt = datetime.fromisoformat(event_at.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        if event_dt > now_dt:
            tags.append("upcoming")
        else:
            tags.append("past")
    except Exception:
        pass
    
    # Build metadata
    final_metadata: dict[str, Any] = {
        "eventAt": event_at,
        "eventType": event_type,
    }
    if metadata:
        final_metadata.update(metadata)
    
    summary = clip_text(content, max_chars=500)
    
    memory = create_memory(
        memory_type=MemoryType.TEMPORAL_EVENT,
        scope_id=scope_id,
        content=content,
        tags=tags,
        keywords=keywords,
        metadata=final_metadata,
        summary=summary,
        cognito_user_id=cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        slack_team_id=slack_team_id,
        rfp_id=rfp_id,
        source=source or "temporal_event",
    )
    
    log.info(
        "temporal_event_memory_created",
        memory_id=memory.get("memoryId"),
        event_at=event_at,
        event_type=event_type,
        scope_id=scope_id,
    )
    
    return memory


def get_upcoming_events(
    *,
    scope_id: str | None = None,
    rfp_id: str | None = None,
    user_sub: str | None = None,
    days_ahead: int = 30,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Get upcoming temporal events within a time window.
    
    Args:
        scope_id: Optional scope identifier
        rfp_id: Optional RFP ID
        user_sub: Optional user identifier
        days_ahead: Number of days to look ahead
        limit: Maximum number of events to return
    
    Returns:
        List of upcoming event memories
    """
    # Determine scope
    if not scope_id:
        if rfp_id:
            scope_id = f"RFP#{rfp_id}"
        elif user_sub:
            scope_id = f"USER#{user_sub}"
    
    if not scope_id:
        return []
    
    # Get all TEMPORAL_EVENT memories for scope
    memories, _ = list_memories_by_type(
        memory_type=MemoryType.TEMPORAL_EVENT,
        scope_id=scope_id,
        limit=limit * 2,
    )
    
    # Filter to upcoming events
    from datetime import timedelta
    
    now_dt = datetime.now(timezone.utc)
    cutoff_dt = now_dt.replace(hour=23, minute=59, second=59) + timedelta(days=days_ahead)
    
    upcoming: list[dict[str, Any]] = []
    for memory in memories:
        metadata = memory.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        
        event_at_str = metadata.get("eventAt")
        if not event_at_str:
            continue
        
        try:
            event_dt = datetime.fromisoformat(event_at_str.replace("Z", "+00:00"))
            if now_dt <= event_dt <= cutoff_dt:
                upcoming.append(memory)
                if len(upcoming) >= limit:
                    break
        except Exception:
            continue
    
    # Sort by event time
    upcoming.sort(key=lambda m: m.get("metadata", {}).get("eventAt", ""))
    
    return upcoming


def detect_temporal_patterns(
    *,
    scope_id: str,
    memory_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Detect temporal patterns in memories (e.g., weekly standups, monthly reviews).
    
    Args:
        scope_id: Scope identifier to analyze
        memory_type: Optional memory type to analyze
        limit: Maximum number of memories to analyze
    
    Returns:
        List of detected patterns
    """
    # This would analyze memory timestamps to find recurring patterns
    # For now, return empty list - full implementation would do temporal analysis
    return []
