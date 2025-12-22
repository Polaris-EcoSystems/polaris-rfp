from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...ai.context import clip_text
from .agent_memory_db import MemoryType, create_memory, list_memories_by_scope
from .agent_memory_keywords import extract_entities, extract_keywords, extract_tags
from ..retrieval.agent_memory_opensearch import index_memory
from ..retrieval.agent_memory_retrieval import get_memories_for_context, retrieve_relevant_memories


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_user_memory(*, user_sub: str) -> dict[str, Any]:
    """
    Retrieve structured memory for a user.
    Returns a dict with episodic, semantic, and procedural memory.
    
    This is a convenience function that queries the new memory database.
    """
    scope_id = f"USER#{user_sub}"
    
    # Get recent memories of each type
    episodic_items, _ = list_memories_by_scope(scope_id=scope_id, memory_type=MemoryType.EPISODIC, limit=20)
    semantic_items, _ = list_memories_by_scope(scope_id=scope_id, memory_type=MemoryType.SEMANTIC, limit=50)
    procedural_items, _ = list_memories_by_scope(scope_id=scope_id, memory_type=MemoryType.PROCEDURAL, limit=20)
    
    # Convert semantic memories to dict format (key-value pairs)
    semantic_dict: dict[str, Any] = {}
    for mem in semantic_items:
        content = mem.get("content", "")
        # Try to parse semantic memory content (may be JSON or key-value format)
        # For now, use content as-is or extract from metadata
        metadata = mem.get("metadata", {})
        if isinstance(metadata, dict) and "key" in metadata and "value" in metadata:
            semantic_dict[metadata["key"]] = metadata["value"]
        elif content:
            # Fallback: use content as both key and value indicator
            semantic_dict[content[:100]] = content
    
    return {
        "episodic": episodic_items,
        "semantic": semantic_dict,
        "procedural": procedural_items,
    }


