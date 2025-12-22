# Memory System Improvements - Quick Reference

## Quick Start

### Enable Autonomous Memory Decisions

```python
from .agent_memory_hooks import store_episodic_memory_from_agent_interaction

store_episodic_memory_from_agent_interaction(
    user_sub="user123",
    user_message="I prefer morning meetings",
    agent_response="Noted, I'll schedule morning meetings",
    use_autonomous_decision=True,  # Enable autonomous mode
)
```

### Use Context Hierarchy

```python
from .agent_context_builder import build_memory_context
from .token_budget_tracker import TokenBudgetTracker

tracker = TokenBudgetTracker.from_time_budget(minutes=15)
context = build_memory_context(
    user_sub="user123",
    query_text="user preferences",
    use_hierarchy=True,  # Enable hierarchy
    token_budget_tracker=tracker,
)
```

### Create and Update Memory Blocks

```python
from .agent_memory_blocks import create_memory_block, update_memory_block

# Create block
block = create_memory_block(
    user_sub="user123",
    block_id="preferences",
    title="User Preferences",
    content="Prefers morning meetings",
)

# Update block
updated = update_memory_block(
    user_sub="user123",
    block_id="preferences",
    content="Prefers morning meetings, uses Slack",
)
```

### Update Existing Memory

```python
from .agent_memory import update_existing_memory

updated = update_existing_memory(
    memory_id="mem_abc123",
    memory_type=MemoryType.SEMANTIC,
    scope_id="USER#user123",
    created_at="2024-01-01T00:00:00Z",
    content="Updated preference: morning meetings",
    reason="User confirmed change",
)
```

## Tool Usage Examples

### Agent Memory Update Tool

```json
{
  "name": "agent_memory_update_block",
  "arguments": {
    "memoryId": "mem_abc123",
    "memoryType": "SEMANTIC",
    "scopeId": "USER#user123",
    "createdAt": "2024-01-01T00:00:00Z",
    "content": "Updated content",
    "reason": "Information update"
  }
}
```

### Agent Memory Block Tools

```json
{
  "name": "agent_memory_create_block",
  "arguments": {
    "userSub": "user123",
    "blockId": "preferences",
    "title": "User Preferences",
    "content": "Prefers morning meetings"
  }
}
```

### Agent Memory Get Related

```json
{
  "name": "agent_memory_get_related",
  "arguments": {
    "memoryId": "mem_abc123",
    "memoryType": "EPISODIC",
    "scopeId": "USER#user123",
    "createdAt": "2024-01-01T00:00:00Z",
    "depth": 2
  }
}
```

## Feature Flags

All features are opt-in via parameters:

- `use_autonomous_decision=False` - Enable autonomous memory decisions
- `use_hierarchy=False` - Enable context hierarchy
- `use_importance=True` - Use importance in relevance scoring (default: True)
- `use_compaction_settings=True` - Use compaction settings (default: True)

## Key Functions

### Similarity & Updates

- `find_similar_memories()` - Find similar memories
- `find_memory_to_update()` - Find memory to update
- `update_existing_memory()` - Update with history

### Autonomous Decisions

- `should_store_memory_autonomous()` - LLM-based decision

### Memory Blocks

- `create_memory_block()` - Create block
- `get_memory_block()` - Get by block_id
- `update_memory_block()` - Update with versioning

### Relationships

- `auto_detect_relationships()` - Auto-detect
- `retrieve_with_relationships()` - Graph traversal
- `get_related_memories()` - Get related

### Context Hierarchy

- `ContextHierarchy.build_hierarchical_context()` - Progressive loading

### Compaction

- `CompactionSettings.should_compress()` - Check if should compress

### Message History

- `store_message()` - Store message
- `get_recent_messages()` - Get recent
- `link_message_to_memory()` - Link to memory
