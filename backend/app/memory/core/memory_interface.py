"""
Unified memory interface for agents.

This will be implemented by the consolidated memory module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Memory:
    """Represents a memory entry."""
    pass


class MemoryBlock:
    """Represents a memory block."""
    pass


class AgentMemory(ABC):
    """Unified memory interface for agents."""
    
    @abstractmethod
    def store(self, memory: dict[str, Any]) -> dict[str, Any]:
        """Store a memory."""
        pass
    
    @abstractmethod
    def retrieve(self, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Retrieve memories matching query and filters."""
        pass
    
    @abstractmethod
    def update(self, memory_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update an existing memory."""
        pass
    
    @abstractmethod
    def get_blocks(self) -> list[dict[str, Any]]:
        """Get memory blocks."""
        pass
