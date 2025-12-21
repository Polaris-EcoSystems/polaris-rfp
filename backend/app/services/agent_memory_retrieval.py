from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .agent_memory_db import (
    list_memories_by_scope,
    list_memories_by_type,
    update_memory_access,
)
from .agent_memory_keywords import extract_keywords
from .agent_memory_opensearch import search_memories
from ..observability.logging import get_logger

log = get_logger("agent_memory_retrieval")


def _calculate_relevance_score(
    memory: dict[str, Any],
    query_keywords: list[str],
    query_scope: str | None = None,
    query_type: str | None = None,
) -> float:
    """
    Calculate relevance score for a memory based on query parameters.
    
    Scoring factors:
    - Keyword overlap (40%): Count of matching keywords/tags
    - Recency (30%): Days since creation (more recent = higher score)
    - Access frequency (20%): accessCount (higher = more important)
    - Scope match (10%): Exact scope match bonus
    
    Returns:
        Relevance score (0.0 to 1.0, higher is better)
    """
    query_keywords_lower = [kw.lower() for kw in query_keywords]
    
    # Keyword overlap (40% weight)
    memory_keywords = [str(k).lower() for k in memory.get("keywords", [])]
    memory_tags = [str(t).lower() for t in memory.get("tags", [])]
    all_memory_terms = set(memory_keywords + memory_tags)
    
    keyword_matches = sum(1 for qk in query_keywords_lower if qk in all_memory_terms)
    max_possible_matches = max(len(query_keywords_lower), 1)
    keyword_score = min(keyword_matches / max_possible_matches, 1.0)
    
    # Recency (30% weight) - more recent = higher score
    created_at_str = memory.get("createdAt", "")
    try:
        if created_at_str:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            days_old = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).days
            # Score decays over 90 days (0 days = 1.0, 90+ days = 0.0)
            recency_score = max(0.0, 1.0 - (days_old / 90.0))
        else:
            recency_score = 0.5  # Unknown age = medium score
    except Exception:
        recency_score = 0.5
    
    # Access frequency (20% weight) - normalize to 0-1 (capped at 100 accesses)
    access_count = memory.get("accessCount", 0)
    frequency_score = min(access_count / 100.0, 1.0)
    
    # Scope match (10% weight) - exact match bonus
    memory_scope = memory.get("scopeId", "")
    scope_score = 1.0 if query_scope and memory_scope == query_scope else 0.0
    
    # Type match bonus (if specified)
    type_match = 1.0 if query_type and memory.get("memoryType") == query_type else 0.5
    
    # Weighted combination
    final_score = (
        keyword_score * 0.4 +
        recency_score * 0.3 +
        frequency_score * 0.2 +
        scope_score * 0.1
    ) * type_match
    
    return min(max(final_score, 0.0), 1.0)


