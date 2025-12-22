"""
Automatic capability discovery.

Scans modules to automatically discover and register capabilities.
"""

from __future__ import annotations

import inspect
import importlib
from typing import Any

from .capability_inventory import CapabilityInventory, CapabilityMetadata, extract_function_metadata
from ...observability.logging import get_logger

log = get_logger("auto_discovery")


def discover_tools(inventory: CapabilityInventory) -> None:
    """Discover and register all tools."""
    try:
        from ...tools.registry.tool_registry_impl import get_global_registry
        registry = get_global_registry()
        tools = registry.list_tools()
        
        for tool_name, (tool_def, tool_fn) in tools.items():
            # Extract category from name
            category = "tool"
            subcategory = None
            if "_" in tool_name:
                parts = tool_name.split("_")
                if len(parts) > 1:
                    # Common prefixes
                    if parts[0] in ["aws", "slack", "github", "rfp", "memory", "agent"]:
                        subcategory = parts[0]
            
            # Extract parameter info
            parameters = {}
            if isinstance(tool_def, dict):
                params_schema = tool_def.get("parameters", {})
                if isinstance(params_schema, dict):
                    properties = params_schema.get("properties", {})
                    if isinstance(properties, dict):
                        parameters = properties
            
            meta = CapabilityMetadata(
                name=tool_name,
                category=category,
                subcategory=subcategory,
                description=tool_def.get("description", "") if isinstance(tool_def, dict) else "",
                parameters=parameters,
                docstring=tool_def.get("description", "") if isinstance(tool_def, dict) else "",
                source_module="tools.registry.read_registry",
            )
            inventory.register_capability(meta)
        
        log.info("tools_discovered", count=len(tools))
    except Exception as e:
        log.warning("failed_to_discover_tools", error=str(e))


def discover_skills(inventory: CapabilityInventory) -> None:
    """Discover and register all skills."""
    try:
        from ...skills.registry.skills_repo import list_skills
        skills = list_skills(limit=1000)
        
        for skill in skills:
            skill_id = skill.get("skillId") or skill.get("_id") or ""
            name = skill.get("name", skill_id)
            
            meta = CapabilityMetadata(
                name=name,
                category="skill",
                subcategory=None,
                description=skill.get("description", ""),
                docstring=skill.get("description", ""),
                source_module="skills.registry.skills_repo",
            )
            inventory.register_capability(meta)
        
        log.info("skills_discovered", count=len(skills))
    except Exception as e:
        log.warning("failed_to_discover_skills", error=str(e))


def discover_domain_functions(inventory: CapabilityInventory) -> None:
    """Discover domain functions."""
    domain_modules: list[tuple[str, str]] = [
        ("domain.rfp.rfp_logic", "rfp"),
        ("domain.rfp.rfp_analyzer", "rfp"),
    ]
    
    for module_path, subcategory in domain_modules:
        try:
            # Import from the app package
            full_path = f"app.{module_path}"
            module: Any = importlib.import_module(full_path)
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if not name.startswith("_"):
                    meta = extract_function_metadata(func, name=f"{module_path.split('.')[-1]}.{name}")
                    meta.category = "domain"
                    meta.subcategory = subcategory
                    inventory.register_capability(meta)
        except Exception as e:
            log.warning("failed_to_discover_domain", module=module_path, error=str(e))


def discover_repository_methods(inventory: CapabilityInventory) -> None:
    """Discover repository methods."""
    repo_modules: list[tuple[str, str]] = [
        ("repositories.rfp.rfps_repo", "rfp"),
        ("repositories.rfp.proposals_repo", "rfp"),
        ("repositories.rfp.opportunity_state_repo", "rfp"),
        ("repositories.rfp.agent_journal_repo", "rfp"),
        ("repositories.users.user_profiles_repo", "users"),
        ("repositories.users.user_memory_repo", "users"),
        ("repositories.users.tenant_memory_repo", "users"),
    ]
    
    for module_path, subcategory in repo_modules:
        try:
            # Import from the app package
            full_path = f"app.{module_path}"
            module: Any = importlib.import_module(full_path)
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if not name.startswith("_"):
                    meta = extract_function_metadata(func, name=f"{module_path.split('.')[-1]}.{name}")
                    meta.category = "repository"
                    meta.subcategory = subcategory
                    inventory.register_capability(meta)
        except Exception as e:
            log.warning("failed_to_discover_repository", module=module_path, error=str(e))


def discover_shared_utilities(inventory: CapabilityInventory) -> None:
    """Discover shared utility functions."""
    # Add shared utilities as needed
    pass


def discover_all_capabilities(inventory: CapabilityInventory) -> None:
    """Discover all capabilities from all sources."""
    discover_tools(inventory)
    discover_skills(inventory)
    discover_domain_functions(inventory)
    discover_repository_methods(inventory)
    discover_shared_utilities(inventory)
    
    log.info("capability_discovery_complete", total=len(inventory._capabilities))
