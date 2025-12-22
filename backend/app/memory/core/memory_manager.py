"""
Memory manager - unified interface for agent memory operations.

This consolidates all memory operations into a single interface.
"""

from __future__ import annotations

from typing import Any

from .memory_interface import AgentMemory
from . import agent_memory as memory_core
from ..blocks import agent_memory_blocks as memory_blocks
from ..retrieval import agent_memory_retrieval as memory_retrieval
from ...observability.logging import get_logger

log = get_logger("memory_manager")


class MemoryManager(AgentMemory):
    """
    Unified memory manager that provides access to all memory operations.
    
    This is the main interface that agents should use for memory operations.
    """
    
    def __init__(self, user_sub: str | None = None):
        """
        Initialize memory manager.
        
        Args:
            user_sub: User identifier for user-scoped operations
        """
        self.user_sub = user_sub
        self._scope_id = f"USER#{user_sub}" if user_sub else None
    
    def store(self, memory: dict[str, Any]) -> dict[str, Any]:
        """
        Store a memory.
        
        Args:
            memory: Memory dict with content, memory_type, etc.
        
        Returns:
            Stored memory dict with memory_id
        """
        if not self.user_sub:
            raise ValueError("user_sub required for storing memories")
        
        memory_type = memory.get("memoryType", "EPISODIC")
        content = memory.get("content", "")
        
        if memory_type == "EPISODIC":
            return memory_core.add_episodic_memory(
                user_sub=self.user_sub,
                content=content,
                context=memory.get("context"),
                **memory.get("provenance", {}),
            )
        elif memory_type == "SEMANTIC":
            return memory_core.update_semantic_memory(
                user_sub=self.user_sub,
                key=memory.get("key", ""),
                value=memory.get("value"),
                **memory.get("provenance", {}),
            )
        elif memory_type == "PROCEDURAL":
            return memory_core.add_procedural_memory(
                user_sub=self.user_sub,
                workflow=content,
                success=memory.get("success", True),
                context=memory.get("context"),
                **memory.get("provenance", {}),
            )
        else:
            # Generic memory creation
            from .agent_memory_db import create_memory, MemoryType
            
            # Validate memory_type if it's a known MemoryType value
            if memory_type and hasattr(MemoryType, memory_type):
                validated_type = getattr(MemoryType, memory_type)
            else:
                validated_type = memory_type
            
            return create_memory(
                memory_type=validated_type,
                scope_id=self._scope_id or "GLOBAL",
                content=content,
                tags=memory.get("tags"),
                keywords=memory.get("keywords"),
                metadata=memory.get("metadata"),
                **memory.get("provenance", {}),
            )
    
    def retrieve(self, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Retrieve memories matching query and filters.
        
        Args:
            query: Search query
            filters: Optional filters (memory_type, scope_id, etc.)
        
        Returns:
            List of matching memory dicts
        """
        filters = filters or {}
        
        return memory_retrieval.retrieve_relevant_memories(
            scope_id=self._scope_id or filters.get("scope_id"),
            memory_types=filters.get("memory_types"),
            query_text=query,
            limit=filters.get("limit", 20),
        )
    
    def update(self, memory_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """
        Update an existing memory.
        
        Args:
            memory_id: Memory identifier
            updates: Updates to apply (content, metadata, etc.)
        
        Returns:
            Updated memory dict
        """
        from .agent_memory import update_existing_memory
        
        return update_existing_memory(
            memory_id=memory_id,
            memory_type=updates.get("memory_type", "EPISODIC"),
            scope_id=self._scope_id or updates.get("scope_id", ""),
            created_at=updates.get("created_at", ""),
            content=updates.get("content"),
            metadata=updates.get("metadata"),
            reason=updates.get("reason", "Update"),
            user_sub=self.user_sub,
        )
    
    def get_blocks(self) -> list[dict[str, Any]]:
        """
        Get memory blocks for this user.
        
        Returns:
            List of memory block dicts
        """
        if not self.user_sub:
            return []
        
        return memory_blocks.list_memory_blocks(user_sub=self.user_sub)
