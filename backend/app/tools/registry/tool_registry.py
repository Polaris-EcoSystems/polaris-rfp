"""
Tool registry for agent tool discovery and execution.

This will be implemented by the restructured tools module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry(ABC):
    """Registry for tools available to agents."""
    
    @abstractmethod
    def get_tool(self, tool_name: str) -> tuple[dict[str, Any], ToolFn] | None:
        """Get a tool by name."""
        pass
    
    @abstractmethod
    def list_tools(self) -> dict[str, tuple[dict[str, Any], ToolFn]]:
        """List all available tools."""
        pass
    
    @abstractmethod
    def register_tool(self, name: str, tool_def: dict[str, Any], tool_fn: ToolFn) -> None:
        """Register a tool."""
        pass
