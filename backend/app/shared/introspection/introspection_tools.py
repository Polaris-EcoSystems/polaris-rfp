"""
Introspection tools for agents.

Provides agent-accessible tools for discovering and introspecting capabilities.
"""

from __future__ import annotations

from typing import Any

from .capability_inventory import get_inventory
from ...observability.logging import get_logger

log = get_logger("introspection_tools")


def list_capabilities_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    List all available capabilities.
    
    Args:
        category: Optional filter by category (tool, skill, domain, repository, shared)
        subcategory: Optional filter by subcategory (e.g., "aws", "slack", "rfp")
        limit: Maximum number of results (default 100)
    
    Returns:
        List of capabilities with basic info
    """
    category = args.get("category")
    subcategory = args.get("subcategory")
    limit = int(args.get("limit") or 100)
    
    try:
        inventory = get_inventory()
        capabilities = inventory.list_capabilities(
            category=category,
            subcategory=subcategory,
        )
        
        # Format for agent consumption
        formatted = []
        for cap in capabilities[:limit]:
            formatted.append({
                "name": cap.name,
                "category": cap.category,
                "subcategory": cap.subcategory,
                "description": cap.description,
                "usage": cap.usage,
                "introspect": cap.introspection_command,
            })
        
        return {
            "ok": True,
            "capabilities": formatted,
            "count": len(formatted),
            "total": len(capabilities),
        }
    except Exception as e:
        log.error("list_capabilities_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def introspect_capability_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get full introspection details for a capability.
    
    Args:
        name: Capability name to introspect
    
    Returns:
        Full capability details including signature, parameters, docstring, examples
    """
    name = str(args.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name is required"}
    
    try:
        inventory = get_inventory()
        details = inventory.introspect_capability(name)
        
        if not details:
            return {"ok": False, "error": f"Capability '{name}' not found"}
        
        return {
            "ok": True,
            "capability": details,
        }
    except Exception as e:
        log.error("introspect_capability_failed", error=str(e), name=name)
        return {"ok": False, "error": str(e)}


def search_capabilities_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Search capabilities by name or description.
    
    Args:
        query: Search query
        limit: Maximum number of results (default 20)
    
    Returns:
        List of matching capabilities
    """
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query is required"}
    
    limit = int(args.get("limit") or 20)
    
    try:
        inventory = get_inventory()
        matches = inventory.search_capabilities(query)
        
        formatted = []
        for cap in matches[:limit]:
            formatted.append({
                "name": cap.name,
                "category": cap.category,
                "subcategory": cap.subcategory,
                "description": cap.description,
                "usage": cap.usage,
                "introspect": cap.introspection_command,
            })
        
        return {
            "ok": True,
            "matches": formatted,
            "count": len(formatted),
        }
    except Exception as e:
        log.error("search_capabilities_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def get_capability_categories_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get all available categories and subcategories.
    
    Returns:
        Dictionary of categories -> subcategories
    """
    try:
        inventory = get_inventory()
        categories = inventory.get_categories()
        
        return {
            "ok": True,
            "categories": categories,
        }
    except Exception as e:
        log.error("get_categories_failed", error=str(e))
        return {"ok": False, "error": str(e)}


# Tool definitions for agent use
def get_introspection_tools() -> dict[str, tuple[dict[str, Any], Any]]:
    """
    Get introspection tools for agent use.
    
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
        "list_capabilities": (
            tool_def(
                "list_capabilities",
                "List all available capabilities (tools, skills, domain functions, repositories). Use this to discover what's available.",
                {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["tool", "skill", "domain", "repository", "shared"],
                            "description": "Filter by category",
                        },
                        "subcategory": {
                            "type": "string",
                            "description": "Filter by subcategory (e.g., 'aws', 'slack', 'rfp')",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 500,
                            "description": "Maximum number of results",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            ),
            list_capabilities_tool,
        ),
        "introspect_capability": (
            tool_def(
                "introspect_capability",
                "Get full details about a specific capability. Use this to understand parameters, return types, and usage examples.",
                {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Name of capability to introspect",
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            ),
            introspect_capability_tool,
        ),
        "search_capabilities": (
            tool_def(
                "search_capabilities",
                "Search capabilities by name or description. Use this to find capabilities related to a topic.",
                {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Search query",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "description": "Maximum number of results",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            search_capabilities_tool,
        ),
        "get_capability_categories": (
            tool_def(
                "get_capability_categories",
                "Get all available categories and subcategories. Use this to understand the organization of capabilities.",
                {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            ),
            get_capability_categories_tool,
        ),
    }
