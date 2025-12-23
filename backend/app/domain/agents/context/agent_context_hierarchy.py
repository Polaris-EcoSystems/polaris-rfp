"""
Context hierarchy management.

Manages context loading in priority order with token budget awareness.
Implements progressive loading: most important context first, until budget exhausted.
"""

from __future__ import annotations

from typing import Any

from ...memory.blocks.agent_memory_blocks import list_memory_blocks
from ...memory.core.agent_memory_db import MemoryType
from ...memory.retrieval.agent_memory_retrieval import retrieve_relevant_memories
from ...ai.context import clip_text
from ....observability.logging import get_logger

log = get_logger("agent_context_hierarchy")


def format_memory(memory: dict[str, Any]) -> str:
    """Format a memory for context inclusion."""
    mem_type = memory.get("memoryType", "")
    summary = memory.get("summary") or memory.get("content", "")
    created_at = memory.get("createdAt", "")
    
    # Extract date part from ISO timestamp
    date_part = ""
    if created_at:
        date_part = created_at.split("T")[0] if "T" in created_at else created_at[:10]
    
    tags = memory.get("tags", [])
    tag_str = ""
    if tags and isinstance(tags, list):
        tag_str = ", ".join([str(t) for t in tags[:3]])
    
    line = f"[{mem_type}] {clip_text(summary, max_chars=200)}"
    if date_part:
        line += f" ({date_part})"
    if tag_str:
        line += f" [{tag_str}]"
    
    return line


def format_block(block: dict[str, Any]) -> str:
    """Format a memory block for context inclusion."""
    metadata = block.get("metadata", {})
    title = metadata.get("title", "") if isinstance(metadata, dict) else ""
    content = block.get("content", "")
    
    # Extract title from content if content starts with title
    if content and "\n\n" in content:
        parts = content.split("\n\n", 1)
        if len(parts) == 2:
            title = parts[0] if not title else title
            content = parts[1]
    
    summary = clip_text(f"{title}: {content}", max_chars=300)
    return f"[BLOCK] {summary}"


def format_message(message: dict[str, Any]) -> str:
    """Format a message for context inclusion."""
    role = message.get("role", "unknown")
    content = message.get("content", "")
    timestamp = message.get("timestamp", "")
    
    date_part = ""
    if timestamp:
        date_part = timestamp.split("T")[0] if "T" in timestamp else timestamp[:10]
    
    line = f"{role.upper()}: {clip_text(content, max_chars=200)}"
    if date_part:
        line += f" ({date_part})"
    
    return line


