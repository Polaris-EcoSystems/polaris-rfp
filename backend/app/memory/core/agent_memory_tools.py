from __future__ import annotations

from typing import Any

from .agent_memory import (
    add_episodic_memory,
    add_procedural_memory,
    format_memory_for_context,
    update_existing_memory,
    update_semantic_memory,
)
from ..blocks.agent_memory_blocks import (
    create_memory_block,
    get_memory_block,
    list_memory_blocks,
    update_memory_block,
)
from ..relationships.agent_memory_relationships import get_related_memories, retrieve_with_relationships
from ..retrieval.agent_memory_retrieval import get_memories_for_context, retrieve_relevant_memories


def _memory_store_episodic_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Store an episodic memory (conversation, decision, outcome) with full provenance.
    
    Args:
        userSub: User identifier (Cognito sub)
        content: Memory content
        context: Optional context dict (conversationContext, userMessage, agentAction, outcome, etc.)
        scopeId: Optional scope override (defaults to USER#{userSub})
        cognitoUserId: Optional Cognito user ID (defaults to userSub)
        slackUserId: Optional Slack user ID
        slackChannelId: Optional Slack channel ID
        slackThreadTs: Optional Slack thread timestamp
        slackTeamId: Optional Slack team ID
        rfpId: Optional RFP identifier
        source: Optional source system (defaults to "agent_tool")
    """
    user_sub = str(args.get("userSub") or "").strip()
    if not user_sub:
        return {"ok": False, "error": "missing_userSub"}
    
    content = str(args.get("content") or "").strip()
    if not content:
        return {"ok": False, "error": "missing_content"}
    
    context = args.get("context") if isinstance(args.get("context"), dict) else None
    
    # Extract provenance fields from args
    cognito_user_id = str(args.get("cognitoUserId") or "").strip() or None
    slack_user_id = str(args.get("slackUserId") or "").strip() or None
    slack_channel_id = str(args.get("slackChannelId") or "").strip() or None
    slack_thread_ts = str(args.get("slackThreadTs") or "").strip() or None
    slack_team_id = str(args.get("slackTeamId") or "").strip() or None
    rfp_id = str(args.get("rfpId") or "").strip() or None
    source = str(args.get("source") or "agent_tool").strip()
    
    try:
        memory = add_episodic_memory(
            user_sub=user_sub,
            content=content,
            context=context,
            cognito_user_id=cognito_user_id,
            slack_user_id=slack_user_id,
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
            slack_team_id=slack_team_id,
            rfp_id=rfp_id,
            source=source,
        )
        return {"ok": True, "memory": memory}
    except Exception as e:
        return {"ok": False, "error": str(e) or "memory_store_failed"}


def _memory_store_semantic_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Store a semantic memory (preference, knowledge, pattern) with full provenance.
    
    Args:
        userSub: User identifier (Cognito sub)
        key: Preference/keyword
        value: Preference value or knowledge fact
        scopeId: Optional scope override
        cognitoUserId: Optional Cognito user ID (defaults to userSub)
        slackUserId: Optional Slack user ID
        slackChannelId: Optional Slack channel ID
        slackThreadTs: Optional Slack thread timestamp
        slackTeamId: Optional Slack team ID
        rfpId: Optional RFP identifier
        source: Optional source system (defaults to "agent_tool")
    """
    user_sub = str(args.get("userSub") or "").strip()
    if not user_sub:
        return {"ok": False, "error": "missing_userSub"}
    
    key = str(args.get("key") or "").strip()
    if not key:
        return {"ok": False, "error": "missing_key"}
    
    value = args.get("value")
    
    # Extract provenance fields from args
    cognito_user_id = str(args.get("cognitoUserId") or "").strip() or None
    slack_user_id = str(args.get("slackUserId") or "").strip() or None
    slack_channel_id = str(args.get("slackChannelId") or "").strip() or None
    slack_thread_ts = str(args.get("slackThreadTs") or "").strip() or None
    slack_team_id = str(args.get("slackTeamId") or "").strip() or None
    rfp_id = str(args.get("rfpId") or "").strip() or None
    source = str(args.get("source") or "agent_tool").strip()
    
    try:
        memory = update_semantic_memory(
            user_sub=user_sub,
            key=key,
            value=value,
            cognito_user_id=cognito_user_id,
            slack_user_id=slack_user_id,
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
            slack_team_id=slack_team_id,
            rfp_id=rfp_id,
            source=source,
        )
        return {"ok": True, "memory": memory}
    except Exception as e:
        return {"ok": False, "error": str(e) or "memory_store_failed"}


def _memory_store_procedural_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Store a procedural memory (workflow, tool usage pattern) with full provenance.
    
    Args:
        userSub: User identifier (Cognito sub)
        workflow: Workflow description or name
        success: Whether the workflow was successful
        context: Optional context (toolSequence, successCriteria, etc.)
        cognitoUserId: Optional Cognito user ID (defaults to userSub)
        slackUserId: Optional Slack user ID
        slackChannelId: Optional Slack channel ID
        slackThreadTs: Optional Slack thread timestamp
        slackTeamId: Optional Slack team ID
        rfpId: Optional RFP identifier
        source: Optional source system (defaults to "agent_tool")
    """
    user_sub = str(args.get("userSub") or "").strip()
    if not user_sub:
        return {"ok": False, "error": "missing_userSub"}
    
    workflow = str(args.get("workflow") or "").strip()
    if not workflow:
        return {"ok": False, "error": "missing_workflow"}
    
    success = bool(args.get("success", True))
    context = args.get("context") if isinstance(args.get("context"), dict) else None
    
    # Extract provenance fields from args
    cognito_user_id = str(args.get("cognitoUserId") or "").strip() or None
    slack_user_id = str(args.get("slackUserId") or "").strip() or None
    slack_channel_id = str(args.get("slackChannelId") or "").strip() or None
    slack_thread_ts = str(args.get("slackThreadTs") or "").strip() or None
    slack_team_id = str(args.get("slackTeamId") or "").strip() or None
    rfp_id = str(args.get("rfpId") or "").strip() or None
    source = str(args.get("source") or "agent_tool").strip()
    
    try:
        memory = add_procedural_memory(
            user_sub=user_sub,
            workflow=workflow,
            success=success,
            context=context,
            cognito_user_id=cognito_user_id,
            slack_user_id=slack_user_id,
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
            slack_team_id=slack_team_id,
            rfp_id=rfp_id,
            source=source,
        )
        return {"ok": True, "memory": memory}
    except Exception as e:
        return {"ok": False, "error": str(e) or "memory_store_failed"}


def _agent_memory_search_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Search agent memories for relevant entries.
    
    Args:
        userSub: User identifier (optional if scopeId provided)
        query: Search query text
        memoryTypes: Optional list of memory types to search (EPISODIC, SEMANTIC, PROCEDURAL)
        scopeId: Optional scope override
        rfpId: Optional RFP identifier (alternative to userSub)
        tenantId: Optional tenant identifier
        limit: Maximum number of results (default 10)
    """
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "missing_query"}
    
    user_sub = str(args.get("userSub") or "").strip() or None
    scope_id = str(args.get("scopeId") or "").strip() or None
    rfp_id = str(args.get("rfpId") or "").strip() or None
    tenant_id = str(args.get("tenantId") or "").strip() or None
    
    # Determine scope
    if scope_id:
        pass  # Use provided scope_id
    elif rfp_id:
        scope_id = f"RFP#{rfp_id}"
    elif user_sub:
        scope_id = f"USER#{user_sub}"
    elif tenant_id:
        scope_id = f"TENANT#{tenant_id}"
    else:
        return {"ok": False, "error": "missing_scope (provide userSub, rfpId, tenantId, or scopeId)"}
    
    memory_types_raw = args.get("memoryTypes")
    memory_types: list[str] | None = None
    if isinstance(memory_types_raw, list):
        memory_types = [str(mt).strip().upper() for mt in memory_types_raw if str(mt).strip()]
    
    limit = max(1, min(50, int(args.get("limit") or 10)))
    
    try:
        results = retrieve_relevant_memories(
            scope_id=scope_id,
            memory_types=memory_types,
            query_text=query,
            limit=limit,
        )
        return {"ok": True, "query": query, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "memory_search_failed"}


