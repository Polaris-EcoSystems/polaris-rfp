"""
Capability Inventory - Comprehensive catalog of all available capabilities.

Provides agents with easy discovery and introspection of:
- Tools
- Skills
- Domain functions
- Repository methods
- Shared utilities
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from ...observability.logging import get_logger

log = get_logger("capability_inventory")


@dataclass
class CapabilityMetadata:
    """Metadata about a capability."""
    name: str
    category: str  # "tool", "skill", "domain", "repository", "shared"
    subcategory: str | None = None  # e.g., "aws", "slack", "rfp"
    description: str = ""
    signature: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    return_type: str | None = None
    docstring: str = ""
    examples: list[str] = field(default_factory=list)
    source_module: str = ""
    source_file: str = ""


@dataclass
class CapabilityInfo:
    """Information about a capability for agent introspection."""
    name: str
    category: str
    subcategory: str | None
    description: str
    usage: str  # How to use it
    parameters: dict[str, Any]
    examples: list[str]
    introspection_command: str  # Command to get full details


class CapabilityInventory:
    """
    Comprehensive inventory of all capabilities.
    
    Catalogs tools, skills, domain functions, repositories, and shared utilities.
    """
    
    def __init__(self):
        """Initialize inventory."""
        self._capabilities: dict[str, CapabilityMetadata] = {}
        self._by_category: dict[str, list[str]] = {}
        self._by_subcategory: dict[str, dict[str, list[str]]] = {}
    
    def register_capability(self, metadata: CapabilityMetadata) -> None:
        """Register a capability."""
        self._capabilities[metadata.name] = metadata
        
        # Index by category
        if metadata.category not in self._by_category:
            self._by_category[metadata.category] = []
        self._by_category[metadata.category].append(metadata.name)
        
        # Index by subcategory
        if metadata.subcategory:
            if metadata.category not in self._by_subcategory:
                self._by_subcategory[metadata.category] = {}
            if metadata.subcategory not in self._by_subcategory[metadata.category]:
                self._by_subcategory[metadata.category][metadata.subcategory] = []
            self._by_subcategory[metadata.category][metadata.subcategory].append(metadata.name)
        
        log.debug("capability_registered", name=metadata.name, category=metadata.category)
    
    def get_capability(self, name: str) -> CapabilityMetadata | None:
        """Get capability metadata by name."""
        return self._capabilities.get(name)
    
    def list_capabilities(
        self,
        *,
        category: str | None = None,
        subcategory: str | None = None,
    ) -> list[CapabilityInfo]:
        """
        List capabilities with basic info for agents.
        
        Returns lightweight info suitable for agent prompts.
        """
        capabilities: list[CapabilityInfo] = []
        
        # Filter by category/subcategory
        if category:
            if subcategory:
                names = self._by_subcategory.get(category, {}).get(subcategory, [])
            else:
                names = self._by_category.get(category, [])
        else:
            names = list(self._capabilities.keys())
        
        for name in names:
            meta = self._capabilities.get(name)
            if not meta:
                continue
            
            # Build usage string
            params_str = ", ".join(meta.parameters.keys()) if meta.parameters else "()"
            usage = f"{name}({params_str})"
            
            capabilities.append(CapabilityInfo(
                name=name,
                category=meta.category,
                subcategory=meta.subcategory,
                description=meta.description or meta.docstring.split("\n")[0] if meta.docstring else "",
                usage=usage,
                parameters=meta.parameters,
                examples=meta.examples,
                introspection_command=f"introspect_capability(name=\"{name}\")",
            ))
        
        return capabilities
    
    def introspect_capability(self, name: str) -> dict[str, Any] | None:
        """
        Get full introspection details for a capability.
        
        Returns comprehensive information including:
        - Full signature
        - Parameter details
        - Return type
        - Complete docstring
        - Examples
        - Source location
        """
        meta = self._capabilities.get(name)
        if not meta:
            return None
        
        return {
            "name": meta.name,
            "category": meta.category,
            "subcategory": meta.subcategory,
            "description": meta.description,
            "signature": meta.signature,
            "parameters": meta.parameters,
            "return_type": meta.return_type,
            "docstring": meta.docstring,
            "examples": meta.examples,
            "source_module": meta.source_module,
            "source_file": meta.source_file,
        }
    
    def search_capabilities(self, query: str) -> list[CapabilityInfo]:
        """
        Search capabilities by name or description.
        
        Args:
            query: Search query (searches in name and description)
        
        Returns:
            List of matching capabilities
        """
        query_lower = query.lower()
        matches: list[CapabilityInfo] = []
        
        for name, meta in self._capabilities.items():
            if (query_lower in name.lower() or 
                query_lower in (meta.description or "").lower() or
                query_lower in (meta.docstring or "").lower()):
                
                params_str = ", ".join(meta.parameters.keys()) if meta.parameters else "()"
                usage = f"{name}({params_str})"
                
                matches.append(CapabilityInfo(
                    name=name,
                    category=meta.category,
                    subcategory=meta.subcategory,
                    description=meta.description or meta.docstring.split("\n")[0] if meta.docstring else "",
                    usage=usage,
                    parameters=meta.parameters,
                    examples=meta.examples,
                    introspection_command=f"introspect_capability(name=\"{name}\")",
                ))
        
        return matches
    
    def get_categories(self) -> dict[str, list[str]]:
        """Get all categories and their subcategories."""
        return {
            cat: list(subcats.keys()) if subcats else []
            for cat, subcats in self._by_subcategory.items()
        }


def extract_function_metadata(func: Callable[..., Any], *, name: str | None = None) -> CapabilityMetadata:
    """
    Extract metadata from a function.
    
    Args:
        func: Function to introspect
        name: Optional name override
    
    Returns:
        CapabilityMetadata with extracted information
    """
    name = name or func.__name__
    
    # Get signature
    try:
        sig = inspect.signature(func)
        sig_str = str(sig)
    except Exception:
        sig_str = "()"
    
    # Get docstring
    docstring = inspect.getdoc(func) or ""
    
    # Extract parameters
    parameters: dict[str, Any] = {}
    try:
        for param_name, param in sig.parameters.items():
            param_info: dict[str, Any] = {}
            
            # Type annotation
            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = str(param.annotation)
            
            # Default value
            if param.default != inspect.Parameter.empty:
                param_info["default"] = str(param.default)
            
            # Required
            param_info["required"] = param.default == inspect.Parameter.empty
            
            parameters[param_name] = param_info
    except Exception:
        pass
    
    # Get return type
    return_type = None
    try:
        if sig.return_annotation != inspect.Signature.empty:
            return_type = str(sig.return_annotation)
    except Exception:
        pass
    
    # Get source file
    source_file = ""
    source_module = ""
    try:
        source_file = inspect.getfile(func)
        source_module = func.__module__
    except Exception:
        pass
    
    return CapabilityMetadata(
        name=name,
        category="unknown",
        description=docstring.split("\n")[0] if docstring else "",
        signature=f"{name}{sig_str}",
        parameters=parameters,
        return_type=return_type,
        docstring=docstring,
        source_module=source_module,
        source_file=source_file,
    )


# Global inventory instance
_inventory: CapabilityInventory | None = None


def get_inventory() -> CapabilityInventory:
    """Get the global capability inventory."""
    global _inventory
    if _inventory is None:
        _inventory = CapabilityInventory()
        try:
            from .auto_discovery import discover_all_capabilities
            discover_all_capabilities(_inventory)
        except Exception as e:
            log.warning("failed_to_load_capabilities", error=str(e))
    return _inventory
