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
        from_metadata = from_memory.get("metadata", {})
        if not isinstance(from_metadata, dict):
            from_metadata = {}
        
        # Get relationship data from metadata (new) or top-level (backward compat)
        current_relationship_types = from_metadata.get("relationshipTypes", {}) or from_memory.get("relationshipTypes", {})
        current_relationship_metadata = from_metadata.get("relationshipMetadata", {}) or {}
        
        if to_memory_id not in current_related:
            current_related.append(to_memory_id)
        
        if not isinstance(current_relationship_types, dict):
            current_relationship_types = {}
        current_relationship_types[to_memory_id] = relationship_type
        
        # Store metadata about related memory for efficient lookup
        if not isinstance(current_relationship_metadata, dict):
            current_relationship_metadata = {}
        current_relationship_metadata[to_memory_id] = {
            "memoryType": to_memory_type,
            "scopeId": to_scope_id,
            "createdAt": to_created_at,
            "relationshipType": relationship_type,
        }
        
        # Update memory with related IDs in metadata
        # (from_metadata already retrieved above)
        from_metadata["relationshipTypes"] = current_relationship_types
        from_metadata["relationshipMetadata"] = current_relationship_metadata
        
        update_memory(
            memory_id=from_memory_id,
            memory_type=from_memory_type,
            scope_id=from_scope_id,
            created_at=from_created_at,
            metadata={
                **from_metadata,
                "relatedMemoryIds": current_related,
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
            
            # Store metadata about related memory
            to_metadata = to_memory.get("metadata", {})
            if not isinstance(to_metadata, dict):
                to_metadata = {}
            
            to_current_relationship_metadata = to_metadata.get("relationshipMetadata", {}) or {}
            if not isinstance(to_current_relationship_metadata, dict):
                to_current_relationship_metadata = {}
            to_current_relationship_metadata[from_memory_id] = {
                "memoryType": from_memory_type,
                "scopeId": from_scope_id,
                "createdAt": from_created_at,
                "relationshipType": reverse_relationship_type,
            }
            
            # Update memory with related IDs in metadata
            # (to_metadata already retrieved above)
            to_metadata["relationshipTypes"] = to_current_relationship_types
            to_metadata["relationshipMetadata"] = to_current_relationship_metadata
            
            update_memory(
                memory_id=to_memory_id,
                memory_type=to_memory_type,
                scope_id=to_scope_id,
                created_at=to_created_at,
                metadata={
                    **to_metadata,
                    "relatedMemoryIds": to_current_related,
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
        memory_metadata = memory.get("metadata", {})
        if not isinstance(memory_metadata, dict):
            memory_metadata = {}
        
        relationship_types_map = memory_metadata.get("relationshipTypes", {}) or memory.get("relationshipTypes", {})
        relationship_metadata_map = memory_metadata.get("relationshipMetadata", {}) or {}
        
        if not isinstance(relationship_types_map, dict):
            relationship_types_map = {}
        if not isinstance(relationship_metadata_map, dict):
            relationship_metadata_map = {}
        
        if not related_ids:
            return []
        
        # Filter by relationship type if specified
        if relationship_type:
            related_ids = [
                rid for rid in related_ids
                if relationship_types_map.get(rid) == relationship_type
            ]
        
        # Fetch related memories - use stored metadata if available
        related_memories: list[dict[str, Any]] = []
        
        for related_id in related_ids[:limit]:
            try:
                # Try to use stored metadata for direct lookup
                rel_meta = relationship_metadata_map.get(related_id)
                if rel_meta and isinstance(rel_meta, dict):
                    # Use stored metadata for efficient lookup
                    related_mem = get_memory(
                        memory_id=related_id,
                        memory_type=rel_meta.get("memoryType", ""),
                        scope_id=rel_meta.get("scopeId", ""),
                        created_at=rel_meta.get("createdAt", ""),
                    )
                    if related_mem:
                        related_memories.append(related_mem)
                        continue
                
                # Fallback: search across scopes
                from .agent_memory_db import find_memory_by_id
                
                search_scopes = [scope_id]
                if scope_id.startswith("USER#"):
                    user_sub = scope_id.replace("USER#", "")
                    search_scopes.append(f"USER#{user_sub}")
                
                related_mem = find_memory_by_id(
                    memory_id=related_id,
                    scope_ids=search_scopes,
                    memory_types=[memory_type] if memory_type else None,
                )
                
                if related_mem:
                    related_memories.append(related_mem)
            except Exception as e:
                log.warning("failed_to_find_related_memory", error=str(e), memory_id=related_id)
                continue
        
        return related_memories
    
    except Exception as e:
        log.error("failed_to_get_related_memories", error=str(e), memory_id=memory_id)
        return []


def auto_detect_relationships(
    *,
    memory: dict[str, Any],
    user_sub: str,
) -> list[dict[str, Any]]:
    """
    Auto-detect relationships for a newly created memory.
    
    Args:
        memory: Newly created memory dict
        user_sub: User identifier
    
    Returns:
        List of relationship dicts with to_memory_id, relationship_type, etc.
    """
    relationships: list[dict[str, Any]] = []
    
    try:
        from .agent_memory_retrieval import retrieve_relevant_memories
        
        memory_id = memory.get("memoryId")
        memory_type = memory.get("memoryType", "")
        scope_id = memory.get("scopeId", "")
        created_at = memory.get("createdAt", "")
        content = memory.get("content", "")
        rfp_id = memory.get("rfpId")
        
        if not memory_id or not scope_id or not created_at:
            return relationships
        
        # Find similar memories in same scope
        similar = retrieve_relevant_memories(
            scope_id=scope_id,
            memory_types=[memory_type] if memory_type else None,
            query_text=content,
            limit=10,
        )
        
        for similar_mem in similar:
            similar_id = similar_mem.get("memoryId")
            if similar_id == memory_id:
                continue  # Skip self
            
            similar_created_at = similar_mem.get("createdAt", "")
            similar_rfp_id = similar_mem.get("rfpId")
            
            # Determine relationship type
            relationship_type = "related"
            
            # Same RFP → related
            if rfp_id and similar_rfp_id and rfp_id == similar_rfp_id:
                relationship_type = "related"
            
            # Temporal proximity → temporal_sequence
            if similar_created_at:
                try:
                    from datetime import datetime
                    from_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    to_date = datetime.fromisoformat(similar_created_at.replace("Z", "+00:00"))
                    time_diff = abs((from_date - to_date).total_seconds())
                    if time_diff < 3600:  # Within 1 hour
                        if from_date < to_date:
                            relationship_type = "temporal_sequence"
                except Exception:
                    pass
            
            relationships.append({
                "to_memory_id": similar_id,
                "to_memory_type": similar_mem.get("memoryType", ""),
                "to_scope_id": similar_mem.get("scopeId", ""),
                "to_created_at": similar_created_at,
                "relationship_type": relationship_type,
            })
        
        return relationships[:5]  # Limit to top 5 relationships
    
    except Exception as e:
        log.warning("auto_detect_relationships_failed", error=str(e), memory_id=memory.get("memoryId"))
        return relationships


def retrieve_with_relationships(
    *,
    memory_id: str,
    memory_type: str,
    scope_id: str,
    created_at: str,
    relationship_types: list[str] | None = None,
    depth: int = 1,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Retrieve memories related to a given memory.
    Traverse relationship graph to find connected memories.
    
    Args:
        memory_id: Source memory ID
        memory_type: Source memory type
        scope_id: Source memory scope
        created_at: Source memory created_at timestamp
        relationship_types: Optional filter by relationship types
        depth: Maximum traversal depth (default 1 = direct relationships only)
        limit: Maximum number of results to return
    
    Returns:
        List of related memory dicts sorted by relationship strength
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
        memory_metadata = memory.get("metadata", {})
        if not isinstance(memory_metadata, dict):
            memory_metadata = {}
        
        relationship_types_map = memory_metadata.get("relationshipTypes", {}) or memory.get("relationshipTypes", {})
        relationship_metadata_map = memory_metadata.get("relationshipMetadata", {}) or {}
        
        if not isinstance(relationship_types_map, dict):
            relationship_types_map = {}
        if not isinstance(relationship_metadata_map, dict):
            relationship_metadata_map = {}
        
        if not related_ids:
            return []
        
        # Filter by relationship types if specified
        if relationship_types:
            related_ids = [
                rid for rid in related_ids
                if relationship_types_map.get(rid) in relationship_types
            ]
        
        # Fetch related memories - use stored metadata if available
        related_memories: list[dict[str, Any]] = []
        
        for related_id in related_ids[:limit]:
            try:
                # Try to use stored metadata for direct lookup
                rel_meta = relationship_metadata_map.get(related_id)
                related_mem = None
                
                if rel_meta and isinstance(rel_meta, dict):
                    # Use stored metadata for efficient lookup
                    related_mem = get_memory(
                        memory_id=related_id,
                        memory_type=rel_meta.get("memoryType", ""),
                        scope_id=rel_meta.get("scopeId", ""),
                        created_at=rel_meta.get("createdAt", ""),
                    )
                
                # Fallback: search across scopes
                if not related_mem:
                    from .agent_memory_db import find_memory_by_id
                    
                    search_scopes = [scope_id]
                    if scope_id.startswith("USER#"):
                        user_sub = scope_id.replace("USER#", "")
                        search_scopes.append(f"USER#{user_sub}")
                    
                    related_mem = find_memory_by_id(
                        memory_id=related_id,
                        scope_ids=search_scopes,
                        memory_types=[memory_type] if memory_type else None,
                    )
                
                if related_mem:
                    related_memories.append(related_mem)
                    
                    # If depth > 1, recursively traverse
                    if depth > 1:
                        related_type = related_mem.get("memoryType", "")
                        related_scope = related_mem.get("scopeId", "")
                        related_created_at = related_mem.get("createdAt", "")
                        
                        if related_type and related_scope and related_created_at:
                            deeper_results = retrieve_with_relationships(
                                memory_id=related_id,
                                memory_type=related_type,
                                scope_id=related_scope,
                                created_at=related_created_at,
                                relationship_types=relationship_types,
                                depth=depth - 1,
                            )
                            # Add deeper results (avoid duplicates)
                            existing_ids = {m.get("memoryId") for m in related_memories}
                            for deeper_mem in deeper_results:
                                deeper_id = deeper_mem.get("memoryId")
                                if deeper_id and deeper_id not in existing_ids:
                                    related_memories.append(deeper_mem)
                                    existing_ids.add(deeper_id)
            except Exception as e:
                log.warning("failed_to_retrieve_related", error=str(e), memory_id=related_id)
                continue
        
        return related_memories
    
    except Exception as e:
        log.error("failed_to_retrieve_with_relationships", error=str(e), memory_id=memory_id)
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
        memory_metadata = memory.get("metadata", {})
        if not isinstance(memory_metadata, dict):
            memory_metadata = {}
        
        relationship_types_map = memory_metadata.get("relationshipTypes", {}) or memory.get("relationshipTypes", {})
        
        if not isinstance(relationship_types_map, dict):
            relationship_types_map = {}
        
        # Filter by relationship types if specified
        if relationship_types:
            related_ids = [
                rid for rid in related_ids
                if relationship_types_map.get(rid) in relationship_types
            ]
        
        # Recursively traverse related memories
        from .agent_memory_db import find_memory_by_id
        
        for related_id in related_ids[:10]:  # Limit recursion width
            try:
                # Try to find related memory
                # We need to determine its scope/type - for now, search in same scope
                related_mem = find_memory_by_id(
                    memory_id=related_id,
                    scope_ids=[start_scope_id],
                )
                
                if related_mem:
                    # Recursively traverse if depth allows
                    if max_depth > 1:
                        related_type = related_mem.get("memoryType", "")
                        related_scope = related_mem.get("scopeId", "")
                        related_created_at = related_mem.get("createdAt", "")
                        
                        if related_type and related_scope and related_created_at:
                            deeper_results = traverse_memory_graph(
                                start_memory_id=related_id,
                                start_memory_type=related_type,
                                start_scope_id=related_scope,
                                start_created_at=related_created_at,
                                max_depth=max_depth - 1,
                                relationship_types=relationship_types,
                                visited=visited,
                            )
                            results.extend(deeper_results)
                    else:
                        # Just add direct relationship if at max depth
                        results.append(related_mem)
            except Exception as e:
                log.warning("failed_to_traverse_related", error=str(e), related_id=related_id)
                continue
        
        return results
    
    except Exception as e:
        log.error("failed_to_traverse_graph", error=str(e), start_memory_id=start_memory_id)
        return []
