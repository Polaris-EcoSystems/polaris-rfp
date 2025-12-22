from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import DynamoTable, get_table
from ..observability.logging import get_logger
from ..settings import settings

log = get_logger("agent_memory_db")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MemoryType:
    """Memory type constants."""
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"
    TOOL_PATTERN = "TOOL_PATTERN"
    WORKFLOW = "WORKFLOW"
    CONTEXT_PATTERN = "CONTEXT_PATTERN"
    DIAGNOSTICS = "DIAGNOSTICS"
    EXTERNAL_CONTEXT = "EXTERNAL_CONTEXT"  # Real-world context (news, weather, events, research)
    COLLABORATION_CONTEXT = "COLLABORATION_CONTEXT"  # Team interaction patterns and collaboration context
    TEMPORAL_EVENT = "TEMPORAL_EVENT"  # Time-indexed events and milestones
    ERROR_LOG = "ERROR_LOG"  # Tool/function call errors for debugging and learning
    MEMORY_BLOCK = "MEMORY_BLOCK"  # Durable, editable memory blocks


def _get_memory_table() -> DynamoTable:
    """
    Get the agent memory DynamoDB table.
    
    Raises:
        ValueError: If AGENT_MEMORY_TABLE_NAME is not configured
    """
    table_name = settings.agent_memory_table_name
    if not table_name:
        raise ValueError("AGENT_MEMORY_TABLE_NAME is not set")
    return get_table(table_name=table_name)


def _memory_key(*, memory_type: str, scope_id: str, created_at: str, memory_id: str) -> dict[str, str]:
    """Build the primary key for a memory item."""
    pk = f"MEMORY#{memory_type}#{scope_id}"
    sk = f"{created_at}#{memory_id}"
    return {"pk": pk, "sk": sk}


