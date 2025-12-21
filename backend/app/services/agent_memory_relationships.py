"""
Memory relationship graph management.

Provides bidirectional memory relationships and graph traversal capabilities.
"""

from __future__ import annotations

from typing import Any

from .agent_memory_db import get_memory, update_memory
from ..observability.logging import get_logger

log = get_logger("agent_memory_relationships")


RELATIONSHIP_TYPES = {
    "refers_to": "Memory A refers to or mentions Memory B",
    "depends_on": "Memory A depends on Memory B (e.g., procedural step depends on previous step)",
    "contradicts": "Memory A contradicts Memory B",
    "reinforces": "Memory A reinforces or supports Memory B",
    "temporal_sequence": "Memory A happens before Memory B in time",
    "causes": "Memory A causes or leads to Memory B",
    "part_of": "Memory A is part of Memory B",
    "related": "Generic related relationship",
}


def add_relationship(
    *,
    from_memory_id: str,
    from_memory_type: str,
    from_scope_id: str,
    from_created_at: str,
    to_memory_id: str,
    to_memory_type: str,
    to_scope_id: str,
    to_created_at: str,
    relationship_type: str = "related",
    bidirectional: bool = True,
) -> bool:
    """
    Add a bidirectional relationship between two memories.
    
    Args:
        from_memory_id: Source memory ID
        from_memory_type: Source memory type
        from_scope_id: Source memory scope
        from_created_at: Source memory created_at timestamp
        to_memory_id: Target memory ID
        to_memory_type: Target memory type
        to_scope_id: Target memory scope
        to_created_at: Target memory created_at timestamp
        relationship_type: Type of relationship (see RELATIONSHIP_TYPES)
        bidirectional: Whether to add reverse relationship
    
    Returns:
        True if successful, False otherwise
    """
    if relationship_type not in RELATIONSHIP_TYPES:
        log.warning("unknown_relationship_type", relationship_type=relationship_type)
        relationship_type = "related"
    
    try:
        # Get source memory
        from_memory = get_memory(
            memory_id=from_memory_id,
            memory_type=from_memory_type,
            scope_id=from_scope_id,
            created_at=from_created_at,
        )
        if not from_memory:
            log.warning("source_memory_not_found", memory_id=from_memory_id)
            return False
        
        # Get target memory
        to_memory = get_memory(
            memory_id=to_memory_id,
            memory_type=to_memory_type,
            scope_id=to_scope_id,
            created_at=to_created_at,
        )
        if not to_memory:
            log.warning("target_memory_not_found", memory_id=to_memory_id)
            return False
        
        # Update source memory with relationship
        current_related = from_memory.get("relatedMemoryIds", [])
        current_relationship_types = from_memory.get("relationshipTypes", {})
        
        if to_memory_id not in current_related:
            current_related.append(to_memory_id)
        
        if not isinstance(current_relationship_types, dict):
            current_relationship_types = {}
        current_relationship_types[to_memory_id] = relationship_type
        
        update_memory(
            memory_id=from_memory_id,
            memory_type=from_memory_type,
            scope_id=from_scope_id,
            created_at=from_created_at,
            related_memory_ids=current_related,
            metadata={
                **from_memory.get("metadata", {}),
                "relationshipTypes": current_relationship_types,
            },
        )
        
        # Add bidirectional relationship if requested
        if bidirectional:
            reverse_relationship_type = _get_reverse_relationship_type(relationship_type)
            to_current_related = to_memory.get("relatedMemoryIds", [])
            to_current_relationship_types = to_memory.get("relationshipTypes", {})
            
            if not isinstance(to_current_relationship_types, dict):
                to_current_relationship_types = {}
            
            if from_memory_id not in to_current_related:
                to_current_related.append(from_memory_id)
            
            to_current_relationship_types[from_memory_id] = reverse_relationship_type
            
            update_memory(
                memory_id=to_memory_id,
                memory_type=to_memory_type,
                scope_id=to_scope_id,
                created_at=to_created_at,
                related_memory_ids=to_current_related,
                metadata={
                    **to_memory.get("metadata", {}),
                    "relationshipTypes": to_current_relationship_types,
                },
            )
        
        log.debug(
            "memory_relationship_added",
            from_memory_id=from_memory_id,
            to_memory_id=to_memory_id,
            relationship_type=relationship_type,
            bidirectional=bidirectional,
        )
        
        return True
    
    except Exception as e:
        log.error("failed_to_add_relationship", error=str(e), from_memory_id=from_memory_id, to_memory_id=to_memory_id)
        return False


