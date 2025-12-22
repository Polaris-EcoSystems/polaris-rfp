"""
Prompt helper for agents - generates capability discovery prompts.

Provides formatted capability lists for agent system prompts.
"""

from __future__ import annotations

from typing import Any

from .capability_inventory import get_inventory
from ...observability.logging import get_logger

log = get_logger("prompt_helper")


def generate_capability_summary(
    *,
    category: str | None = None,
    limit: int = 50,
) -> str:
    """
    Generate a formatted summary of capabilities for agent prompts.
    
    Returns a concise, agent-readable summary that can be included in system prompts.
    """
    inventory = get_inventory()
    capabilities = inventory.list_capabilities(category=category)
    
    if not capabilities:
        return "No capabilities available."
    
    lines = [f"Available capabilities ({len(capabilities)} total):"]
    lines.append("")
    lines.append("Use `list_capabilities()` to see all, or `introspect_capability(name=\"...\")` for details.")
    lines.append("")
    
    # Group by category
    by_category: dict[str, list[Any]] = {}
    for cap in capabilities[:limit]:
        if cap.category not in by_category:
            by_category[cap.category] = []
        by_category[cap.category].append(cap)
    
    for cat, caps in sorted(by_category.items()):
        lines.append(f"## {cat.upper()}")
        if caps[0].subcategory:
            # Group by subcategory
            by_subcat: dict[str, list[Any]] = {}
            for cap in caps:
                subcat = cap.subcategory or "other"
                if subcat not in by_subcat:
                    by_subcat[subcat] = []
                by_subcat[subcat].append(cap)
            
            for subcat, subcaps in sorted(by_subcat.items()):
                lines.append(f"### {subcat}")
                for cap in subcaps[:20]:  # Limit per subcategory
                    lines.append(f"- {cap.name}: {cap.description[:100]}")
                    lines.append(f"  Usage: {cap.usage}")
                    lines.append(f"  Introspect: {cap.introspection_command}")
        else:
            for cap in caps[:20]:
                lines.append(f"- {cap.name}: {cap.description[:100]}")
                lines.append(f"  Usage: {cap.usage}")
                lines.append(f"  Introspect: {cap.introspection_command}")
        lines.append("")
    
    if len(capabilities) > limit:
        lines.append(f"... and {len(capabilities) - limit} more. Use list_capabilities() to see all.")
    
    return "\n".join(lines)


def generate_introspection_guide() -> str:
    """
    Generate a guide for agents on how to use introspection.
    
    Returns formatted text explaining the introspection system.
    """
    return """## Capability Introspection Guide

You have access to a comprehensive capability inventory system. Here's how to use it:

### Discovery Commands

1. **List all capabilities:**
   ```
   list_capabilities()
   ```
   Returns all available tools, skills, domain functions, and repository methods.

2. **Filter by category:**
   ```
   list_capabilities(category="tool")
   list_capabilities(category="skill")
   list_capabilities(category="domain")
   list_capabilities(category="repository")
   ```

3. **Filter by subcategory:**
   ```
   list_capabilities(category="tool", subcategory="aws")
   list_capabilities(category="repository", subcategory="rfp")
   ```

4. **Search capabilities:**
   ```
   search_capabilities(query="rfp")
   search_capabilities(query="slack")
   ```

5. **Get full details:**
   ```
   introspect_capability(name="get_rfp_by_id")
   introspect_capability(name="aws_ecs_describe_service")
   ```

### Categories

- **tools**: Agent-executable tools (aws_*, slack_*, etc.)
- **skills**: Stored procedures and workflows
- **domain**: Business logic functions (rfp_logic.*, etc.)
- **repository**: Data access methods (rfps_repo.*, etc.)
- **shared**: Shared utility functions

### Usage Pattern

1. Discover what's available: `list_capabilities()` or `search_capabilities(query="...")`
2. Get details: `introspect_capability(name="...")` 
3. Use the capability based on the introspection details

All capabilities are automatically discovered and indexed. You don't need to know them ahead of time - just search and introspect!
"""


def get_capability_prompt_section() -> str:
    """
    Get the capability discovery section for agent system prompts.
    
    Returns formatted text that should be included in agent system prompts.
    """
    summary = generate_capability_summary(limit=30)
    guide = generate_introspection_guide()
    
    return f"""
{guide}

---

## Quick Reference

{summary}

---

Remember: You can always use `list_capabilities()`, `search_capabilities(query="...")`, or `introspect_capability(name="...")` to discover and understand any capability.
"""