def get_recent_messages(
    *,
    user_sub: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get recent messages for a user.
    
    Args:
        user_sub: User identifier
        limit: Maximum number of messages
    
    Returns:
        List of message dicts with role, content, timestamp
    """
    try:
        from .agent_message_history import get_recent_messages as get_msgs
        return get_msgs(user_sub=user_sub, limit=limit)
    except Exception:
        # Fallback: return empty list if message history not available
        return []


def get_active_memory_blocks(
    *,
    user_sub: str,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Get active memory blocks (high importance, recent access).
    
    Args:
        user_sub: User identifier
        query: Query text for relevance
        limit: Maximum number of blocks
    
    Returns:
        List of memory block dicts
    """
    try:
        # Get all blocks and filter by relevance
        all_blocks = list_memory_blocks(user_sub=user_sub, limit=limit * 2)
        
        # For now, just return most recent blocks
        # In a full implementation, would score by importance and relevance
        return all_blocks[:limit]
    except Exception:
        return []


class ContextHierarchy:
    """
    Manages context loading in priority order with token budget awareness.
    
    Priority order:
    1. Recent messages (if available)
    2. Active memory blocks (high importance, recent access)
    3. Relevant episodic memories (query-matched)
    4. Semantic memories (preferences)
    5. Procedural memories (workflows)
    6. Archival/compressed memories (summaries)
    """
    
    def build_hierarchical_context(
        self,
        *,
        token_budget_tracker: Any | None,
        query: str,
        user_sub: str,
        rfp_id: str | None = None,
        channel_id: str | None = None,
        thread_ts: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build context in priority order until budget exhausted.
        
        Args:
            token_budget_tracker: TokenBudgetTracker instance (optional)
            query: Query text for relevance matching
            user_sub: User identifier
            rfp_id: Optional RFP identifier
            channel_id: Optional channel identifier
            thread_ts: Optional thread timestamp
        
        Returns:
            Tuple of (context_string, metadata_about_included_items)
        """
        context_parts: list[str] = []
        included: dict[str, Any] = {
            "recent_messages": 0,
            "active_blocks": 0,
            "episodic_memories": 0,
            "semantic_memories": 0,
            "procedural_memories": 0,
            "archival_memories": 0,
        }
        
        # If no budget tracker, use simple limit-based approach
        if token_budget_tracker is None:
            # Fallback to simple retrieval
            from ...memory.retrieval.agent_memory_retrieval import get_memories_for_context
            
            memories = get_memories_for_context(
                user_sub=user_sub,
                rfp_id=rfp_id,
                query_text=query,
                limit=15,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
            
            for mem in memories:
                mem_type = mem.get("memoryType", "")
                if mem_type == MemoryType.EPISODIC:
                    included["episodic_memories"] += 1
                elif mem_type == MemoryType.SEMANTIC:
                    included["semantic_memories"] += 1
                elif mem_type == MemoryType.PROCEDURAL:
                    included["procedural_memories"] += 1
                else:
                    included["archival_memories"] += 1
                
                context_parts.append(format_memory(mem))
            
            return "\n\n".join(context_parts), included
        
        # Priority 1: Recent messages (if available)
        if token_budget_tracker.remaining() > 1000:
            messages = get_recent_messages(user_sub=user_sub, limit=10)
            if messages:
                context_parts.append("Recent messages:")
                for msg in messages:
                    msg_text = format_message(msg)
                    if token_budget_tracker.can_add(msg_text):
                        context_parts.append(msg_text)
                        included["recent_messages"] += 1
                        token_budget_tracker.record_llm_call(
                            input_text=msg_text,
                            output_text="",
                        )
                    else:
                        break
                context_parts.append("")
        
        # Priority 2: Active memory blocks (high importance, recent access)
        if token_budget_tracker.remaining() > 500:
            blocks = get_active_memory_blocks(
                user_sub=user_sub,
                query=query,
                limit=5,
            )
            if blocks:
                context_parts.append("Active memory blocks:")
                for block in blocks:
                    block_text = format_block(block)
                    if token_budget_tracker.can_add(block_text):
                        context_parts.append(block_text)
                        included["active_blocks"] += 1
                        token_budget_tracker.record_llm_call(
                            input_text=block_text,
                            output_text="",
                        )
                    else:
                        break
                context_parts.append("")
        
        # Priority 3: Relevant episodic memories (query-matched)
        if token_budget_tracker.remaining() > 500:
            scope_id = f"RFP#{rfp_id}" if rfp_id else f"USER#{user_sub}"
            episodic = retrieve_relevant_memories(
                scope_id=scope_id,
                memory_types=[MemoryType.EPISODIC],
                query_text=query,
                limit=5,
            )
            if episodic:
                context_parts.append("Relevant episodic memories:")
                for mem in episodic:
                    mem_text = format_memory(mem)
                    if token_budget_tracker.can_add(mem_text):
                        context_parts.append(mem_text)
                        included["episodic_memories"] += 1
                        token_budget_tracker.record_llm_call(
                            input_text=mem_text,
                            output_text="",
                        )
                    else:
                        break
                context_parts.append("")
        
        # Priority 4: Semantic memories (preferences)
        if token_budget_tracker.remaining() > 300:
            scope_id = f"USER#{user_sub}"
            semantic = retrieve_relevant_memories(
                scope_id=scope_id,
                memory_types=[MemoryType.SEMANTIC],
                query_text=query,
                limit=10,
            )
            if semantic:
                context_parts.append("User preferences (semantic):")
                for mem in semantic:
                    mem_text = format_memory(mem)
                    if token_budget_tracker.can_add(mem_text):
                        context_parts.append(mem_text)
                        included["semantic_memories"] += 1
                        token_budget_tracker.record_llm_call(
                            input_text=mem_text,
                            output_text="",
                        )
                    else:
                        break
                context_parts.append("")
        
        # Priority 5: Procedural memories (workflows)
        if token_budget_tracker.remaining() > 300:
            scope_id = f"USER#{user_sub}"
            procedural = retrieve_relevant_memories(
                scope_id=scope_id,
                memory_types=[MemoryType.PROCEDURAL],
                query_text=query,
                limit=5,
            )
            if procedural:
                context_parts.append("Known workflows (procedural):")
                for mem in procedural:
                    mem_text = format_memory(mem)
                    if token_budget_tracker.can_add(mem_text):
                        context_parts.append(mem_text)
                        included["procedural_memories"] += 1
                        token_budget_tracker.record_llm_call(
                            input_text=mem_text,
                            output_text="",
                        )
                    else:
                        break
                context_parts.append("")
        
        # Priority 6: Archival/compressed memories (summaries)
        if token_budget_tracker.remaining() > 200:
            scope_id = f"USER#{user_sub}"
            # Get compressed memories (marked with compressed=True)
            all_memories = retrieve_relevant_memories(
                scope_id=scope_id,
                memory_types=None,  # All types
                query_text=query,
                limit=10,
            )
            compressed = [m for m in all_memories if m.get("compressed", False)]
            if compressed:
                context_parts.append("Archival memories (compressed):")
                for mem in compressed[:3]:  # Limit to 3 compressed
                    mem_text = format_memory(mem)
                    if token_budget_tracker.can_add(mem_text):
                        context_parts.append(mem_text)
                        included["archival_memories"] += 1
                        token_budget_tracker.record_llm_call(
                            input_text=mem_text,
                            output_text="",
                        )
                    else:
                        break
                context_parts.append("")
        
        return "\n\n".join(context_parts), included
