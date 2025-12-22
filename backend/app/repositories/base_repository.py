"""
Base repository interface.

All repositories should implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Repository(ABC):
    """Base repository interface."""
    
    @abstractmethod
    def get(self, id: str) -> dict[str, Any] | None:
        """Get an entity by ID."""
        pass
    
    @abstractmethod
    def list(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """List entities matching filters."""
        pass
    
    @abstractmethod
    def create(self, entity: dict[str, Any]) -> dict[str, Any]:
        """Create a new entity."""
        pass
    
    @abstractmethod
    def update(self, id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update an existing entity."""
        pass