def _memory_update_block_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing memory block with new information.
    
    Args:
        memoryId: Memory identifier
        memoryType: Memory type (EPISODIC, SEMANTIC, PROCEDURAL, etc.)
        scopeId: Scope identifier (USER#{userSub}, RFP#{rfpId}, etc.)
        createdAt: Original creation timestamp (ISO format)
        content: New content (optional)
        metadata: New metadata to merge (optional)
        reason: Reason for the update (defaults to "Information update")
        userSub: User identifier (optional, for provenance)
    """
    memory_id = str(args.get("memoryId") or "").strip()
    if not memory_id:
        return {"ok": False, "error": "missing_memoryId"}
    
    memory_type = str(args.get("memoryType") or "").strip()
    if not memory_type:
        return {"ok": False, "error": "missing_memoryType"}
    
    scope_id = str(args.get("scopeId") or "").strip()
    if not scope_id:
        return {"ok": False, "error": "missing_scopeId"}
    
    created_at = str(args.get("createdAt") or "").strip()
    if not created_at:
        return {"ok": False, "error": "missing_createdAt"}
    
    content = str(args.get("content") or "").strip() or None
    metadata = args.get("metadata") if isinstance(args.get("metadata"), dict) else None
    reason = str(args.get("reason") or "Information update").strip()
    user_sub = str(args.get("userSub") or "").strip() or None
    
    try:
        updated = update_existing_memory(
            memory_id=memory_id,
            memory_type=memory_type,
            scope_id=scope_id,
            created_at=created_at,
            content=content,
            metadata=metadata,
            reason=reason,
            user_sub=user_sub,
        )
        return {"ok": True, "memory": updated}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "memory_update_failed"}


def _memory_create_block_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Create a new memory block.
    
    Args:
        userSub: User identifier
        blockId: Unique block identifier
        title: Block title
        content: Block content
        tags: Optional tags
        metadata: Optional metadata
    """
    user_sub = str(args.get("userSub") or "").strip()
    if not user_sub:
        return {"ok": False, "error": "missing_userSub"}
    
    block_id = str(args.get("blockId") or "").strip()
    if not block_id:
        return {"ok": False, "error": "missing_blockId"}
    
    title = str(args.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "missing_title"}
    
    content = str(args.get("content") or "").strip()
    if not content:
        return {"ok": False, "error": "missing_content"}
    
    tags = args.get("tags")
    if isinstance(tags, list):
        tags = [str(t).strip() for t in tags if str(t).strip()]
    else:
        tags = None
    
    metadata = args.get("metadata") if isinstance(args.get("metadata"), dict) else None
    
    try:
        block = create_memory_block(
            user_sub=user_sub,
            block_id=block_id,
            title=title,
            content=content,
            tags=tags,
            metadata=metadata,
        )
        return {"ok": True, "block": block}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "block_create_failed"}