def add_episodic_memory(
    *,
    user_sub: str,
    content: str,
    context: dict[str, Any] | None = None,
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
    Add an episodic memory (specific conversation, decision, outcome) with full provenance.
    
    Args:
        user_sub: User identifier (Cognito sub)
        content: Memory content
        context: Optional context dict (conversationContext, userMessage, agentAction, outcome, etc.)
        cognito_user_id: Cognito user identifier (for traceability - typically same as user_sub)
        slack_user_id: Slack user ID if memory originated from Slack
        slack_channel_id: Slack channel ID where memory originated
        slack_thread_ts: Slack thread timestamp where memory originated
        slack_team_id: Slack team ID
        rfp_id: RFP identifier if memory is related to an RFP
        source: Source system (e.g., "slack_agent", "slack_operator", "api", "migration")
    
    Returns:
        Created memory dict
    """
    scope_id = f"USER#{user_sub}"
    
    # Extract keywords and tags
    keywords = extract_keywords(content)
    tags = extract_tags(content, metadata=context)
    entities = extract_entities(content)
    keywords.extend(entities)
    
    # Build metadata from context
    metadata: dict[str, Any] = {}
    if context:
        metadata.update(context)
    
    # Create summary (first 500 chars)
    summary = clip_text(content, max_chars=500)
    
    # Use cognito_user_id if not provided (assume user_sub is cognito sub)
    final_cognito_user_id = cognito_user_id or user_sub
    
    memory = create_memory(
        memory_type=MemoryType.EPISODIC,
        scope_id=scope_id,
        content=content,
        tags=tags,
        keywords=keywords,
        metadata=metadata if metadata else None,
        summary=summary,
        cognito_user_id=final_cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        slack_team_id=slack_team_id,
        rfp_id=rfp_id,
        source=source,
    )
    
    # Index in OpenSearch (async, best-effort)
    try:
        index_memory(memory)
    except Exception:
        pass  # Non-critical
    
    return memory


def update_semantic_memory(
    *,
    user_sub: str,
    key: str,
    value: Any,
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
    Update semantic memory (preferences, patterns, knowledge) with full provenance.
    
    Args:
        user_sub: User identifier (Cognito sub)
        key: Preference/keyword
        value: Preference value or knowledge fact
        cognito_user_id: Cognito user identifier (for traceability - typically same as user_sub)
        slack_user_id: Slack user ID if memory originated from Slack
        slack_channel_id: Slack channel ID where memory originated
        slack_thread_ts: Slack thread timestamp where memory originated
        slack_team_id: Slack team ID
        rfp_id: RFP identifier if memory is related to an RFP
        source: Source system (e.g., "slack_agent", "slack_operator", "api", "migration")
    
    Returns:
        Created/updated memory dict
    """
    scope_id = f"USER#{user_sub}"
    
    # Format content as key-value pair
    content = f"{key}: {value}"
    
    keywords = extract_keywords(f"{key} {value}")
    tags = extract_tags(content)
    tags.append("preference")
    
    metadata = {
        "key": key,
        "value": value,
        "lastValidatedAt": _now_iso(),
    }
    
    # Use cognito_user_id if not provided (assume user_sub is cognito sub)
    final_cognito_user_id = cognito_user_id or user_sub
    
    memory = create_memory(
        memory_type=MemoryType.SEMANTIC,
        scope_id=scope_id,
        content=content,
        tags=tags,
        keywords=keywords,
        metadata=metadata,
        summary=f"{key}: {value}",
        cognito_user_id=final_cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        slack_team_id=slack_team_id,
        rfp_id=rfp_id,
        source=source,
    )
    
    # Index in OpenSearch
    try:
        index_memory(memory)
    except Exception:
        pass
    
    return memory


def add_procedural_memory(
    *,
    user_sub: str,
    workflow: str,
    success: bool,
    context: dict[str, Any] | None = None,
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
    Add a procedural memory (successful workflow, tool usage pattern) with full provenance.
    
    Args:
        user_sub: User identifier (Cognito sub)
        workflow: Workflow description or name
        success: Whether the workflow was successful
        context: Optional context (toolSequence, successCriteria, etc.)
        cognito_user_id: Cognito user identifier (for traceability - typically same as user_sub)
        slack_user_id: Slack user ID if memory originated from Slack
        slack_channel_id: Slack channel ID where memory originated
        slack_thread_ts: Slack thread timestamp where memory originated
        slack_team_id: Slack team ID
        rfp_id: RFP identifier if memory is related to an RFP
        source: Source system (e.g., "slack_agent", "slack_operator", "api", "migration")
    
    Returns:
        Created memory dict
    """
    scope_id = f"USER#{user_sub}"
    
    content = f"Workflow: {workflow}\nSuccess: {success}"
    if context:
        tool_sequence = context.get("toolSequence")
        if tool_sequence:
            content += f"\nTools: {', '.join(str(t) for t in tool_sequence)}"
        success_criteria = context.get("successCriteria")
        if success_criteria:
            content += f"\nCriteria: {success_criteria}"
    
    keywords = extract_keywords(content)
    tags = extract_tags(content, metadata=context)
    tags.append("workflow")
    if success:
        tags.append("success")
    else:
        tags.append("failure")
    
    metadata = {
        "workflowName": workflow,
        "success": success,
    }
    if context:
        metadata.update(context)
    
    # Use cognito_user_id if not provided (assume user_sub is cognito sub)
    final_cognito_user_id = cognito_user_id or user_sub
    
    memory = create_memory(
        memory_type=MemoryType.PROCEDURAL,
        scope_id=scope_id,
        content=content,
        tags=tags,
        keywords=keywords,
        metadata=metadata,
        summary=f"Workflow: {workflow} ({'success' if success else 'failure'})",
        cognito_user_id=final_cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        slack_team_id=slack_team_id,
        rfp_id=rfp_id,
        source=source,
    )
    
    # Index in OpenSearch
    try:
        index_memory(memory)
    except Exception:
        pass
    
    return memory


def add_diagnostics_memory(
    *,
    scope_id: str = "GLOBAL",
    diagnostics_data: dict[str, Any],
    hours: int = 24,
    source: str | None = None,
) -> dict[str, Any]:
    """
    Store agent diagnostics (metrics and activity summary) in memory.
    
    Diagnostics are stored at GLOBAL scope by default so they can be retrieved
    by any user querying agent activity.
    
    Args:
        scope_id: Scope identifier (defaults to "GLOBAL" for agent-wide diagnostics)
        diagnostics_data: Diagnostics data dict (from build_agent_diagnostics)
        hours: Number of hours the diagnostics cover
        source: Source system (e.g., "diagnostics_service", "agent_tool")
    
    Returns:
        Created memory dict
    """
    # Extract summary text as content
    content = diagnostics_data.get("summaryText", "")
    if not content:
        # Fallback: build content from diagnostics data
        metrics = diagnostics_data.get("metrics", {})
        content = f"Agent Diagnostics (last {hours}h): "
        content += f"Operations: {metrics.get('count', 0)}, "
        content += f"Success rate: {metrics.get('success_rate', 0.0):.1%}, "
        content += f"Avg duration: {metrics.get('avg_duration_ms', 0)}ms"
    
    # Extract keywords from metrics and activities
    keywords: list[str] = ["diagnostics", "metrics", "activity", "agent"]
    metrics = diagnostics_data.get("metrics", {})
    if metrics.get("count", 0) > 0:
        keywords.append("active")
        if metrics.get("success_rate", 0.0) > 0.9:
            keywords.append("successful")
        if metrics.get("success_rate", 1.0) < 0.7:
            keywords.append("issues")
    
    # Add context-specific keywords
    filters = diagnostics_data.get("filters", {})
    if filters.get("userSub"):
        keywords.append("user-specific")
    if filters.get("rfpId"):
        keywords.append("rfp-specific")
        keywords.append(f"rfp-{filters.get('rfpId', '')[:10]}")
    if filters.get("channelId"):
        keywords.append("channel-specific")
    
    # Extract keywords from activities
    activities = diagnostics_data.get("recentActivities", [])
    for activity in activities[:10]:  # Top 10 activities
        activity_type = str(activity.get("type", "")).lower()
        if activity_type:
            keywords.append(activity_type)
        tool = str(activity.get("tool", "")).lower()
        if tool:
            keywords.append(tool)
    
    # Build tags
    tags = ["diagnostics", "metrics", "agent-activity"]
    if filters.get("rfpId"):
        tags.append(f"rfp:{filters.get('rfpId')}")
    if filters.get("userSub"):
        tags.append(f"user:{filters.get('userSub')[:20]}")
    
    # Store full diagnostics data in metadata
    metadata = {
        "diagnostics": diagnostics_data,
        "hours": hours,
        "window": diagnostics_data.get("window", {}),
    }
    
    # Create summary (first 500 chars of summary text)
    summary = clip_text(content, max_chars=500)
    
    memory = create_memory(
        memory_type=MemoryType.DIAGNOSTICS,
        scope_id=scope_id,
        content=content,
        tags=tags,
        keywords=keywords,
        metadata=metadata,
        summary=summary,
        source=source or "diagnostics_service",
    )
    
    # Index in OpenSearch (async, best-effort)
    try:
        index_memory(memory)
    except Exception:
        pass  # Non-critical
    
    return memory


def compress_memory(
    *,
    user_sub: str,
    days_old: int = 30,
) -> str:
    """
    Compress old memories by summarizing them.
    Returns a summary of old memories that can replace detailed entries.
    
    This is a wrapper around the compression module.
    """
    from .agent_memory_compression import compress_old_memories
    
    scope_id = f"USER#{user_sub}"
    result = compress_old_memories(
        scope_id=scope_id,
        memory_type=MemoryType.EPISODIC,
        days_old=days_old,
    )
    
    compressed_count = result.get("compressed_count", 0)
    if compressed_count > 0:
        return f"Compressed {compressed_count} memories"
    return "No memories to compress"


def search_memory(
    *,
    user_sub: str,
    query: str,
    memory_types: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Search user memory for relevant entries.
    Returns a list of matching memory entries.
    
    Args:
        user_sub: User identifier
        query: Search query text
        memory_types: Optional list of memory types to search (None = all)
        limit: Maximum number of results
    
    Returns:
        List of matching memory entries
    """
    scope_id = f"USER#{user_sub}"
    
    # Convert memory type strings to constants if needed
    type_constants: list[str] | None = None
    if memory_types:
        type_constants = []
        for mt in memory_types:
            if hasattr(MemoryType, mt.upper()):
                type_constants.append(getattr(MemoryType, mt.upper()))
            else:
                type_constants.append(mt.upper())
    
    results = retrieve_relevant_memories(
        scope_id=scope_id,
        memory_types=type_constants,
        query_text=query,
        limit=limit,
    )
    
    return results


def format_memory_for_context(
    *,
    user_sub: str,
    max_chars: int = 2000,
) -> str:
    """
    Format user memory for inclusion in agent context.
    Returns a formatted string optimized for prompts.
    
    Args:
        user_sub: User identifier
        max_chars: Maximum characters to return
    
    Returns:
        Formatted memory context string
    """
    memories = get_memories_for_context(
        user_sub=user_sub,
        limit=10,
    )
    
    if not memories:
        return ""
    
    lines: list[str] = []
    
    # Group by type
    episodic = [m for m in memories if m.get("memoryType") == MemoryType.EPISODIC]
    semantic = [m for m in memories if m.get("memoryType") == MemoryType.SEMANTIC]
    procedural = [m for m in memories if m.get("memoryType") == MemoryType.PROCEDURAL]
    
    # Format semantic memories (preferences)
    if semantic:
        lines.append("User preferences (semantic memory):")
        for mem in semantic[:10]:
            summary = mem.get("summary") or mem.get("content", "")
            lines.append(f"  - {clip_text(summary, max_chars=100)}")
        lines.append("")
    
    # Format episodic memories (recent conversations/decisions)
    if episodic:
        lines.append("Recent memories (episodic):")
        for mem in episodic[:5]:
            summary = mem.get("summary") or mem.get("content", "")
            lines.append(f"  - {clip_text(summary, max_chars=200)}")
        lines.append("")
    
    # Format procedural memories (workflows)
    if procedural:
        lines.append("Known workflows (procedural):")
        for mem in procedural[:3]:
            summary = mem.get("summary") or mem.get("content", "")
            lines.append(f"  - {clip_text(summary, max_chars=150)}")
        lines.append("")
    
    formatted = "\n".join(lines).strip()
    return clip_text(formatted, max_chars=max_chars)


def _calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two text strings using keyword overlap.
    
    Uses Jaccard similarity on keyword sets for a simple but effective measure.
    
    Args:
        text1: First text
        text2: Second text
    
    Returns:
        Similarity score (0.0 to 1.0, higher is more similar)
    """
    if not text1 or not text2:
        return 0.0
    
    # Extract keywords from both texts
    keywords1 = set(extract_keywords(text1, max_keywords=50))
    keywords2 = set(extract_keywords(text2, max_keywords=50))
    
    if not keywords1 and not keywords2:
        # Fallback to simple word overlap if no keywords
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 and not words2:
            return 1.0 if text1 == text2 else 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0
    
    # Jaccard similarity on keywords
    intersection = len(keywords1 & keywords2)
    union = len(keywords1 | keywords2)
    return intersection / union if union > 0 else 0.0


def find_similar_memories(
    *,
    user_sub: str,
    content: str,
    memory_type: str | None = None,
    similarity_threshold: float = 0.3,
    limit: int = 5,
    scope_id: str | None = None,
) -> list[tuple[dict[str, Any], float]]:
    """
    Find memories similar to the given content using keyword/tag overlap.
    
    Args:
        user_sub: User identifier
        content: Content to find similar memories for
        memory_type: Optional memory type to filter by
        similarity_threshold: Minimum similarity score (0.0 to 1.0)
        limit: Maximum number of results
        scope_id: Optional scope override (defaults to USER#{user_sub})
    
    Returns:
        List of (memory_dict, similarity_score) tuples, sorted by similarity (highest first)
    """
    if not scope_id:
        scope_id = f"USER#{user_sub}"
    
    # Get candidate memories
    memory_types = [memory_type] if memory_type else None
    candidates = retrieve_relevant_memories(
        scope_id=scope_id,
        memory_types=memory_types,
        query_text=content,
        limit=limit * 3,  # Get more candidates for similarity scoring
    )
    
    # Calculate similarity scores
    scored: list[tuple[dict[str, Any], float]] = []
    content_keywords = set(extract_keywords(content, max_keywords=50))
    
    for memory in candidates:
        # Calculate similarity using keyword overlap
        memory_keywords = set(memory.get("keywords", []))
        memory_tags = set(memory.get("tags", []))
        all_memory_terms = memory_keywords | memory_tags
        
        # Keyword overlap similarity
        if content_keywords and all_memory_terms:
            intersection = len(content_keywords & all_memory_terms)
            union = len(content_keywords | all_memory_terms)
            keyword_similarity = intersection / union if union > 0 else 0.0
        else:
            keyword_similarity = 0.0
        
        # Also calculate text similarity on content
        memory_content = memory.get("content", "")
        text_similarity = _calculate_text_similarity(content, memory_content)
        
        # Combined similarity (weighted average)
        combined_similarity = (keyword_similarity * 0.6 + text_similarity * 0.4)
        
        if combined_similarity >= similarity_threshold:
            scored.append((memory, combined_similarity))
    
    # Sort by similarity (descending) and return top N
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def find_memory_to_update(
    *,
    user_sub: str,
    content: str,
    memory_type: str | None = None,
    similarity_threshold: float = 0.7,
) -> dict[str, Any] | None:
    """
    Find an existing memory that should be updated with new content.
    
    This is a convenience function that finds the most similar memory
    above the similarity threshold, suitable for updating.
    
    Args:
        user_sub: User identifier
        content: New content to potentially update with
        memory_type: Optional memory type to filter by
        similarity_threshold: Minimum similarity to consider for update (default 0.7)
    
    Returns:
        Most similar memory dict if found above threshold, None otherwise
    """
    similar = find_similar_memories(
        user_sub=user_sub,
        content=content,
        memory_type=memory_type,
        similarity_threshold=similarity_threshold,
        limit=1,
    )
    
    if similar and len(similar) > 0:
        return similar[0][0]  # Return the memory dict (first element of first tuple)
    
    return None


def update_existing_memory(
    *,
    memory_id: str,
    memory_type: str,
    scope_id: str,
    created_at: str,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
    reason: str = "Information update",
    user_sub: str | None = None,
) -> dict[str, Any]:
    """
    Update an existing memory with new information.
    Tracks update history and reasons.
    
    Args:
        memory_id: Memory identifier
        memory_type: Memory type
        scope_id: Scope identifier
        created_at: Original creation timestamp
        content: New content (optional)
        metadata: New metadata to merge (optional)
        reason: Reason for the update
        user_sub: User identifier (for provenance)
    
    Returns:
        Updated memory dict
    
    Raises:
        ValueError: If memory not found or update is not significant
    """
    from .agent_memory_db import get_memory, update_memory
    
    # Get existing memory
    existing = get_memory(
        memory_id=memory_id,
        memory_type=memory_type,
        scope_id=scope_id,
        created_at=created_at,
    )
    
    if not existing:
        raise ValueError(f"Memory not found: {memory_id}")
    
    # Check if update is significant (if content is being updated)
    if content is not None:
        existing_content = existing.get("content", "")
        similarity = _calculate_text_similarity(existing_content, content)
        if similarity > 0.95:
            raise ValueError("No significant change detected (similarity > 0.95)")
    
    # Merge metadata intelligently
    existing_metadata = existing.get("metadata", {})
    if not isinstance(existing_metadata, dict):
        existing_metadata = {}
    
    # Get or initialize update history
    update_history = existing_metadata.get("updateHistory", [])
    if not isinstance(update_history, list):
        update_history = []
    
    # Add update entry to history
    update_entry = {
        "timestamp": _now_iso(),
        "reason": reason,
        "previousContent": existing.get("content", "")[:200] if content is not None else None,
    }
    update_history.append(update_entry)
    
    # Merge new metadata with existing
    merged_metadata = dict(existing_metadata)
    if metadata:
        # Deep merge for nested dicts, but allow overwriting for top-level keys
        for key, value in metadata.items():
            if key == "updateHistory":
                continue  # Don't overwrite update history
            if isinstance(value, dict) and isinstance(merged_metadata.get(key), dict):
                merged_metadata[key] = {**merged_metadata[key], **value}
            else:
                merged_metadata[key] = value
    
    # Update updateHistory in merged metadata
    merged_metadata["updateHistory"] = update_history
    
    # Update keywords and tags if content changed
    new_tags = None
    new_keywords = None
    new_summary = None
    
    if content is not None:
        new_keywords = extract_keywords(content)
        new_tags = extract_tags(content, metadata=merged_metadata)
        entities = extract_entities(content)
        new_keywords.extend(entities)
        new_summary = clip_text(content, max_chars=500)
    
    # Update the memory
    updated = update_memory(
        memory_id=memory_id,
        memory_type=memory_type,
        scope_id=scope_id,
        created_at=created_at,
        content=content,
        tags=new_tags,
        keywords=new_keywords,
        metadata=merged_metadata,
        summary=new_summary,
    )
    
    if not updated:
        raise ValueError("Failed to update memory")
    
    # Re-index in OpenSearch (best-effort)
    try:
        from .agent_memory_opensearch import index_memory
        index_memory(updated)
    except Exception:
        pass  # Non-critical
    
    return updated
