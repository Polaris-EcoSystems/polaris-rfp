from __future__ import annotations

from typing import Any

from .agent_memory_db import list_memories_by_scope
from ...observability.logging import get_logger

log = get_logger("agent_memory_query")


def query_memories_by_provenance(
    *,
    cognito_user_id: str | None = None,
    slack_user_id: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    rfp_id: str | None = None,
    source: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Query memories by provenance fields for traceability.
    
    This function searches across all scopes to find memories matching
    the provenance criteria. This is useful for auditing and debugging.
    
    Args:
        cognito_user_id: Filter by Cognito user ID
        slack_user_id: Filter by Slack user ID
        slack_channel_id: Filter by Slack channel ID
        slack_thread_ts: Filter by Slack thread timestamp
        rfp_id: Filter by RFP ID
        source: Filter by source system
        limit: Maximum number of results
    
    Returns:
        List of matching memory dicts with full provenance
    """
    # This is a simplified implementation - for production, you might want
    # to add GSI indexes on provenance fields for efficient querying
    
    # Strategy: Query by scope if we can determine it, then filter by provenance
    all_memories: list[dict[str, Any]] = []
    
    # If we have cognito_user_id, query USER scope
    if cognito_user_id:
        scope_id = f"USER#{cognito_user_id}"
        memories, _ = list_memories_by_scope(scope_id=scope_id, limit=limit * 2)
        all_memories.extend(memories)
    
    # If we have rfp_id, query RFP scope
    if rfp_id:
        scope_id = f"RFP#{rfp_id}"
        memories, _ = list_memories_by_scope(scope_id=scope_id, limit=limit * 2)
        all_memories.extend(memories)
    
    # Filter by provenance criteria
    filtered: list[dict[str, Any]] = []
    for mem in all_memories:
        # Check provenance match
        if cognito_user_id and mem.get("cognitoUserId") != cognito_user_id:
            continue
        if slack_user_id and mem.get("slackUserId") != slack_user_id:
            continue
        if slack_channel_id and mem.get("slackChannelId") != slack_channel_id:
            continue
        if slack_thread_ts and mem.get("slackThreadTs") != slack_thread_ts:
            continue
        if rfp_id and mem.get("rfpId") != rfp_id:
            continue
        if source and mem.get("source") != source:
            continue
        
        filtered.append(mem)
        if len(filtered) >= limit:
            break
    
    return filtered[:limit]


def get_memory_provenance(memory: dict[str, Any]) -> dict[str, Any]:
    """
    Extract provenance information from a memory for traceability.
    
    Returns a dict with all provenance fields for easy inspection.
    """
    return {
        "cognitoUserId": memory.get("cognitoUserId"),
        "slackUserId": memory.get("slackUserId"),
        "slackChannelId": memory.get("slackChannelId"),
        "slackThreadTs": memory.get("slackThreadTs"),
        "slackTeamId": memory.get("slackTeamId"),
        "rfpId": memory.get("rfpId"),
        "source": memory.get("source"),
        "createdAt": memory.get("createdAt"),
        "memoryId": memory.get("memoryId"),
        "scopeId": memory.get("scopeId"),
    }
