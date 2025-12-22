# Capability Introspection System

## Overview

The capability introspection system provides agents with comprehensive discovery and introspection of all available capabilities:

- **Tools** - Agent-executable tools (AWS, Slack, RFP, Memory, etc.)
- **Skills** - Stored procedures and workflows
- **Domain Functions** - Business logic functions (RFP logic, analysis, etc.)
- **Repository Methods** - Data access methods (RFPs, proposals, users, etc.)
- **Shared Utilities** - Shared utility functions

## Architecture

### Components

1. **CapabilityInventory** (`shared/introspection/capability_inventory.py`)

   - Central registry of all capabilities
   - Indexed by category and subcategory
   - Provides search and introspection

2. **Introspection Tools** (`shared/introspection/introspection_tools.py`)

   - Agent-accessible tools for discovery
   - `list_capabilities` - List all capabilities
   - `introspect_capability` - Get full details
   - `search_capabilities` - Search by query
   - `get_capability_categories` - Get categories

3. **Auto-Discovery** (`shared/introspection/auto_discovery.py`)

   - Automatically discovers capabilities from modules
   - Scans tools, skills, domains, repositories
   - Extracts metadata (signatures, docstrings, parameters)

4. **Prompt Helper** (`shared/introspection/prompt_helper.py`)
   - Generates capability summaries for agent prompts
   - Provides formatted discovery guides

## Usage

### For Agents

Agents can use introspection tools to discover capabilities:

```python
# List all capabilities
list_capabilities()

# List tools only
list_capabilities(category="tool")

# List AWS tools
list_capabilities(category="tool", subcategory="aws")

# Search for RFP-related capabilities
search_capabilities(query="rfp")

# Get full details about a capability
introspect_capability(name="get_rfp_by_id")
```

### For Developers

Include capability discovery in agent system prompts:

```python
from app.shared.introspection.prompt_helper import get_capability_prompt_section

system_prompt = f"""
You are an AI agent with access to many capabilities.

{get_capability_prompt_section()}

Use the introspection tools to discover what's available.
"""
```

## Capability Metadata

Each capability includes:

- **Name** - Unique identifier
- **Category** - tool, skill, domain, repository, shared
- **Subcategory** - e.g., "aws", "slack", "rfp"
- **Description** - What it does
- **Signature** - Function signature
- **Parameters** - Parameter details (type, required, default)
- **Return Type** - What it returns
- **Docstring** - Full documentation
- **Examples** - Usage examples (when available)
- **Source** - Module and file location

## Auto-Discovery

The system automatically discovers:

- **Tools** - From tool registry
- **Skills** - From skills repository
- **Domain Functions** - From domain modules (rfp_logic, rfp_analyzer, etc.)
- **Repository Methods** - From repository modules (rfps_repo, proposals_repo, etc.)

Discovery happens on first access to the inventory.

## Integration

### Adding to Agent Prompts

The introspection system is automatically available to agents via tools. To include a summary in system prompts:

```python
from app.shared.introspection.prompt_helper import get_capability_prompt_section

# Include in agent system prompt
prompt = f"""
{base_prompt}

{get_capability_prompt_section()}
"""
```

### Tool Registration

Introspection tools are automatically registered in the tool registry:

```python
from app.tools.registry.read_registry import READ_TOOLS

# Tools available:
# - list_capabilities
# - introspect_capability
# - search_capabilities
# - get_capability_categories
```

## Benefits

1. **Self-Discovery** - Agents can discover capabilities without hardcoding
2. **Reduced Prompting** - No need to list all capabilities in prompts
3. **Dynamic** - New capabilities automatically discovered
4. **Comprehensive** - Covers tools, skills, domains, repositories
5. **Introspectable** - Full details available on demand

## Example Agent Usage

```
Agent: "I need to work with RFPs. What capabilities do I have?"

System: [Calls list_capabilities(category="repository", subcategory="rfp")]

Agent: "I see get_rfp_by_id. What are its parameters?"

System: [Calls introspect_capability(name="rfps_repo.get_rfp_by_id")]

Agent: "Perfect! Now I can use it."
```

## Future Enhancements

- Add usage examples to capabilities
- Track capability usage statistics
- Provide capability recommendations based on context
- Add capability versioning
- Support capability deprecation warnings