def _memory_get_block_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get a memory block by block_id.
    
    Args:
        userSub: User identifier
        blockId: Block identifier
    """
    user_sub = str(args.get("userSub") or "").strip()
    if not user_sub:
        return {"ok": False, "error": "missing_userSub"}
    
    block_id = str(args.get("blockId") or "").strip()
    if not block_id:
        return {"ok": False, "error": "missing_blockId"}
    
    try:
        block = get_memory_block(user_sub=user_sub, block_id=block_id)
        if block:
            return {"ok": True, "block": block}
        else:
            return {"ok": False, "error": "block_not_found"}
    except Exception as e:
        return {"ok": False, "error": str(e) or "block_get_failed"}


def _memory_update_block_tool_wrapper(args: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing memory block.
    
    Args:
        userSub: User identifier
        blockId: Block identifier
        content: New content (optional)
        title: New title (optional)
        metadata: New metadata to merge (optional)
    """
    user_sub = str(args.get("userSub") or "").strip()
    if not user_sub:
        return {"ok": False, "error": "missing_userSub"}
    
    block_id = str(args.get("blockId") or "").strip()
    if not block_id:
        return {"ok": False, "error": "missing_blockId"}
    
    content = str(args.get("content") or "").strip() or None
    title = str(args.get("title") or "").strip() or None
    metadata = args.get("metadata") if isinstance(args.get("metadata"), dict) else None
    
    try:
        updated = update_memory_block(
            user_sub=user_sub,
            block_id=block_id,
            content=content,
            title=title,
            metadata=metadata,
        )
        return {"ok": True, "block": updated}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "block_update_failed"}


