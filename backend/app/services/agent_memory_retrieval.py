from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from .agent_memory_db import (
    MemoryType,
    list_memories_by_scope,
    list_memories_by_type,
    update_memory_access,
)
from .agent_memory_keywords import extract_keywords
from .agent_memory_opensearch import search_memories
from .agent_memory_scope_expansion import expand_scopes_contextually
from ..observability.logging import get_logger

log = get_logger("agent_memory_retrieval")


def _calculate_relevance_score(
    memory: dict[str, Any],
    query_keywords: list[str],
    query_scope: str | None = None,
    query_type: str | None = None,
    apply_provenance_trust: bool = True,
    use_importance: bool = True,
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
    keyword_score = min(keyword_matches / max_possible_matches, 1.0) if query_keywords_lower else 0.5  # Default if no keywords
    
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
    
    # Apply provenance trust weighting if enabled
    if apply_provenance_trust:
        try:
            from .agent_memory_provenance import calculate_provenance_trust_weight
            trust_weight = calculate_provenance_trust_weight(memory=memory)
            final_score *= trust_weight
        except Exception:
            pass  # If provenance calculation fails, use score as-is
    
    # Apply importance scoring (integrate into relevance)
    try:
        from .agent_memory_consolidation import calculate_importance_score
        importance = calculate_importance_score(memory=memory, base_access_count=access_count)
        # Blend importance into relevance (20% weight for importance)
        final_score = final_score * 0.8 + importance * 0.2
    except Exception:
        pass  # If importance calculation fails, use score as-is
    
    return min(max(final_score, 0.0), 1.0)


def retrieve_relevant_memories(
    *,
    scope_id: str | None = None,
    memory_types: list[str] | None = None,
    query_text: str | None = None,
    limit: int = 20,
    use_opensearch: bool = True,
    token_budget_tracker: Any | None = None,  # TokenBudgetTracker for budget-aware retrieval
    min_importance: float | None = None,  # Minimum importance score filter
    use_importance: bool = True,  # Whether to use importance in relevance scoring
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
    # If multiple memory types requested, query in parallel
    if scope_id and not query_text:
        if memory_types and len(memory_types) > 1:
            # Parallel retrieval for multiple types
            with ThreadPoolExecutor(max_workers=min(len(memory_types), 5)) as executor:
                futures = {
                    executor.submit(
                        list_memories_by_scope,
                        scope_id=scope_id,
                        memory_type=mem_type,
                        limit=min(limit * 2, 100),
                    ): mem_type
                    for mem_type in memory_types
                }
                for future in as_completed(futures):
                    try:
                        items, _ = future.result()
                        candidates.extend(items)
                    except Exception as e:
                        log.warning("parallel_scope_retrieval_failed", error=str(e), memory_type=futures[future])
        else:
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
    
    # Strategy 3: Type-based query (use DynamoDB GSI2) - parallel retrieval
    elif memory_types and not query_text:
        # Parallel retrieval for multiple memory types
        with ThreadPoolExecutor(max_workers=min(len(memory_types), 5)) as executor:
            futures = {
                executor.submit(
                    list_memories_by_type,
                    memory_type=mem_type,
                    scope_id=scope_id,
                    limit=min(limit * 2, 50),
                ): mem_type
                for mem_type in memory_types
            }
            for future in as_completed(futures):
                try:
                    items, _ = future.result()
                    candidates.extend(items)
                except Exception as e:
                    log.warning("parallel_memory_retrieval_failed", error=str(e), memory_type=futures[future])
    else:
        # Fallback: query all types in parallel if no specific strategy
        if not memory_types:
            # Default memory types to query
            memory_types = [MemoryType.EPISODIC, MemoryType.SEMANTIC, MemoryType.PROCEDURAL]
        
        with ThreadPoolExecutor(max_workers=min(len(memory_types), 5)) as executor:
            futures = {
                executor.submit(
                    list_memories_by_type,
                    memory_type=mem_type,
                    scope_id=scope_id,
                    limit=min(limit * 2, 50),
                ): mem_type
                for mem_type in memory_types
            }
            for future in as_completed(futures):
                try:
                    items, _ = future.result()
                    candidates.extend(items)
                except Exception as e:
                    log.warning("parallel_memory_retrieval_failed", error=str(e), memory_type=futures[future])
    
    # Filter by memory type if specified
    if memory_types:
        candidates = [c for c in candidates if c.get("memoryType") in memory_types]
    
    # Filter by importance if specified
    if min_importance is not None:
        try:
            from .agent_memory_consolidation import calculate_importance_score
            filtered_candidates: list[dict[str, Any]] = []
            for memory in candidates:
                importance = calculate_importance_score(memory=memory)
                if importance >= min_importance:
                    filtered_candidates.append(memory)
            candidates = filtered_candidates
        except Exception:
            pass  # If importance calculation fails, skip filtering
    
    # Calculate relevance scores
    scored_memories: list[tuple[float, dict[str, Any]]] = []
    query_matched_memory_ids: set[str] = set()
    
    # First pass: calculate scores and identify query-matched memories
    for memory in candidates:
        score = _calculate_relevance_score(
            memory=memory,
            query_keywords=query_keywords,
            query_scope=scope_id,
            query_type=memory_types[0] if memory_types else None,
            use_importance=use_importance,
        )
        scored_memories.append((score, memory))
        
        # If score is high, mark as query-matched
        if score > 0.5:
            memory_id = memory.get("memoryId")
            if memory_id:
                query_matched_memory_ids.add(memory_id)
    
    # Second pass: boost scores for memories related to query-matched memories
    if query_matched_memory_ids:
        for i, (score, memory) in enumerate(scored_memories):
            memory_id = memory.get("memoryId")
            if memory_id in query_matched_memory_ids:
                continue  # Already query-matched
            
            # Check if this memory has relationships to query-matched memories
            related_ids = memory.get("relatedMemoryIds", [])
            if related_ids and any(rid in query_matched_memory_ids for rid in related_ids):
                # Boost score by 20% if related to query-matched memory
                boosted_score = score * 1.2
                scored_memories[i] = (min(boosted_score, 1.0), memory)
    
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
    include_global_diagnostics: bool = True,
    channel_id: str | None = None,
    thread_ts: str | None = None,
    context: dict[str, Any] | None = None,
    expand_scopes: bool = True,
) -> list[dict[str, Any]]:
    """
    Get relevant memories for agent context building.

    This is a convenience function that determines the appropriate scope
    and retrieves memories. Optionally includes GLOBAL scope diagnostics
    memories when querying about agent activity.

    Args:
        user_sub: User identifier
        rfp_id: RFP identifier
        tenant_id: Tenant identifier
        query_text: Optional search query (if contains agent/activity keywords, includes diagnostics)
        memory_types: Optional list of memory types to filter by
        limit: Maximum number of memories to return
        include_global_diagnostics: Whether to include GLOBAL scope diagnostics if query matches

    Returns:
        List of relevant memories
    """
    # Determine primary scope
    primary_scope_id: str | None = None
    if rfp_id:
        primary_scope_id = f"RFP#{rfp_id}"
    elif user_sub:
        primary_scope_id = f"USER#{user_sub}"
    elif tenant_id:
        primary_scope_id = f"TENANT#{tenant_id}"
    elif channel_id:
        if thread_ts:
            primary_scope_id = f"THREAD#{channel_id}#{thread_ts}"
        else:
            primary_scope_id = f"CHANNEL#{channel_id}"
    
    # Expand scopes contextually if enabled
    scope_ids: list[str] = []
    if expand_scopes:
        scope_ids = expand_scopes_contextually(
            primary_scope_id=primary_scope_id,
            rfp_id=rfp_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            user_sub=user_sub,
            tenant_id=tenant_id,
            query_text=query_text,
            context=context,
        )
    else:
        if primary_scope_id:
            scope_ids = [primary_scope_id]
    
    # If no scopes determined, use primary scope only
    if not scope_ids and primary_scope_id:
        scope_ids = [primary_scope_id]
    
    # Retrieve memories from all expanded scopes
    all_memories: list[dict[str, Any]] = []
    for scope_id in scope_ids:
        scope_memories = retrieve_relevant_memories(
            scope_id=scope_id,
            memory_types=memory_types,
            query_text=query_text,
            limit=limit * 2,  # Get more per scope, will re-rank across scopes
        )
        all_memories.extend(scope_memories)
    
    # Re-rank all memories across scopes by relevance
    # Apply cross-scope relevance scoring
    query_keywords = extract_keywords(query_text, max_keywords=20) if query_text else []
    scored_memories: list[tuple[float, dict[str, Any]]] = []
    
    for memory in all_memories:
        score = _calculate_relevance_score(
            memory=memory,
            query_keywords=query_keywords,
            query_scope=primary_scope_id,
            use_importance=True,  # Always use importance in context building
        )
        # Bonus for primary scope matches
        memory_scope = memory.get("scopeId", "")
        if memory_scope == primary_scope_id:
            score *= 1.2  # 20% boost for primary scope
        scored_memories.append((score, memory))
    
    # Sort by score and deduplicate by memoryId
    scored_memories.sort(key=lambda x: x[0], reverse=True)
    seen_ids: set[str] = set()
    memories: list[dict[str, Any]] = []
    for score, memory in scored_memories:
        memory_id = memory.get("memoryId")
        if memory_id and memory_id not in seen_ids:
            seen_ids.add(memory_id)
            memories.append(memory)
            if len(memories) >= limit:
                break
    
    # If query text suggests agent activity diagnostics or real-world context, also include GLOBAL memories
    if include_global_diagnostics and query_text:
        query_lower = query_text.lower()
        
        # Check for agent activity keywords
        activity_keywords = ["agent", "activity", "recent", "what", "diagnostics", "metrics", "doing", "been"]
        # Check for real-world context keywords
        real_world_keywords = ["news", "weather", "research", "current", "today", "recent events", "geopolitical", "business", "finance", "market"]
        
        if any(keyword in query_lower for keyword in activity_keywords + real_world_keywords):
            # Also retrieve diagnostics and external context from GLOBAL scope
            from .agent_memory_db import MemoryType
            global_memories = retrieve_relevant_memories(
                scope_id="GLOBAL",
                memory_types=[MemoryType.DIAGNOSTICS, MemoryType.EXTERNAL_CONTEXT],
                query_text=query_text,
                limit=8,  # Limit global memories
            )
            # Combine and deduplicate by memory ID
            seen_memory_ids: set[str] = set()
            for mem in memories:
                mem_id = mem.get("memoryId")
                if mem_id and isinstance(mem_id, str):
                    seen_memory_ids.add(mem_id)
            for global_mem in global_memories:
                mem_id = global_mem.get("memoryId")
                if mem_id and isinstance(mem_id, str) and mem_id not in seen_memory_ids:
                    memories.append(global_mem)
                    seen_memory_ids.add(mem_id)
    
    return memories[:limit]