def _normalize_memory(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize a memory item for API consumption (remove internal keys)."""
    if not item:
        return None
    out = dict(item)
    # Remove internal DynamoDB keys
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk"):
        out.pop(k, None)
    return out


def create_memory(
    *,
    memory_type: str,
    scope_id: str,
    content: str,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    summary: str | None = None,
    compressed: bool = False,
    original_memory_ids: list[str] | None = None,
    related_memory_ids: list[str] | None = None,
    expires_at: int | None = None,
    # Provenance/traceability fields
    cognito_user_id: str | None = None,
    slack_user_id: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    slack_team_id: str | None = None,
    rfp_id: str | None = None,
    source: str | None = None,  # e.g., "slack_agent", "slack_operator", "api", "migration"
) -> dict[str, Any]:
    """
    Create a new memory entry with full provenance tracking.
    
    Args:
        memory_type: One of MemoryType constants
        scope_id: Scope identifier (USER#{userSub}, RFP#{rfpId}, TENANT#{tenantId}, GLOBAL)
        content: Main memory content (text, max 20KB)
        tags: Array of tags for categorization
        keywords: Array of extracted keywords for search
        metadata: Contextual metadata
        summary: Optional short summary (max 500 chars)
        compressed: Boolean flag indicating if this is a compressed/summarized memory
        original_memory_ids: List of IDs if this memory is a compression of others
        related_memory_ids: Links to related memories
        expires_at: TTL timestamp (Unix epoch in seconds)
        cognito_user_id: Cognito user identifier (sub) for traceability
        slack_user_id: Slack user ID for traceability
        slack_channel_id: Slack channel ID where memory originated
        slack_thread_ts: Slack thread timestamp where memory originated
        slack_team_id: Slack team ID
        rfp_id: RFP identifier if memory is related to an RFP
        source: Source system (e.g., "slack_agent", "slack_operator", "api", "migration")
    
    Returns:
        Normalized memory dict
    """
    if not memory_type or not scope_id or not content:
        raise ValueError("memory_type, scope_id, and content are required")
    
    memory_id = f"mem_{uuid.uuid4().hex[:18]}"
    now = _now_iso()
    
    # Build provenance metadata
    provenance: dict[str, Any] = {}
    if cognito_user_id:
        provenance["cognitoUserId"] = str(cognito_user_id).strip()
    if slack_user_id:
        provenance["slackUserId"] = str(slack_user_id).strip()
    if slack_channel_id:
        provenance["slackChannelId"] = str(slack_channel_id).strip()
    if slack_thread_ts:
        provenance["slackThreadTs"] = str(slack_thread_ts).strip()
    if slack_team_id:
        provenance["slackTeamId"] = str(slack_team_id).strip()
    if rfp_id:
        provenance["rfpId"] = str(rfp_id).strip()
    if source:
        provenance["source"] = str(source).strip()
    
    # Merge provenance into metadata if provided, otherwise create new metadata
    final_metadata = metadata if isinstance(metadata, dict) else {}
    if provenance:
        final_metadata = {**final_metadata, "provenance": provenance}
    
    item: dict[str, Any] = {
        **_memory_key(memory_type=memory_type, scope_id=scope_id, created_at=now, memory_id=memory_id),
        "entityType": "AgentMemory",
        "memoryId": memory_id,
        "memoryType": memory_type,
        "scopeId": scope_id,
        "content": str(content)[:20000],  # Max 20KB
        "tags": [str(t).strip().lower() for t in (tags or []) if str(t).strip()][:25],
        "keywords": [str(k).strip().lower() for k in (keywords or []) if str(k).strip()][:50],
        "metadata": final_metadata,
        "summary": str(summary)[:500] if summary else None,
        "compressed": bool(compressed),
        "originalMemoryIds": [str(mid) for mid in (original_memory_ids or [])][:20],
        "relatedMemoryIds": [str(mid) for mid in (related_memory_ids or [])][:20],
        "accessCount": 0,
        "lastAccessedAt": now,
        "createdAt": now,
        "updatedAt": now,
        # Provenance fields (also stored at top level for easy querying)
        "cognitoUserId": cognito_user_id,
        "slackUserId": slack_user_id,
        "slackChannelId": slack_channel_id,
        "slackThreadTs": slack_thread_ts,
        "slackTeamId": slack_team_id,
        "rfpId": rfp_id,
        "source": source,
        # GSI1: SEARCH#{scopeId} / {lastAccessedAt}#{memoryId}
        "gsi1pk": f"SEARCH#{scope_id}",
        "gsi1sk": f"{now}#{memory_id}",
        # GSI2: TYPE#{memoryType} / {createdAt}#{memoryId}
        "gsi2pk": f"TYPE#{memory_type}",
        "gsi2sk": f"{now}#{memory_id}",
    }
    
    if expires_at:
        item["expiresAt"] = expires_at
    
    # Remove None values
    item = {k: v for k, v in item.items() if v is not None}
    
    table = _get_memory_table()
    table.put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    
    log.info(
        "memory_created",
        memory_id=memory_id,
        memory_type=memory_type,
        scope_id=scope_id,
        cognito_user_id=cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        rfp_id=rfp_id,
        source=source,
    )
    
    return _normalize_memory(item) or {}


def get_memory(*, memory_id: str, memory_type: str, scope_id: str, created_at: str) -> dict[str, Any] | None:
    """
    Get a memory by its ID and creation timestamp.
    
    Args:
        memory_id: Unique memory identifier (mem_*)
        memory_type: Memory type (one of MemoryType constants)
        scope_id: Scope identifier (USER#{userSub}, RFP#{rfpId}, etc.)
        created_at: ISO timestamp when memory was created (used in sort key)
    
    Returns:
        Normalized memory dict or None if not found
    """
    table = _get_memory_table()
    key = _memory_key(memory_type=memory_type, scope_id=scope_id, created_at=created_at, memory_id=memory_id)
    item = table.get_item(key=key)
    return _normalize_memory(item)


def update_memory_access(*, memory_id: str, memory_type: str, scope_id: str, created_at: str) -> dict[str, Any] | None:
    """
    Update access count and last accessed timestamp for a memory.
    
    This updates the access tracking fields used for relevance scoring.
    Also updates GSI1 sort key to reflect new lastAccessedAt timestamp.
    
    Args:
        memory_id: Unique memory identifier
        memory_type: Memory type
        scope_id: Scope identifier
        created_at: ISO timestamp when memory was created
    
    Returns:
        Updated memory dict or None if not found
    """
    table = _get_memory_table()
    key = _memory_key(memory_type=memory_type, scope_id=scope_id, created_at=created_at, memory_id=memory_id)
    now = _now_iso()
    
    updated = table.update_item(
        key=key,
        update_expression="SET accessCount = accessCount + :inc, lastAccessedAt = :la, updatedAt = :u, gsi1sk = :gsi1sk",
        expression_attribute_names=None,
        expression_attribute_values={
            ":inc": 1,
            ":la": now,
            ":u": now,
            ":gsi1sk": f"{now}#{memory_id}",
        },
        return_values="ALL_NEW",
    )
    return _normalize_memory(updated)


def list_memories_by_scope(
    *,
    scope_id: str,
    memory_type: str | None = None,
    limit: int = 50,
    next_token: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    List memories by scope, optionally filtered by type.
    Uses GSI1 for scope-based queries with recency ordering.
    """
    table = _get_memory_table()
    gsi1pk = f"SEARCH#{scope_id}"
    
    if memory_type:
        # Query by scope, then filter by type
        page = table.query_page(
            index_name="GSI1",
            key_condition_expression=Key("gsi1pk").eq(gsi1pk),
            filter_expression=Key("memoryType").eq(memory_type) if memory_type else None,
            limit=limit,
            scan_index_forward=False,  # Most recent first
            next_token=next_token,
        )
    else:
        page = table.query_page(
            index_name="GSI1",
            key_condition_expression=Key("gsi1pk").eq(gsi1pk),
            limit=limit,
            scan_index_forward=False,  # Most recent first
            next_token=next_token,
        )
    
    items = [_normalize_memory(item) for item in (page.items or [])]
    return [item for item in items if item], page.next_token


def list_memories_by_type(
    *,
    memory_type: str,
    scope_id: str | None = None,
    limit: int = 50,
    next_token: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    List memories by type, optionally filtered by scope.
    Uses GSI2 for type-based queries.
    """
    table = _get_memory_table()
    gsi2pk = f"TYPE#{memory_type}"
    
    if scope_id:
        # Query by type, then filter by scope
        page = table.query_page(
            index_name="GSI2",
            key_condition_expression=Key("gsi2pk").eq(gsi2pk),
            filter_expression=Key("scopeId").eq(scope_id) if scope_id else None,
            limit=limit,
            scan_index_forward=False,  # Most recent first
            next_token=next_token,
        )
    else:
        page = table.query_page(
            index_name="GSI2",
            key_condition_expression=Key("gsi2pk").eq(gsi2pk),
            limit=limit,
            scan_index_forward=False,  # Most recent first
            next_token=next_token,
        )
    
    items = [_normalize_memory(item) for item in (page.items or [])]
    return [item for item in items if item], page.next_token


def update_memory(
    *,
    memory_id: str,
    memory_type: str,
    scope_id: str,
    created_at: str,
    content: str | None = None,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    summary: str | None = None,
    expires_at: int | None = None,
) -> dict[str, Any] | None:
    """Update an existing memory."""
    table = _get_memory_table()
    key = _memory_key(memory_type=memory_type, scope_id=scope_id, created_at=created_at, memory_id=memory_id)
    now = _now_iso()
    
    update_parts: list[str] = ["updatedAt = :u"]
    expr_values: dict[str, Any] = {":u": now}
    
    if content is not None:
        update_parts.append("content = :content")
        expr_values[":content"] = str(content)[:20000]
    
    if tags is not None:
        update_parts.append("tags = :tags")
        expr_values[":tags"] = [str(t).strip().lower() for t in tags if str(t).strip()][:25]
    
    if keywords is not None:
        update_parts.append("keywords = :keywords")
        expr_values[":keywords"] = [str(k).strip().lower() for k in keywords if str(k).strip()][:50]
    
    if metadata is not None:
        update_parts.append("metadata = :metadata")
        expr_values[":metadata"] = metadata if isinstance(metadata, dict) else {}
    
    if summary is not None:
        update_parts.append("summary = :summary")
        expr_values[":summary"] = str(summary)[:500] if summary else None
    
    if expires_at is not None:
        update_parts.append("expiresAt = :exp")
        expr_values[":exp"] = int(expires_at)
    
    update_expr = "SET " + ", ".join(update_parts)
    
    updated = table.update_item(
        key=key,
        update_expression=update_expr,
        expression_attribute_names=None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )
    return _normalize_memory(updated)


def find_memory_by_id(
    *,
    memory_id: str,
    scope_ids: list[str] | None = None,
    memory_types: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Find a memory by its ID across multiple scopes.
    
    This is less efficient than get_memory() but useful when you only have the memory_id.
    Searches across provided scopes or common scopes if not specified.
    
    Args:
        memory_id: Memory identifier to find
        scope_ids: Optional list of scope IDs to search (if None, searches common scopes)
        memory_types: Optional list of memory types to search (if None, searches all types)
    
    Returns:
        Memory dict if found, None otherwise
    """
    if not memory_id:
        return None
    
    # Default scopes to search if not provided
    if not scope_ids:
        scope_ids = []  # Will search by type only if no scopes provided
    
    # Default memory types if not provided
    if not memory_types:
        memory_types = [
            MemoryType.EPISODIC,
            MemoryType.SEMANTIC,
            MemoryType.PROCEDURAL,
            MemoryType.MEMORY_BLOCK,
        ]
    
    # Search by type across all scopes (or globally if no scopes)
    for memory_type in memory_types:
        if scope_ids:
            # Search in specific scopes
            for scope_id in scope_ids:
                memories, _ = list_memories_by_scope(
                    scope_id=scope_id,
                    memory_type=memory_type,
                    limit=100,
                )
                for mem in memories:
                    if mem.get("memoryId") == memory_id:
                        return mem
        else:
            # Search by type globally
            memories, _ = list_memories_by_type(
                memory_type=memory_type,
                limit=100,
            )
            for mem in memories:
                if mem.get("memoryId") == memory_id:
                    return mem
    
    return None


def delete_memory(*, memory_id: str, memory_type: str, scope_id: str, created_at: str) -> None:
    """
    Delete a memory from DynamoDB.
    
    Note: This does NOT delete from OpenSearch index. Use agent_memory_opensearch.delete_memory_index()
    separately if you need to remove from search index as well.
    
    Args:
        memory_id: Unique memory identifier
        memory_type: Memory type
        scope_id: Scope identifier
        created_at: ISO timestamp when memory was created
    """
    table = _get_memory_table()
    key = _memory_key(memory_type=memory_type, scope_id=scope_id, created_at=created_at, memory_id=memory_id)
    table.delete_item(key=key)
