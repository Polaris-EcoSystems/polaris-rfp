"""
Memory consolidation and importance scoring.

Implements human-like memory consolidation where important memories are strengthened
and less important ones fade or get compressed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .agent_memory_db import (
    MemoryType,
    get_memory,
    list_memories_by_scope,
    update_memory,
)
from ..observability.logging import get_logger

log = get_logger("agent_memory_consolidation")


def calculate_importance_score(
    *,
    memory: dict[str, Any],
    base_access_count: int = 0,
) -> float:
    """
    Calculate importance score for a memory based on access patterns.
    
    Factors:
    - Access frequency (accessCount)
    - Recency of access (lastAccessedAt)
    - Recency of creation (createdAt)
    - Memory type (some types are inherently more important)
    - Relationships (memories with many relationships are more important)
    
    Returns:
        Importance score (0.0 to 1.0, higher is more important)
    """
    access_count = memory.get("accessCount", base_access_count)
    last_accessed = memory.get("lastAccessedAt")
    created_at = memory.get("createdAt")
    memory_type = memory.get("memoryType", "")
    related_ids = memory.get("relatedMemoryIds", [])
    
    # Access frequency score (0-0.4 weight)
    # Normalize to 0-1 (capped at 100 accesses = 1.0)
    frequency_score = min(access_count / 100.0, 1.0) * 0.4
    
    # Recency of access score (0-0.3 weight)
    # More recently accessed = higher score
    recency_score = 0.15  # Default medium score
    if last_accessed:
        try:
            last_dt = datetime.fromisoformat(last_accessed.replace("Z", "+00:00"))
            days_since_access = (datetime.now(timezone.utc) - last_dt.replace(tzinfo=timezone.utc)).days
            # Score decays over 30 days
            recency_score = max(0.0, 1.0 - (days_since_access / 30.0)) * 0.3
        except Exception:
            pass
    
    # Creation recency score (0-0.1 weight)
    # Newer memories slightly more important initially
    creation_score = 0.05  # Default
    if created_at:
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            days_old = (datetime.now(timezone.utc) - created_dt.replace(tzinfo=timezone.utc)).days
            # New memories (< 7 days) get boost
            if days_old < 7:
                creation_score = (1.0 - (days_old / 7.0)) * 0.1
        except Exception:
            pass
    
    # Memory type importance (0-0.1 weight)
    type_scores = {
        MemoryType.PROCEDURAL: 1.0,  # Procedures are important
        MemoryType.SEMANTIC: 0.9,  # Preferences/knowledge important
        MemoryType.EPISODIC: 0.7,  # Events vary in importance
        MemoryType.COLLABORATION_CONTEXT: 0.8,  # Collaboration patterns important
        MemoryType.TEMPORAL_EVENT: 0.9,  # Deadlines/events important
        MemoryType.DIAGNOSTICS: 0.5,  # Diagnostics less important over time
        MemoryType.EXTERNAL_CONTEXT: 0.4,  # External context often transient
    }
    type_score = type_scores.get(memory_type, 0.7) * 0.1
    
    # Relationship importance (0-0.1 weight)
    # Memories with many relationships are more central/important
    relationship_count = len(related_ids) if isinstance(related_ids, list) else 0
    relationship_score = min(relationship_count / 10.0, 1.0) * 0.1
    
    total_score = frequency_score + recency_score + creation_score + type_score + relationship_score
    return min(max(total_score, 0.0), 1.0)


def consolidate_old_memories(
    *,
    scope_id: str,
    memory_type: str | None = None,
    days_old: int = 90,
    min_access_count: int = 5,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Consolidate old, low-importance memories by compressing or summarizing them.
    
    Args:
        scope_id: Scope identifier
        memory_type: Optional memory type to consolidate
        days_old: Minimum age in days to consider for consolidation
        min_access_count: Minimum access count threshold (memories below this are candidates)
        limit: Maximum number of memories to process
    
    Returns:
        List of consolidated memory summaries
    """
    # Get old memories
    all_memories, _ = list_memories_by_scope(
        scope_id=scope_id,
        memory_type=memory_type,
        limit=limit * 2,
    )
    
    cutoff_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) - timedelta(days=days_old)
    
    candidates: list[dict[str, Any]] = []
    for memory in all_memories:
        created_at = memory.get("createdAt")
        if not created_at:
            continue
        
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if created_dt.replace(tzinfo=timezone.utc) >= cutoff_date:
                continue  # Too recent
            
            access_count = memory.get("accessCount", 0)
            if access_count >= min_access_count:
                continue  # Accessed enough, keep as-is
            
            importance = calculate_importance_score(memory=memory)
            if importance < 0.3:  # Low importance threshold
                candidates.append(memory)
        except Exception:
            continue
    
    # Sort by importance (lowest first - consolidate least important)
    candidates.sort(key=lambda m: calculate_importance_score(memory=m))
    
    consolidated: list[dict[str, Any]] = []
    for memory in candidates[:limit]:
        # Create compressed summary memory
        # For now, just mark for consolidation - full implementation would create summaries
        consolidated.append(memory)
    
    log.info(
        "memories_consolidated",
        scope_id=scope_id,
        count=len(consolidated),
        memory_type=memory_type,
    )
    
    return consolidated


def update_memory_importance(
    *,
    memory_id: str,
    memory_type: str,
    scope_id: str,
    created_at: str,
) -> float | None:
    """
    Update and store importance score for a memory.
    
    Args:
        memory_id: Memory ID
        memory_type: Memory type
        scope_id: Scope ID
        created_at: Created at timestamp
    
    Returns:
        Updated importance score, or None if update failed
    """
    try:
        memory = get_memory(
            memory_id=memory_id,
            memory_type=memory_type,
            scope_id=scope_id,
            created_at=created_at,
        )
        if not memory:
            return None
        
        importance = calculate_importance_score(memory=memory)
        
        # Update memory with importance score in metadata
        metadata = memory.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        
        metadata["importanceScore"] = importance
        
        update_memory(
            memory_id=memory_id,
            memory_type=memory_type,
            scope_id=scope_id,
            created_at=created_at,
            metadata=metadata,
        )
        
        return importance
    
    except Exception as e:
        log.error("failed_to_update_importance", error=str(e), memory_id=memory_id)
        return None
