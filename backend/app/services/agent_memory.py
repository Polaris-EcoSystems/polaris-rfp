from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..ai.context import clip_text
from .agent_memory_db import MemoryType, create_memory, list_memories_by_scope
from .agent_memory_keywords import extract_entities, extract_keywords, extract_tags
from .agent_memory_opensearch import index_memory
from .agent_memory_retrieval import get_memories_for_context, retrieve_relevant_memories


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
