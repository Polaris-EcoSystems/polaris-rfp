"""
Memory blocks as first-class entities.

Memory blocks are durable, agent-readable entities that agents can reference and edit.
Similar to Letta's memory blocks but integrated with existing memory types.
"""

from __future__ import annotations

from typing import Any

from ..core.agent_memory_db import MemoryType, create_memory, list_memories_by_scope, update_memory
from ..core.agent_memory_keywords import extract_entities, extract_keywords, extract_tags
from ..retrieval.agent_memory_opensearch import index_memory
from ...ai.context import clip_text
from ...observability.logging import get_logger

log = get_logger("agent_memory_blocks")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_memory_block(
    *,
    user_sub: str,
    block_id: str,  # Agent-assigned or auto-generated
    title: str,
    content: str,
    memory_type: str = MemoryType.MEMORY_BLOCK,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
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
    Create a durable memory block that agents can reference and edit.
    
    Args:
        user_sub: User identifier
        block_id: Unique block identifier (must be unique per user)
        title: Block title
        content: Block content
        memory_type: Memory type (defaults to MEMORY_BLOCK)
        tags: Optional tags
        metadata: Optional metadata
        cognito_user_id: Cognito user identifier
        slack_user_id: Slack user ID
        slack_channel_id: Slack channel ID
        slack_thread_ts: Slack thread timestamp
        slack_team_id: Slack team ID
        rfp_id: RFP identifier
        source: Source system
    
    Returns:
        Created memory block dict
    
    Raises:
        ValueError: If block_id already exists for this user
    """
    scope_id = f"USER#{user_sub}"
    
    # Check if block already exists
    existing = get_memory_block(user_sub=user_sub, block_id=block_id)
    if existing:
        raise ValueError(f"Block {block_id} already exists for user {user_sub}")
    
    # Extract keywords and tags
    keywords = extract_keywords(f"{title} {content}")
    entities = extract_entities(content)
    keywords.extend(entities)
    
    if tags is None:
        tags = extract_tags(content, metadata=metadata)
    else:
        # Merge with extracted tags
        extracted_tags = extract_tags(content, metadata=metadata)
        tags = list(dict.fromkeys(tags + extracted_tags))[:25]
    
    # Build metadata with block_id
    block_metadata = {
        "blockId": block_id,
        "title": title,
        "version": 1,
    }
    if metadata:
        block_metadata.update(metadata)
    
    # Create summary
    summary = clip_text(f"{title}: {content}", max_chars=500)
    
    # Use cognito_user_id if not provided
    final_cognito_user_id = cognito_user_id or user_sub
    
    memory = create_memory(
        memory_type=memory_type,
        scope_id=scope_id,
        content=f"{title}\n\n{content}",
        tags=tags,
        keywords=keywords,
        metadata=block_metadata,
        summary=summary,
        cognito_user_id=final_cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        slack_team_id=slack_team_id,
        rfp_id=rfp_id,
        source=source or "memory_block",
    )
    
    # Index in OpenSearch
    try:
        index_memory(memory)
    except Exception:
        pass  # Non-critical
    
    return memory


def get_memory_block(
    *,
    user_sub: str,
    block_id: str,
) -> dict[str, Any] | None:
    """
    Get a memory block by block_id.
    
    Args:
        user_sub: User identifier
        block_id: Block identifier
    
    Returns:
        Memory block dict or None if not found
    """
    scope_id = f"USER#{user_sub}"
    
    # Query memories by scope and filter by block_id in metadata
    # This is not the most efficient, but works without schema changes
    memories, _ = list_memories_by_scope(
        scope_id=scope_id,
        memory_type=MemoryType.MEMORY_BLOCK,
        limit=100,
    )
    
    for memory in memories:
        metadata = memory.get("metadata", {})
        if isinstance(metadata, dict) and metadata.get("blockId") == block_id:
            return memory
    
    return None


def update_memory_block(
    *,
    user_sub: str,
    block_id: str,
    content: str | None = None,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Update an existing memory block.
    
    Tracks version history in metadata.
    
    Args:
        user_sub: User identifier
        block_id: Block identifier
        content: New content (optional)
        title: New title (optional)
        metadata: New metadata to merge (optional)
    
    Returns:
        Updated memory block dict
    
    Raises:
        ValueError: If block not found
    """
    existing = get_memory_block(user_sub=user_sub, block_id=block_id)
    if not existing:
        raise ValueError(f"Block {block_id} not found for user {user_sub}")
    
    memory_id = existing.get("memoryId")
    memory_type = existing.get("memoryType", MemoryType.MEMORY_BLOCK)
    scope_id = existing.get("scopeId", f"USER#{user_sub}")
    created_at = existing.get("createdAt", "")
    
    if not memory_id or not created_at:
        raise ValueError("Invalid memory block structure")
    
    # Get existing metadata
    existing_metadata = existing.get("metadata", {})
    if not isinstance(existing_metadata, dict):
        existing_metadata = {}
    
    # Get version history
    version_history = existing_metadata.get("versionHistory", [])
    if not isinstance(version_history, list):
        version_history = []
    
    # Get current version
    current_version = existing_metadata.get("version", 1)
    
    # Determine new content and title
    new_content = content if content is not None else existing.get("content", "")
    new_title = title if title is not None else existing_metadata.get("title", "")
    
    # Extract title from content if content starts with title
    if new_content and "\n\n" in new_content:
        parts = new_content.split("\n\n", 1)
        if not new_title and len(parts) == 2:
            new_title = parts[0]
            new_content = parts[1]
    
    # Add version entry to history
    version_entry = {
        "version": current_version,
        "timestamp": _now_iso(),
        "title": existing_metadata.get("title", ""),
        "contentPreview": existing.get("content", "")[:200],
    }
    version_history.append(version_entry)
    
    # Merge metadata
    merged_metadata = dict(existing_metadata)
    merged_metadata["version"] = current_version + 1
    merged_metadata["title"] = new_title
    merged_metadata["versionHistory"] = version_history
    if metadata:
        # Deep merge for nested dicts
        for key, value in metadata.items():
            if key in ["version", "versionHistory", "blockId"]:
                continue  # Don't overwrite these
            if isinstance(value, dict) and isinstance(merged_metadata.get(key), dict):
                merged_metadata[key] = {**merged_metadata[key], **value}
            else:
                merged_metadata[key] = value
    
    # Update keywords and tags if content changed
    new_tags = None
    new_keywords = None
    new_summary = None
    
    if content is not None or title is not None:
        full_content = f"{new_title}\n\n{new_content}"
        new_keywords = extract_keywords(full_content)
        entities = extract_entities(new_content)
        new_keywords.extend(entities)
        new_tags = extract_tags(new_content, metadata=merged_metadata)
        new_summary = clip_text(f"{new_title}: {new_content}", max_chars=500)
    
    # Update the memory
    updated = update_memory(
        memory_id=memory_id,
        memory_type=memory_type,
        scope_id=scope_id,
        created_at=created_at,
        content=f"{new_title}\n\n{new_content}" if content is not None or title is not None else None,
        tags=new_tags,
        keywords=new_keywords,
        metadata=merged_metadata,
        summary=new_summary,
    )
    
    if not updated:
        raise ValueError("Failed to update memory block")
    
    # Re-index in OpenSearch
    try:
        index_memory(updated)
    except Exception:
        pass  # Non-critical
    
    return updated


def list_memory_blocks(
    *,
    user_sub: str,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """
    List all memory blocks for a user.
    
    Args:
        user_sub: User identifier
        limit: Maximum number of blocks to return
    
    Returns:
        List of memory block dicts
    """
    scope_id = f"USER#{user_sub}"
    
    memories, _ = list_memories_by_scope(
        scope_id=scope_id,
        memory_type=MemoryType.MEMORY_BLOCK,
        limit=limit,
    )
    
    return memories