def _memory_list_blocks_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    List all memory blocks for a user.
    
    Args:
        userSub: User identifier
        limit: Maximum number of blocks (default 25)
    """
    user_sub = str(args.get("userSub") or "").strip()
    if not user_sub:
        return {"ok": False, "error": "missing_userSub"}
    
    limit = max(1, min(100, int(args.get("limit") or 25)))
    
    try:
        blocks = list_memory_blocks(user_sub=user_sub, limit=limit)
        return {"ok": True, "blocks": blocks, "count": len(blocks)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "block_list_failed"}


def _memory_get_related_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get memories related to a given memory using relationship graph.
    
    Args:
        memoryId: Source memory ID
        memoryType: Source memory type
        scopeId: Source memory scope
        createdAt: Source memory created_at timestamp
        relationshipType: Optional filter by relationship type
        depth: Maximum traversal depth (default 1)
        limit: Maximum number of results
    """
    memory_id = str(args.get("memoryId") or "").strip()
    if not memory_id:
        return {"ok": False, "error": "missing_memoryId"}
    
    memory_type = str(args.get("memoryType") or "").strip()
    if not memory_type:
        return {"ok": False, "error": "missing_memoryType"}
    
    scope_id = str(args.get("scopeId") or "").strip()
    if not scope_id:
        return {"ok": False, "error": "missing_scopeId"}
    
    created_at = str(args.get("createdAt") or "").strip()
    if not created_at:
        return {"ok": False, "error": "missing_createdAt"}
    
    relationship_type = str(args.get("relationshipType") or "").strip() or None
    depth = max(1, min(3, int(args.get("depth") or 1)))
    limit = max(1, min(50, int(args.get("limit") or 20)))
    
    try:
        if depth > 1:
            results = retrieve_with_relationships(
                memory_id=memory_id,
                memory_type=memory_type,
                scope_id=scope_id,
                created_at=created_at,
                relationship_types=[relationship_type] if relationship_type else None,
                depth=depth,
            )
        else:
            results = get_related_memories(
                memory_id=memory_id,
                memory_type=memory_type,
                scope_id=scope_id,
                created_at=created_at,
                relationship_type=relationship_type,
                limit=limit,
            )
        
        return {"ok": True, "related_memories": results[:limit], "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "relationship_retrieval_failed"}


def _agent_memory_get_context_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get relevant memories formatted for agent context.
    
    Args:
        userSub: User identifier (optional if scopeId provided)
        scopeId: Optional scope override
        rfpId: Optional RFP identifier
        tenantId: Optional tenant identifier
        queryText: Optional search query to filter memories
        memoryTypes: Optional list of memory types
        limit: Maximum number of memories (default 15)
        maxChars: Maximum characters in formatted output (default 2000)
    """
    user_sub = str(args.get("userSub") or "").strip() or None
    rfp_id = str(args.get("rfpId") or "").strip() or None
    tenant_id = str(args.get("tenantId") or "").strip() or None
    query_text = str(args.get("queryText") or "").strip() or None
    limit = max(1, min(50, int(args.get("limit") or 15)))
    
    memory_types_raw = args.get("memoryTypes")
    memory_types: list[str] | None = None
    if isinstance(memory_types_raw, list):
        memory_types = [str(mt).strip().upper() for mt in memory_types_raw if str(mt).strip()]
    
    try:
        memories = get_memories_for_context(
            user_sub=user_sub,
            rfp_id=rfp_id,
            tenant_id=tenant_id,
            query_text=query_text,
            memory_types=memory_types,
            limit=limit,
        )
        
        # Format for context
        if user_sub:
            formatted = format_memory_for_context(user_sub=user_sub, max_chars=int(args.get("maxChars") or 2000))
        else:
            # Manual formatting if no user_sub
            lines: list[str] = []
            for mem in memories[:limit]:
                mem_type = mem.get("memoryType", "")
                summary = mem.get("summary") or mem.get("content", "")
                lines.append(f"[{mem_type}] {summary[:200]}")
            formatted = "\n".join(lines)
        
        return {
            "ok": True,
            "memories": memories,
            "formatted": formatted,
            "count": len(memories),
        }
    except Exception as e:
        return {"ok": False, "error": str(e) or "memory_get_context_failed"}


# Tool definitions for agent use
def get_memory_tools() -> dict[str, tuple[dict[str, Any], Any]]:
    """
    Get memory-related tools for agent use.
    
    Returns:
        Dict of tool name -> (tool_def, tool_fn)
    """
    def tool_def(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": parameters,
        }
    
    return {
        "agent_memory_store_episodic": (
            tool_def(
                "agent_memory_store_episodic",
                "Store an episodic memory in the new structured memory system (conversation, decision, outcome).",
                {
                    "type": "object",
                    "properties": {
                        "userSub": {"type": "string", "minLength": 1, "maxLength": 120},
                        "content": {"type": "string", "minLength": 1, "maxLength": 20000},
                        "context": {"type": "object", "description": "Optional context (conversationContext, userMessage, agentAction, outcome, etc.)"},
                        "scopeId": {"type": "string", "maxLength": 200, "description": "Optional scope override (defaults to USER#{userSub})"},
                        "cognitoUserId": {"type": "string", "maxLength": 200, "description": "Optional Cognito user ID (defaults to userSub)"},
                        "slackUserId": {"type": "string", "maxLength": 40, "description": "Optional Slack user ID for traceability"},
                        "slackChannelId": {"type": "string", "maxLength": 40, "description": "Optional Slack channel ID where memory originated"},
                        "slackThreadTs": {"type": "string", "maxLength": 40, "description": "Optional Slack thread timestamp where memory originated"},
                        "slackTeamId": {"type": "string", "maxLength": 40, "description": "Optional Slack team ID"},
                        "rfpId": {"type": "string", "maxLength": 120, "description": "Optional RFP identifier"},
                        "source": {"type": "string", "maxLength": 100, "description": "Optional source system (defaults to 'agent_tool')"},
                    },
                    "required": ["userSub", "content"],
                    "additionalProperties": False,
                },
            ),
            _memory_store_episodic_tool,
        ),
        "agent_memory_store_semantic": (
            tool_def(
                "agent_memory_store_semantic",
                "Store a semantic memory in the new structured memory system (preference, knowledge, pattern).",
                {
                    "type": "object",
                    "properties": {
                        "userSub": {"type": "string", "minLength": 1, "maxLength": 120},
                        "key": {"type": "string", "minLength": 1, "maxLength": 200},
                        "value": {"type": ["string", "number", "boolean", "null"], "description": "Preference value or knowledge fact"},
                        "scopeId": {"type": "string", "maxLength": 200, "description": "Optional scope override"},
                        "cognitoUserId": {"type": "string", "maxLength": 200, "description": "Optional Cognito user ID (defaults to userSub)"},
                        "slackUserId": {"type": "string", "maxLength": 40, "description": "Optional Slack user ID for traceability"},
                        "slackChannelId": {"type": "string", "maxLength": 40, "description": "Optional Slack channel ID where memory originated"},
                        "slackThreadTs": {"type": "string", "maxLength": 40, "description": "Optional Slack thread timestamp where memory originated"},
                        "slackTeamId": {"type": "string", "maxLength": 40, "description": "Optional Slack team ID"},
                        "rfpId": {"type": "string", "maxLength": 120, "description": "Optional RFP identifier"},
                        "source": {"type": "string", "maxLength": 100, "description": "Optional source system (defaults to 'agent_tool')"},
                    },
                    "required": ["userSub", "key", "value"],
                    "additionalProperties": False,
                },
            ),
            _memory_store_semantic_tool,
        ),
        "agent_memory_store_procedural": (
            tool_def(
                "agent_memory_store_procedural",
                "Store a procedural memory in the new structured memory system (workflow, tool usage pattern).",
                {
                    "type": "object",
                    "properties": {
                        "userSub": {"type": "string", "minLength": 1, "maxLength": 120},
                        "workflow": {"type": "string", "minLength": 1, "maxLength": 500},
                        "success": {"type": "boolean", "description": "Whether the workflow was successful"},
                        "context": {"type": "object", "description": "Optional context (toolSequence, successCriteria, etc.)"},
                        "cognitoUserId": {"type": "string", "maxLength": 200, "description": "Optional Cognito user ID (defaults to userSub)"},
                        "slackUserId": {"type": "string", "maxLength": 40, "description": "Optional Slack user ID for traceability"},
                        "slackChannelId": {"type": "string", "maxLength": 40, "description": "Optional Slack channel ID where memory originated"},
                        "slackThreadTs": {"type": "string", "maxLength": 40, "description": "Optional Slack thread timestamp where memory originated"},
                        "slackTeamId": {"type": "string", "maxLength": 40, "description": "Optional Slack team ID"},
                        "rfpId": {"type": "string", "maxLength": 120, "description": "Optional RFP identifier"},
                        "source": {"type": "string", "maxLength": 100, "description": "Optional source system (defaults to 'agent_tool')"},
                    },
                    "required": ["userSub", "workflow", "success"],
                    "additionalProperties": False,
                },
            ),
            _memory_store_procedural_tool,
        ),
        "agent_memory_search": (
            tool_def(
                "agent_memory_search",
                "Search agent memories for relevant entries using keyword and semantic search (new structured memory system).",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 500},
                        "userSub": {"type": "string", "maxLength": 120, "description": "User identifier (optional if scopeId/rfpId provided)"},
                        "rfpId": {"type": "string", "maxLength": 120, "description": "RFP identifier (alternative to userSub)"},
                        "tenantId": {"type": "string", "maxLength": 120, "description": "Tenant identifier"},
                        "scopeId": {"type": "string", "maxLength": 200, "description": "Scope override"},
                        "memoryTypes": {"type": "array", "items": {"type": "string", "enum": ["EPISODIC", "SEMANTIC", "PROCEDURAL", "TOOL_PATTERN", "WORKFLOW", "CONTEXT_PATTERN"]}, "description": "Filter by memory types"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            _agent_memory_search_tool,
        ),
        "agent_memory_get_context": (
            tool_def(
                "agent_memory_get_context",
                "Get relevant agent memories formatted for context inclusion (new structured memory system).",
                {
                    "type": "object",
                    "properties": {
                        "userSub": {"type": "string", "maxLength": 120, "description": "User identifier (optional if scopeId/rfpId provided)"},
                        "rfpId": {"type": "string", "maxLength": 120, "description": "RFP identifier"},
                        "tenantId": {"type": "string", "maxLength": 120, "description": "Tenant identifier"},
                        "scopeId": {"type": "string", "maxLength": 200, "description": "Scope override"},
                        "queryText": {"type": "string", "maxLength": 500, "description": "Optional search query to filter memories"},
                        "memoryTypes": {"type": "array", "items": {"type": "string", "enum": ["EPISODIC", "SEMANTIC", "PROCEDURAL", "TOOL_PATTERN", "WORKFLOW", "CONTEXT_PATTERN"]}},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        "maxChars": {"type": "integer", "minimum": 100, "maximum": 10000},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            ),
            _agent_memory_get_context_tool,
        ),
        "agent_memory_update_block": (
            tool_def(
                "agent_memory_update_block",
                "Update an existing memory block with new information. Tracks update history and preserves provenance.",
                {
                    "type": "object",
                    "properties": {
                        "memoryId": {"type": "string", "minLength": 1, "maxLength": 50, "description": "Memory identifier"},
                        "memoryType": {"type": "string", "enum": ["EPISODIC", "SEMANTIC", "PROCEDURAL", "TOOL_PATTERN", "WORKFLOW", "CONTEXT_PATTERN", "DIAGNOSTICS", "EXTERNAL_CONTEXT", "COLLABORATION_CONTEXT", "TEMPORAL_EVENT", "ERROR_LOG"], "description": "Memory type"},
                        "scopeId": {"type": "string", "minLength": 1, "maxLength": 200, "description": "Scope identifier (USER#{userSub}, RFP#{rfpId}, etc.)"},
                        "createdAt": {"type": "string", "minLength": 1, "maxLength": 50, "description": "Original creation timestamp (ISO format)"},
                        "content": {"type": "string", "maxLength": 20000, "description": "New content (optional, will check for significant changes)"},
                        "metadata": {"type": "object", "description": "New metadata to merge (optional, will be merged with existing)"},
                        "reason": {"type": "string", "maxLength": 500, "description": "Reason for the update (defaults to 'Information update')"},
                        "userSub": {"type": "string", "maxLength": 120, "description": "User identifier (optional, for provenance)"},
                    },
                    "required": ["memoryId", "memoryType", "scopeId", "createdAt"],
                    "additionalProperties": False,
                },
            ),
            _memory_update_block_tool,
        ),
        "agent_memory_create_block": (
            tool_def(
                "agent_memory_create_block",
                "Create a new durable memory block that agents can reference and edit.",
                {
                    "type": "object",
                    "properties": {
                        "userSub": {"type": "string", "minLength": 1, "maxLength": 120},
                        "blockId": {"type": "string", "minLength": 1, "maxLength": 100, "description": "Unique block identifier"},
                        "title": {"type": "string", "minLength": 1, "maxLength": 240, "description": "Block title"},
                        "content": {"type": "string", "minLength": 1, "maxLength": 20000, "description": "Block content"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"},
                        "metadata": {"type": "object", "description": "Optional metadata"},
                    },
                    "required": ["userSub", "blockId", "title", "content"],
                    "additionalProperties": False,
                },
            ),
            _memory_create_block_tool,
        ),
        "agent_memory_get_block": (
            tool_def(
                "agent_memory_get_block",
                "Get a memory block by block_id.",
                {
                    "type": "object",
                    "properties": {
                        "userSub": {"type": "string", "minLength": 1, "maxLength": 120},
                        "blockId": {"type": "string", "minLength": 1, "maxLength": 100, "description": "Block identifier"},
                    },
                    "required": ["userSub", "blockId"],
                    "additionalProperties": False,
                },
            ),
            _memory_get_block_tool,
        ),
        "agent_memory_block_update": (
            tool_def(
                "agent_memory_block_update",
                "Update an existing memory block. Tracks version history.",
                {
                    "type": "object",
                    "properties": {
                        "userSub": {"type": "string", "minLength": 1, "maxLength": 120},
                        "blockId": {"type": "string", "minLength": 1, "maxLength": 100, "description": "Block identifier"},
                        "content": {"type": "string", "maxLength": 20000, "description": "New content (optional)"},
                        "title": {"type": "string", "maxLength": 240, "description": "New title (optional)"},
                        "metadata": {"type": "object", "description": "New metadata to merge (optional)"},
                    },
                    "required": ["userSub", "blockId"],
                    "additionalProperties": False,
                },
            ),
            _memory_update_block_tool_wrapper,
        ),
        "agent_memory_list_blocks": (
            tool_def(
                "agent_memory_list_blocks",
                "List all memory blocks for a user.",
                {
                    "type": "object",
                    "properties": {
                        "userSub": {"type": "string", "minLength": 1, "maxLength": 120},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Maximum number of blocks (default 25)"},
                    },
                    "required": ["userSub"],
                    "additionalProperties": False,
                },
            ),
            _memory_list_blocks_tool,
        ),
        "agent_memory_get_related": (
            tool_def(
                "agent_memory_get_related",
                "Get memories related to a given memory using the relationship graph. Traverses connections between memories.",
                {
                    "type": "object",
                    "properties": {
                        "memoryId": {"type": "string", "minLength": 1, "maxLength": 50, "description": "Source memory ID"},
                        "memoryType": {"type": "string", "enum": ["EPISODIC", "SEMANTIC", "PROCEDURAL", "TOOL_PATTERN", "WORKFLOW", "CONTEXT_PATTERN", "DIAGNOSTICS", "EXTERNAL_CONTEXT", "COLLABORATION_CONTEXT", "TEMPORAL_EVENT", "ERROR_LOG", "MEMORY_BLOCK"], "description": "Source memory type"},
                        "scopeId": {"type": "string", "minLength": 1, "maxLength": 200, "description": "Source memory scope"},
                        "createdAt": {"type": "string", "minLength": 1, "maxLength": 50, "description": "Source memory created_at timestamp"},
                        "relationshipType": {"type": "string", "enum": ["refers_to", "depends_on", "contradicts", "reinforces", "temporal_sequence", "causes", "part_of", "related"], "description": "Optional filter by relationship type"},
                        "depth": {"type": "integer", "minimum": 1, "maximum": 3, "description": "Maximum traversal depth (default 1)"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Maximum number of results"},
                    },
                    "required": ["memoryId", "memoryType", "scopeId", "createdAt"],
                    "additionalProperties": False,
                },
            ),
            _memory_get_related_tool,
        ),
    }
