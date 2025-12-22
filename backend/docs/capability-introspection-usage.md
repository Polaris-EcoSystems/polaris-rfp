# Capability Introspection - Usage Guide

## Problem Solved

Previously, agents needed all capabilities listed in their system prompts, creating:

- **Huge prompts** - Hundreds of capabilities listed
- **Maintenance burden** - Updates require prompt changes
- **Limited discovery** - Agents can't find new capabilities
- **No introspection** - Can't get details about capabilities

## Solution

The introspection system provides:

- **Self-discovery** - Agents can list/search capabilities
- **On-demand introspection** - Get full details when needed
- **Automatic indexing** - New capabilities auto-discovered
- **Lightweight prompts** - Just include discovery guide

## How It Works

### 1. Agent System Prompt

Instead of listing all capabilities, include:

```python
from app.shared.introspection.prompt_helper import get_capability_prompt_section

system_prompt = f"""
You are an AI agent.

{get_capability_prompt_section()}

Use the introspection tools to discover capabilities as needed.
"""
```

This gives agents:

- Guide on how to use introspection
- Quick reference (top 30 capabilities)
- Commands to discover more

### 2. Agent Discovery Flow

```
Agent needs to work with RFPs
  ↓
Calls: search_capabilities(query="rfp")
  ↓
Gets list of RFP-related capabilities
  ↓
Calls: introspect_capability(name="rfps_repo.get_rfp_by_id")
  ↓
Gets full details (parameters, return type, docstring)
  ↓
Uses the capability
```

### 3. Available Tools

All agents automatically have access to:

**list_capabilities**

- List all capabilities
- Filter by category/subcategory
- Returns lightweight info

**introspect_capability**

- Get full details about a capability
- Parameters, return type, docstring, examples
- Source location

**search_capabilities**

- Search by name or description
- Useful for finding related capabilities

**get_capability_categories**

- Get all categories and subcategories
- Understand organization

## Example Agent Interaction

```
User: "Get me RFP rfp_123"

Agent: [Calls search_capabilities(query="rfp get")]
Agent: [Finds "rfps_repo.get_rfp_by_id"]
Agent: [Calls introspect_capability(name="rfps_repo.get_rfp_by_id")]
Agent: [Sees it takes rfp_id parameter]
Agent: [Calls get_rfp_by_id(rfp_id="rfp_123")]
Agent: [Returns RFP data]
```

## What Gets Discovered

### Tools

- All tools from tool registry
- Categorized by prefix (aws*\*, slack*\*, etc.)
- Includes parameter schemas

### Skills

- All skills from skills repository
- Includes description and metadata

### Domain Functions

- Functions from domain modules
- e.g., `rfp_logic.compute_fit_score`
- e.g., `rfp_analyzer.analyze_rfp`

### Repository Methods

- Methods from repository modules
- e.g., `rfps_repo.get_rfp_by_id`
- e.g., `proposals_repo.list_proposals`

### Shared Utilities

- Shared utility functions
- (Can be extended as needed)

## Benefits

1. **Reduced Prompt Size**

   - Before: 10,000+ tokens listing all capabilities
   - After: ~500 tokens with discovery guide

2. **Self-Service Discovery**

   - Agents find what they need
   - No hardcoding required

3. **Always Up-to-Date**

   - New capabilities automatically indexed
   - No prompt updates needed

4. **Better Understanding**

   - Full introspection available
   - Parameters, types, docstrings

5. **Flexible**
   - Search and filter
   - Categorized views

## Integration Points

### In Agent Prompts

```python
from app.shared.introspection.prompt_helper import get_capability_prompt_section

# Include in system prompt
prompt = base_prompt + get_capability_prompt_section()
```

### In Tool Registry

Introspection tools are automatically registered:

```python
from app.tools.registry.read_registry import READ_TOOLS

# Available:
# - list_capabilities
# - introspect_capability
# - search_capabilities
# - get_capability_categories
```

### Manual Discovery

```python
from app.shared.introspection import get_inventory

inventory = get_inventory()
capabilities = inventory.list_capabilities(category="tool")
details = inventory.introspect_capability("get_rfp_by_id")
```

## Prompt Template

Here's a template for agent system prompts:

```
You are an AI agent with access to many capabilities.

## Capability Discovery

You can discover and introspect capabilities using:

- list_capabilities() - List all capabilities
- search_capabilities(query="...") - Search by name/description
- introspect_capability(name="...") - Get full details

## Quick Reference

[Top 30 capabilities listed here]

## Usage Pattern

1. Discover: search_capabilities(query="your topic")
2. Introspect: introspect_capability(name="capability_name")
3. Use: Call the capability with proper parameters

All capabilities are automatically indexed. You don't need to know them ahead of time!
```

## Future Enhancements

- Usage examples for each capability
- Capability recommendations based on context
- Usage statistics and popularity
- Capability versioning
- Deprecation warnings
- Capability relationships (e.g., "similar to X")