def retrieve_relevant_memories(
    *,
    scope_id: str | None = None,
    memory_types: list[str] | None = None,
    query_text: str | None = None,
    limit: int = 20,
    use_opensearch: bool = True,
) -> list[dict[str, Any]]:
    start_time = time.time()
    """
    Retrieve relevant memories using a combination of DynamoDB queries and OpenSearch search.
    
    Strategy:
    1. If simple scope query: Use DynamoDB directly (fast)
    2. If keyword/topic query: Use OpenSearch, then fetch full records from DynamoDB
    3. Apply relevance scoring to all results
    4. Return top N most relevant
    
    Args:
        scope_id: Scope identifier (USER#{userSub}, RFP#{rfpId}, etc.)
        memory_types: List of memory types to filter by (None = all types)
        query_text: Optional text query for keyword search
        limit: Maximum number of memories to return
        use_opensearch: Whether to use OpenSearch for keyword queries
    
    Returns:
        List of relevant memory dicts, sorted by relevance (highest first)
    """
    candidates: list[dict[str, Any]] = []
    
    # Extract keywords from query text if provided
    query_keywords: list[str] = []
    if query_text:
        query_keywords = extract_keywords(query_text, max_keywords=20)
    
    # Strategy 1: Simple scope query (use DynamoDB)
    if scope_id and not query_text:
        memory_type = memory_types[0] if memory_types and len(memory_types) == 1 else None
        items, _ = list_memories_by_scope(
            scope_id=scope_id,
            memory_type=memory_type,
            limit=min(limit * 2, 100),  # Get more candidates for scoring
        )
        candidates.extend(items)
    
    # Strategy 2: Keyword/topic query (use OpenSearch)
    elif query_text and use_opensearch:
        opensearch_results = search_memories(
            query_text=query_text,
            keywords=query_keywords,
            scope_id=scope_id,
            memory_type=memory_types[0] if memory_types and len(memory_types) == 1 else None,
            limit=min(limit * 3, 100),  # Get more candidates
        )
        
        # Fetch full records from DynamoDB using memoryIds
        # Note: We'd need to store created_at in OpenSearch or have another lookup mechanism
        # For now, we'll use what OpenSearch returns (may not have all fields)
        candidates.extend(opensearch_results)
    
    # Strategy 3: Type-based query (use DynamoDB GSI2)
    elif memory_types and not query_text:
        for mem_type in memory_types:
            items, _ = list_memories_by_type(
                memory_type=mem_type,
                scope_id=scope_id,
                limit=min(limit * 2, 50),
            )
            candidates.extend(items)
    
    # Filter by memory type if specified
    if memory_types:
        candidates = [c for c in candidates if c.get("memoryType") in memory_types]
    
    # Calculate relevance scores
    scored_memories: list[tuple[float, dict[str, Any]]] = []
    for memory in candidates:
        score = _calculate_relevance_score(
            memory=memory,
            query_keywords=query_keywords,
            query_scope=scope_id,
            query_type=memory_types[0] if memory_types else None,
        )
        scored_memories.append((score, memory))
    
    # Sort by score (descending) and return top N
    scored_memories.sort(key=lambda x: x[0], reverse=True)
    top_memories = [mem for _, mem in scored_memories[:limit]]
    
    # Update access counts (best-effort, non-blocking)
    for memory in top_memories:
        memory_id = memory.get("memoryId")
        memory_type = memory.get("memoryType")
        scope_id_mem = memory.get("scopeId")
        created_at = memory.get("createdAt")
        
        if memory_id and memory_type and scope_id_mem and created_at:
            try:
                update_memory_access(
                    memory_id=memory_id,
                    memory_type=memory_type,
                    scope_id=scope_id_mem,
                    created_at=created_at,
                )
            except Exception:
                pass  # Non-critical, continue
    
    duration_ms = int((time.time() - start_time) * 1000)
    log.info(
        "memory_retrieval_completed",
        scope_id=scope_id,
        memory_types=memory_types,
        has_query=bool(query_text),
        candidates_found=len(candidates),
        results_returned=len(top_memories),
        duration_ms=duration_ms,
    )
    
    return top_memories


def get_memories_for_context(
    *,
    user_sub: str | None = None,
    rfp_id: str | None = None,
    tenant_id: str | None = None,
    query_text: str | None = None,
    memory_types: list[str] | None = None,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """
    Get relevant memories for agent context building.
    
    This is a convenience function that determines the appropriate scope
    and retrieves memories.
    
    Args:
        user_sub: User identifier
        rfp_id: RFP identifier
        tenant_id: Tenant identifier
        query_text: Optional search query
        memory_types: Optional list of memory types to filter by
        limit: Maximum number of memories to return
    
    Returns:
        List of relevant memories
    """
    # Determine scope
    scope_id: str | None = None
    if rfp_id:
        scope_id = f"RFP#{rfp_id}"
    elif user_sub:
        scope_id = f"USER#{user_sub}"
    elif tenant_id:
        scope_id = f"TENANT#{tenant_id}"
    
    return retrieve_relevant_memories(
        scope_id=scope_id,
        memory_types=memory_types,
        query_text=query_text,
        limit=limit,
    )
