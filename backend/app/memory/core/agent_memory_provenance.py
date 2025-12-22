"""
Provenance-based memory queries and trust weighting.

Enables querying memories by who created them, when, and where,
with trust weighting based on source credibility.
"""

from __future__ import annotations

from typing import Any

from .agent_memory_query import query_memories_by_provenance
from ...observability.logging import get_logger

log = get_logger("agent_memory_provenance")


def calculate_provenance_trust_weight(
    *,
    memory: dict[str, Any],
    verified_users: set[str] | None = None,
    frequently_cited_users: set[str] | None = None,
) -> float:
    """
    Calculate trust weight for a memory based on provenance.
    
    Factors:
    - Source system credibility
    - User verification status
    - Frequency of citations/references
    - Provenance completeness
    
    Returns:
        Trust weight multiplier (0.5 to 1.5, where 1.0 is neutral)
    """
    verified_users = verified_users or set()
    frequently_cited_users = frequently_cited_users or set()
    
    provenance = memory.get("metadata", {}).get("provenance", {})
    if not isinstance(provenance, dict):
        return 1.0  # Neutral if no provenance
    
    trust_multiplier = 1.0
    
    # Source system credibility
    source = provenance.get("source", "")
    trusted_sources = {"slack_operator", "api", "system"}
    if source in trusted_sources:
        trust_multiplier += 0.1
    
    # User verification
    cognito_user_id = provenance.get("cognitoUserId")
    if cognito_user_id and cognito_user_id in verified_users:
        trust_multiplier += 0.2
    
    # Frequently cited users
    if cognito_user_id and cognito_user_id in frequently_cited_users:
        trust_multiplier += 0.1
    
    # Provenance completeness bonus
    required_fields = ["cognitoUserId", "source"]
    present_fields = sum(1 for field in required_fields if provenance.get(field))
    completeness_bonus = (present_fields / len(required_fields)) * 0.1
    trust_multiplier += completeness_bonus
    
    return min(max(trust_multiplier, 0.5), 1.5)  # Cap between 0.5 and 1.5


def get_memories_by_participants(
    *,
    participant_user_ids: list[str],
    memory_types: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Get memories that involve specific participants.
    
    Args:
        participant_user_ids: List of user IDs to filter by
        memory_types: Optional memory types to filter
        limit: Maximum number of memories to return
    
    Returns:
        List of memories involving the participants
    """
    all_memories: list[dict[str, Any]] = []
    
    # Query memories by provenance for each participant
    for user_id in participant_user_ids[:10]:  # Limit to avoid too many queries
        try:
            memories = query_memories_by_provenance(
                cognito_user_id=user_id,
                limit=limit,
            )
            all_memories.extend(memories)
        except Exception as e:
            log.warning("failed_to_query_participant_memories", error=str(e), user_id=user_id)
    
    # Filter by memory type if specified
    if memory_types:
        all_memories = [
            m for m in all_memories
            if m.get("memoryType") in memory_types
        ]
    
    # Deduplicate by memoryId
    seen_ids: set[str] = set()
    unique_memories: list[dict[str, Any]] = []
    for memory in all_memories:
        memory_id = memory.get("memoryId")
        if memory_id and memory_id not in seen_ids:
            seen_ids.add(memory_id)
            unique_memories.append(memory)
            if len(unique_memories) >= limit:
                break
    
    return unique_memories


def get_conversation_thread_memories(
    *,
    channel_id: str,
    thread_ts: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Get all memories that originated from a specific conversation thread.
    
    Args:
        channel_id: Slack channel ID
        thread_ts: Slack thread timestamp
        limit: Maximum number of memories to return
    
    Returns:
        List of memories from the conversation thread
    """
    try:
        memories = query_memories_by_provenance(
            slack_channel_id=channel_id,
            limit=limit * 2,
        )
        
        # Filter to specific thread
        thread_memories = [
            m for m in memories
            if m.get("metadata", {}).get("provenance", {}).get("slackThreadTs") == thread_ts
        ]
        
        return thread_memories[:limit]
    
    except Exception as e:
        log.error("failed_to_get_thread_memories", error=str(e), channel_id=channel_id, thread_ts=thread_ts)
        return []