def _get_reverse_relationship_type(relationship_type: str) -> str:
    """Get reverse relationship type for bidirectional links."""
    reverse_map = {
        "depends_on": "enables",
        "temporal_sequence": "temporal_sequence",  # Reverse is still temporal, but direction changes
        "causes": "caused_by",
        "part_of": "contains",
        "refers_to": "referred_by",
    }
    return reverse_map.get(relationship_type, "related")


def get_related_memories(
    *,
    memory_id: str,
    memory_type: str,
    scope_id: str,
    created_at: str,
    relationship_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Get memories related to a given memory.
    
    Args:
        memory_id: Source memory ID
        memory_type: Source memory type
        scope_id: Source memory scope
        created_at: Source memory created_at timestamp
        relationship_type: Optional filter by relationship type
        limit: Maximum number of related memories to return
    
    Returns:
        List of related memory dicts
    """
    try:
        memory = get_memory(
            memory_id=memory_id,
            memory_type=memory_type,
            scope_id=scope_id,
            created_at=created_at,
        )
        if not memory:
            return []
        
        related_ids = memory.get("relatedMemoryIds", [])
        relationship_types = memory.get("relationshipTypes", {})
        
        if not isinstance(relationship_types, dict):
            relationship_types = {}
        
        if not related_ids:
            return []
        
        # Filter by relationship type if specified
        if relationship_type:
            related_ids = [
                rid for rid in related_ids
                if relationship_types.get(rid) == relationship_type
            ]
        
        # Fetch related memories
        related_memories: list[dict[str, Any]] = []
        for related_id in related_ids[:limit]:
            # Try to find related memory by querying (we'd need memory lookup by ID)
            # For now, return metadata about relationships
            # TODO: Implement efficient lookup of memories by ID across scopes
            pass
        
        return related_memories
    
    except Exception as e:
        log.error("failed_to_get_related_memories", error=str(e), memory_id=memory_id)
        return []


def traverse_memory_graph(
    *,
    start_memory_id: str,
    start_memory_type: str,
    start_scope_id: str,
    start_created_at: str,
    max_depth: int = 3,
    relationship_types: list[str] | None = None,
    visited: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Traverse memory relationship graph starting from a memory.
    
    Args:
        start_memory_id: Starting memory ID
        start_memory_type: Starting memory type
        start_scope_id: Starting memory scope
        start_created_at: Starting memory created_at timestamp
        max_depth: Maximum traversal depth
        relationship_types: Optional filter by relationship types
        visited: Set of visited memory IDs (for recursion)
    
    Returns:
        List of memories found in traversal
    """
    if visited is None:
        visited = set()
    
    memory_key = f"{start_memory_id}#{start_scope_id}"
    if memory_key in visited or max_depth <= 0:
        return []
    
    visited.add(memory_key)
    
    try:
        memory = get_memory(
            memory_id=start_memory_id,
            memory_type=start_memory_type,
            scope_id=start_scope_id,
            created_at=start_created_at,
        )
        if not memory:
            return []
        
        results: list[dict[str, Any]] = [memory]
        
        related_ids = memory.get("relatedMemoryIds", [])
        relationship_types_map = memory.get("relationshipTypes", {})
        
        if not isinstance(relationship_types_map, dict):
            relationship_types_map = {}
        
        # Filter by relationship types if specified
        if relationship_types:
            related_ids = [
                rid for rid in related_ids
                if relationship_types_map.get(rid) in relationship_types
            ]
        
        # Recursively traverse (would need efficient memory lookup)
        # For now, return direct relationships only
        # TODO: Implement full graph traversal with efficient memory lookup
        
        return results
    
    except Exception as e:
        log.error("failed_to_traverse_graph", error=str(e), start_memory_id=start_memory_id)
        return []
