"""
Tool registry implementation.

Consolidates tool registration and discovery.
"""

from __future__ import annotations

from typing import Any, Callable

from .tool_registry import ToolRegistry, ToolFn
from ...observability.logging import get_logger

log = get_logger("tool_registry")

# Type alias for tool function (matches ToolFn from tool_registry)
ToolFunction = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistryImpl(ToolRegistry):
    """
    Implementation of tool registry.
    
    Manages tool registration and provides tool lookup.
    """
    
    def __init__(self):
        """Initialize registry."""
        self._tools: dict[str, tuple[dict[str, Any], ToolFn]] = {}
    
    def get_tool(self, tool_name: str) -> tuple[dict[str, Any], ToolFn] | None:
        """Get a tool by name."""
        return self._tools.get(tool_name)
    
    def list_tools(self) -> dict[str, tuple[dict[str, Any], ToolFn]]:
        """List all available tools."""
        return dict(self._tools)
    
    def register_tool(self, name: str, tool_def: dict[str, Any], tool_fn: ToolFn) -> None:
        """Register a tool."""
        if name in self._tools:
            log.warning("tool_already_registered", tool_name=name, overwriting=True)
        
        self._tools[name] = (tool_def, tool_fn)
        log.debug("tool_registered", tool_name=name)
    
    def register_tools(self, tools: dict[str, tuple[dict[str, Any], ToolFn]]) -> None:
        """Register multiple tools at once."""
        for name, (tool_def, tool_fn) in tools.items():
            self.register_tool(name, tool_def, tool_fn)
    
    def get_tools_by_category(self, category: str) -> dict[str, tuple[dict[str, Any], ToolFn]]:
        """
        Get tools by category.
        
        Args:
            category: Tool category (e.g., "aws", "slack", "rfp")
        
        Returns:
            Dict of tool_name -> (tool_def, tool_fn)
        """
        prefix = f"{category}_"
        return {
            name: (tool_def, tool_fn)
            for name, (tool_def, tool_fn) in self._tools.items()
            if name.startswith(prefix)
        }


# Global registry instance
_global_registry: ToolRegistryImpl | None = None


def get_global_registry() -> ToolRegistryImpl:
    """Get the global tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistryImpl()
        # Load tools from read_registry
        try:
            from .read_registry import READ_TOOLS
            _global_registry.register_tools(READ_TOOLS)
        except ImportError as e:
            log.warning("could_not_load_tools", error=str(e))
    return _global_registry
