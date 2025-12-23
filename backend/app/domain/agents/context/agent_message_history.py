"""
Message history storage and retrieval.

Stores unified message history per user, linking messages to memories.
Enables building context from message history + memories.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ...db.dynamodb.table import DynamoTable, get_table
from ...observability.logging import get_logger
from ...settings import settings

log = get_logger("agent_message_history")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_message_table() -> DynamoTable:
    """
    Get the message history DynamoDB table.
    
    Uses the same table as agent memory for now (can be separated later).
    """
    table_name = settings.agent_memory_table_name
    if not table_name:
        raise ValueError("AGENT_MEMORY_TABLE_NAME is not set")
    return get_table(table_name=table_name)


def _message_key(*, user_sub: str, timestamp: str, message_id: str) -> dict[str, str]:
    """Build the primary key for a message item."""
    pk = f"MESSAGE#{user_sub}"
    sk = f"{timestamp}#{message_id}"
    return {"pk": pk, "sk": sk}


def _normalize_message(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize a message item for API consumption."""
    if not item:
        return None
    out = dict(item)
    # Remove internal DynamoDB keys
    for k in ("pk", "sk", "gsi1pk", "gsi1sk"):
        out.pop(k, None)
    return out


def store_message(
    *,
    user_sub: str,
    role: str,  # "user" or "assistant"
    content: str,
    metadata: dict[str, Any] | None = None,
    linked_memory_id: str | None = None,
) -> dict[str, Any]:
    """
    Store a message in the unified message history.
    
    Args:
        user_sub: User identifier
        role: Message role ("user" or "assistant")
        content: Message content
        metadata: Optional metadata (channel_id, thread_ts, etc.)
        linked_memory_id: Optional memory ID this message is linked to
    
    Returns:
        Created message dict
    """
    if not user_sub or not role or not content:
        raise ValueError("user_sub, role, and content are required")
    
    if role not in ["user", "assistant"]:
        raise ValueError("role must be 'user' or 'assistant'")
    
    message_id = f"msg_{uuid.uuid4().hex[:18]}"
    now = _now_iso()
    timestamp = now
    
    item: dict[str, Any] = {
        **_message_key(user_sub=user_sub, timestamp=timestamp, message_id=message_id),
        "entityType": "AgentMessage",
        "messageId": message_id,
        "userSub": user_sub,
        "role": role,
        "content": str(content)[:20000],  # Max 20KB
        "metadata": metadata if isinstance(metadata, dict) else {},
        "linkedMemoryId": linked_memory_id,
        "timestamp": timestamp,
        "createdAt": timestamp,
        # GSI1: USER#{userSub} / {timestamp}#{messageId} (for querying by user, sorted by time)
        "gsi1pk": f"USER#{user_sub}",
        "gsi1sk": f"{timestamp}#{message_id}",
    }
    
    # Remove None values
    item = {k: v for k, v in item.items() if v is not None}
    
    table = _get_message_table()
    table.put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    
    log.info(
        "message_stored",
        message_id=message_id,
        user_sub=user_sub,
        role=role,
        linked_memory_id=linked_memory_id,
    )
    
    return _normalize_message(item) or {}


def get_recent_messages(
    *,
    user_sub: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get recent messages for a user.
    
    Args:
        user_sub: User identifier
        limit: Maximum number of messages to return
    
    Returns:
        List of message dicts, sorted by timestamp (most recent first)
    """
    table = _get_message_table()
    gsi1pk = f"USER#{user_sub}"
    
    page = table.query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(gsi1pk),
        limit=limit,
        scan_index_forward=False,  # Most recent first
    )
    
    items = [_normalize_message(item) for item in (page.items or [])]
    return [item for item in items if item]


def link_message_to_memory(
    *,
    message_id: str,
    user_sub: str,
    timestamp: str,
    memory_id: str,
) -> bool:
    """
    Link a message to a memory.
    
    Args:
        message_id: Message identifier
        user_sub: User identifier
        timestamp: Message timestamp
        memory_id: Memory identifier to link to
    
    Returns:
        True if successful, False otherwise
    """
    try:
        table = _get_message_table()
        key = _message_key(user_sub=user_sub, timestamp=timestamp, message_id=message_id)
        
        table.update_item(
            key=key,
            update_expression="SET linkedMemoryId = :mid, updatedAt = :u",
            expression_attribute_names=None,
            expression_attribute_values={
                ":mid": memory_id,
                ":u": _now_iso(),
            },
        )
        
        log.debug("message_linked_to_memory", message_id=message_id, memory_id=memory_id)
        return True
    
    except Exception as e:
        log.warning("failed_to_link_message", error=str(e), message_id=message_id, memory_id=memory_id)
        return False


def get_messages_by_memory(
    *,
    memory_id: str,
    user_sub: str,
) -> list[dict[str, Any]]:
    """
    Get messages linked to a specific memory.
    
    Args:
        memory_id: Memory identifier
        user_sub: User identifier
    
    Returns:
        List of message dicts linked to the memory
    """
    # Query all messages for user and filter by linkedMemoryId
    # This is not the most efficient, but works without additional GSI
    all_messages = get_recent_messages(user_sub=user_sub, limit=100)
    
    linked = [msg for msg in all_messages if msg.get("linkedMemoryId") == memory_id]
    return linked
