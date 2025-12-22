"""
Introspection system for agent capability discovery.

Provides comprehensive inventory and introspection of:
- Tools
- Skills  
- Domain functions
- Repository methods
- Shared utilities
"""

from .capability_inventory import (
    CapabilityInventory,
    CapabilityMetadata,
    CapabilityInfo,
    get_inventory,
    extract_function_metadata,
)

# Lazy imports to avoid circular dependencies
def get_introspection_tools():
    from .introspection_tools import get_introspection_tools as _get
    return _get()

def discover_all_capabilities(inventory: CapabilityInventory) -> None:
    from .auto_discovery import discover_all_capabilities as _discover
    return _discover(inventory)

__all__ = [
    "CapabilityInventory",
    "CapabilityMetadata",
    "CapabilityInfo",
    "get_inventory",
    "extract_function_metadata",
    "get_introspection_tools",
    "discover_all_capabilities",
]
