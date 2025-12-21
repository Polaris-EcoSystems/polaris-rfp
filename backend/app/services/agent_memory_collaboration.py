"""
Collaboration pattern detection and COLLABORATION_CONTEXT memory management.

Tracks team interaction patterns and successful collaboration sequences.
"""

from __future__ import annotations

from typing import Any

from .agent_memory_db import MemoryType, create_memory
from .agent_memory_keywords import extract_keywords
from ..ai.context import clip_text
from ..observability.logging import get_logger

log = get_logger("agent_memory_collaboration")


def add_collaboration_context_memory(
    *,
    participant_user_ids: list[str],
    content: str,
    collaboration_type: str | None = None,
    success: bool = True,
    context: dict[str, Any] | None = None,
    scope_id: str | None = None,
    # Provenance fields
    cognito_user_id: str | None = None,
    slack_user_id: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    slack_team_id: str | None = None,
    rfp_id: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """
    Add a collaboration context memory tracking team interaction patterns.
    
    Args:
        participant_user_ids: List of user IDs who participated in the collaboration
        content: Description of the collaboration
        collaboration_type: Type of collaboration (e.g., "code_review", "design_session", "decision_making")
        success: Whether the collaboration was successful
        context: Additional context about the collaboration
        scope_id: Optional scope override (defaults to TENANT or multi-USER scope)
        cognito_user_id: Cognito user identifier
        slack_user_id: Slack user ID
        slack_channel_id: Slack channel ID
        slack_thread_ts: Slack thread timestamp
        slack_team_id: Slack team ID
        rfp_id: RFP identifier if related to an RFP
        source: Source system
    
    Returns:
        Created memory dict
    """
    if not participant_user_ids or not content:
        raise ValueError("participant_user_ids and content are required")
    
    # Determine scope: use TENANT if available, or create composite scope
    if not scope_id:
        # Try to determine tenant from first participant
        # For now, use a multi-user scope format
        participant_str = "_".join(sorted(participant_user_ids[:5]))[:100]  # Limit length
        scope_id = f"COLLAB#{participant_str}"  # Collaboration-specific scope
        # Could also use TENANT scope if tenant_id is available in context
    
    # Extract keywords
    keywords = extract_keywords(content)
    keywords.extend([f"participant_{uid}" for uid in participant_user_ids[:10]])  # Limit
    
    # Build tags
    tags = ["collaboration"]
    if collaboration_type:
        tags.append(collaboration_type)
    if success:
        tags.append("successful")
    else:
        tags.append("unsuccessful")
    
    # Build metadata
    metadata: dict[str, Any] = {
        "participantUserIds": participant_user_ids,
        "collaborationType": collaboration_type,
        "success": success,
    }
    if context:
        metadata.update(context)
    
    summary = clip_text(content, max_chars=500)
    
    memory = create_memory(
        memory_type=MemoryType.COLLABORATION_CONTEXT,
        scope_id=scope_id,
        content=content,
        tags=tags,
        keywords=keywords,
        metadata=metadata,
        summary=summary,
        cognito_user_id=cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        slack_team_id=slack_team_id,
        rfp_id=rfp_id,
        source=source or "collaboration_detection",
    )
    
    log.info(
        "collaboration_memory_created",
        memory_id=memory.get("memoryId"),
        participant_count=len(participant_user_ids),
        collaboration_type=collaboration_type,
        success=success,
    )
    
    return memory


def detect_collaboration_patterns(
    *,
    user_ids: list[str],
    rfp_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Detect collaboration patterns from existing memories.
    
    Looks for repeated successful collaborations between users.
    
    Args:
        user_ids: List of user IDs to analyze
        rfp_id: Optional RFP ID to scope the analysis
        limit: Maximum number of patterns to return
    
    Returns:
        List of detected collaboration patterns
    """
    # This would query COLLABORATION_CONTEXT memories involving these users
    # and identify patterns (e.g., "User A and User B frequently collaborate on design tasks")
    # For now, return empty list - full implementation would query memories
    return []
