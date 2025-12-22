# Memory System Improvements - Inspired by Letta's Approach

## Executive Summary

Your current memory system is already sophisticated with multiple memory types, provenance tracking, and intelligent retrieval. However, comparing it to Letta's stateful agent architecture reveals opportunities to make memory management more autonomous, persistent, and agent-centric.

## Current System Strengths

✅ **Multi-type memory system** (EPISODIC, SEMANTIC, PROCEDURAL, etc.)
✅ **Provenance tracking** (full traceability of memory origins)
✅ **Scope-based organization** (USER, RFP, CHANNEL, THREAD hierarchies)
✅ **Intelligent retrieval** (relevance scoring, keyword matching, OpenSearch)
✅ **Memory compression** (summarizing old memories)
✅ **Memory tools** (agents can store/search memories)
✅ **Context-aware expansion** (automatic scope expansion)

## Key Gaps vs. Letta's Approach

### 1. **Self-Editing Memory** (High Priority)

**Current State:**

- Agents can store memories via tools, but updates require explicit tool calls
- No automatic detection of when existing memories should be updated
- Semantic memory creates new entries rather than updating existing ones

**Letta Approach:**

- Agents actively decide when to update existing memories vs. create new ones
- Built-in tools for editing memory blocks
- Automatic conflict detection and resolution

**Recommendation:**

```python
# Add to agent_memory.py
def update_existing_memory(
    *,
    memory_id: str,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
    reason: str,  # Why this update is happening
) -> dict[str, Any]:
    """
    Update an existing memory with new information.
    Tracks update history and reasons.
    """
    # Check if update is significant enough
    # Merge metadata intelligently
    # Preserve provenance chain
    # Update access patterns
```

**Implementation Steps:**

1. Add `update_memory_block` tool for agents
2. Implement memory similarity detection (find existing memories to update)
3. Add update history tracking in metadata
4. Create conflict resolution logic (when memories contradict)

### 2. **Memory Blocks as First-Class Entities** (High Priority)

**Current State:**

- Memories are stored but not organized into durable "blocks"
- No concept of memory blocks that agents can reference and edit
- User/tenant memory blocks exist separately from agent memory

**Letta Approach:**

- Memory blocks are durable, agent-readable entities
- Agents can read, write, and edit specific blocks
- Blocks have titles, content, tags, and metadata
- Blocks persist across sessions

**Recommendation:**

```python
# Enhance agent_memory.py with block management
def create_memory_block(
    *,
    user_sub: str,
    block_id: str,  # Agent-assigned or auto-generated
    title: str,
    content: str,
    memory_type: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a durable memory block that agents can reference and edit.
    Similar to Letta's memory blocks but integrated with your memory types.
    """
    # Store as a special memory type or enhance existing
    # Enable direct block_id lookups
    # Support block versioning
```

**Implementation Steps:**

1. Add `MEMORY_BLOCK` as a special memory type or enhance existing types
2. Create block management functions (create, read, update, delete)
3. Add block_id to memory schema for direct lookups
4. Implement block versioning for edit history

### 3. **Context Hierarchy Management** (Medium Priority)

**Current State:**

- Context is built ad-hoc in `agent_context_builder.py`
- No explicit hierarchy or prioritization rules
- Token budget awareness exists but not fully integrated

**Letta Approach:**

- Explicit context hierarchy (recent messages → memory blocks → archival memory)
- Intelligent context window management
- Progressive loading based on relevance and budget

**Recommendation:**

```python
# Add to agent_context_builder.py
class ContextHierarchy:
    """
    Manages context loading in priority order:
    1. Recent messages (last N messages)
    2. Active memory blocks (highly relevant, recently accessed)
    3. Relevant episodic memories (query-matched)
    4. Semantic memories (preferences, patterns)
    5. Procedural memories (workflows)
    6. Archival/compressed memories (summaries)
    """
    def build_hierarchical_context(
        self,
        *,
        token_budget: int,
        query: str,
        user_sub: str,
        rfp_id: str | None = None,
    ) -> str:
        # Load in priority order until budget exhausted
        # Track what was included for debugging
```

**Implementation Steps:**

1. Create `ContextHierarchy` class
2. Integrate with existing `build_memory_context`
3. Add token budget tracking throughout
4. Implement progressive loading (most important first)

### 4. **Intelligent Compaction Settings** (Medium Priority)

**Current State:**

- Compression exists but is manual/scheduled
- No automatic compaction based on access patterns
- Compression doesn't consider memory importance

**Letta Approach:**

- Configurable compaction settings
- Automatic compaction based on access frequency and age
- Importance-aware compression (preserve important memories)

**Recommendation:**

```python
# Enhance agent_memory_compression.py
class CompactionSettings:
    """
    Configurable compaction rules:
    - Age threshold (days)
    - Access count threshold
    - Importance threshold
    - Compression strategy (summarize vs. archive)
    """
    def should_compress(
        self,
        memory: dict[str, Any],
        settings: dict[str, Any],
    ) -> bool:
        # Check age, access count, importance
        # Return True if should compress
```

**Implementation Steps:**

1. Add `CompactionSettings` class
2. Integrate importance scoring from `agent_memory_consolidation`
3. Create per-scope compaction settings
4. Add automatic compaction triggers

### 5. **Single Perpetual Message History** (Low Priority - Architectural)

**Current State:**

- Messages are stored in Slack threads
- No unified message history per agent/user
- Context is rebuilt from scratch each time

**Letta Approach:**

- Single perpetual message history per agent
- All interactions are part of persistent memory
- No concept of "threads" - just continuous history

**Recommendation:**
This is a larger architectural change. Consider:

- Storing message history in memory system
- Linking messages to memories automatically
- Building context from message history + memories

**Implementation Steps:**

1. Design message history storage schema
2. Create message-to-memory linking
3. Update context building to use message history
4. Migrate existing thread-based approach

### 6. **Memory Relationship Graph Enhancement** (Medium Priority)

**Current State:**

- `agent_memory_relationships.py` exists but may be underutilized
- Relationships are created but not actively used in retrieval

**Letta Approach:**

- Memory relationships enable graph traversal
- Related memories are retrieved together
- Relationship types guide retrieval strategies

**Recommendation:**

```python
# Enhance agent_memory_retrieval.py
def retrieve_with_relationships(
    *,
    memory_id: str,
    relationship_types: list[str] | None = None,
    depth: int = 1,
) -> list[dict[str, Any]]:
    """
    Retrieve memories related to a given memory.
    Traverse relationship graph to find connected memories.
    """
    # Use agent_memory_relationships to traverse graph
    # Return related memories sorted by relationship strength
```

**Implementation Steps:**

1. Enhance relationship creation in memory hooks
2. Add relationship-aware retrieval
3. Use relationships in relevance scoring
4. Visualize memory graphs for debugging

### 7. **Autonomous Memory Decision Making** (High Priority)

**Current State:**

- Agents must explicitly call memory tools
- No automatic detection of "should I remember this?"
- Memory hooks exist but are post-interaction only

**Letta Approach:**

- Agents autonomously decide what to remember
- Built-in prompts guide memory formation
- Automatic memory updates when information changes

**Recommendation:**

```python
# Add to agent_memory_tools.py or create agent_memory_autonomous.py
def should_store_memory(
    *,
    conversation_context: dict[str, Any],
    agent_response: str,
    user_message: str,
) -> dict[str, Any] | None:
    """
    Use LLM to determine if this interaction should be stored.
    Returns memory type and content if should store, None otherwise.
    """
    # Use lightweight LLM call to classify:
    # - Is this a preference/pattern? → SEMANTIC
    # - Is this a decision/outcome? → EPISODIC
    # - Is this a workflow? → PROCEDURAL
    # - Should I update existing memory? → Check for similar memories
```

**Implementation Steps:**

1. Create autonomous memory decision function
2. Integrate into agent interaction hooks
3. Add to agent system prompts (guidance on when to remember)
4. Track decision accuracy over time

### 8. **Memory Importance and Access Patterns** (Medium Priority)

**Current State:**

- Access counting exists (`accessCount`)
- Importance scoring exists in `agent_memory_consolidation`
- Not fully integrated into retrieval prioritization

**Letta Approach:**

- Memories are ranked by importance and recency
- Frequently accessed memories are prioritized
- Important memories are preserved during compression

**Recommendation:**

```python
# Enhance agent_memory_retrieval.py
def _calculate_relevance_score(
    memory: dict[str, Any],
    query_keywords: list[str],
    # ... existing params ...
    use_importance: bool = True,  # NEW
) -> float:
    """
    Enhanced relevance scoring with importance integration.
    """
    # ... existing scoring ...

    if use_importance:
        importance = calculate_importance_score(memory)
        # Blend importance into final score (30% weight)
        final_score = final_score * 0.7 + importance * 0.3

    return final_score
```

**Implementation Steps:**

1. Integrate importance scoring into relevance calculation
2. Update access patterns more frequently
3. Use importance in compression decisions
4. Add importance-based retrieval filters

## Implementation Priority

### Phase 1: High-Impact, Low-Effort (1-2 weeks)

1. ✅ **Self-editing memory** - Add update_memory_block tool
2. ✅ **Autonomous memory decisions** - Add should_store_memory function
3. ✅ **Importance integration** - Enhance relevance scoring

### Phase 2: Medium-Impact (2-4 weeks)

4. ✅ **Memory blocks** - Create block management system
5. ✅ **Context hierarchy** - Implement ContextHierarchy class
6. ✅ **Relationship graph** - Enhance relationship-aware retrieval

### Phase 3: Advanced Features (4-8 weeks)

7. ✅ **Compaction settings** - Configurable compaction rules
8. ✅ **Message history** - Unified message history storage

## Code Examples

### Example 1: Self-Editing Memory Tool

```python
def _memory_update_block_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing memory block with new information.
    """
    memory_id = args.get("memoryId")
    content = args.get("content")
    reason = args.get("reason", "Information update")

    # Find existing memory
    existing = get_memory(memory_id=memory_id, ...)

    # Check if update is significant
    similarity = calculate_similarity(existing["content"], content)
    if similarity > 0.95:
        return {"ok": False, "error": "No significant change"}

    # Update with history tracking
    updated = update_memory(
        memory_id=memory_id,
        content=content,
        metadata={
            **existing.get("metadata", {}),
            "updateHistory": existing.get("metadata", {}).get("updateHistory", []) + [{
                "timestamp": _now_iso(),
                "reason": reason,
                "previousContent": existing["content"][:200],
            }],
        },
    )

    return {"ok": True, "memory": updated}
```

### Example 2: Autonomous Memory Decision

```python
def should_store_memory_autonomous(
    *,
    user_message: str,
    agent_response: str,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Use LLM to determine if and how to store this interaction.
    """
    from ..ai.verified_calls import call_text_verified

    prompt = f"""Analyze this interaction and determine if it should be stored in memory.

User: {user_message}
Agent: {agent_response}
Context: {json.dumps(context, indent=2)}

Determine:
1. Should this be stored? (yes/no)
2. If yes, what type? (EPISODIC, SEMANTIC, PROCEDURAL, or NONE)
3. What is the key information to remember? (extract)
4. Is this updating existing knowledge? (yes/no + which memory if known)

Respond in JSON format:
{{
    "shouldStore": true/false,
    "memoryType": "EPISODIC|SEMANTIC|PROCEDURAL|NONE",
    "content": "key information to remember",
    "isUpdate": true/false,
    "updateMemoryId": "memory_id if updating",
    "key": "key name if SEMANTIC",
    "value": "value if SEMANTIC"
}}"""

    response, _ = call_text_verified(
        purpose="memory_decision",
        messages=[
            {"role": "system", "content": "You are a memory management assistant."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=500,
        temperature=0.2,
    )

    # Parse and return decision
    try:
        decision = json.loads(response)
        if decision.get("shouldStore"):
            return decision
    except:
        pass

    return None
```

### Example 3: Context Hierarchy

```python
class ContextHierarchy:
    def build_hierarchical_context(
        self,
        *,
        token_budget_tracker: Any,
        query: str,
        user_sub: str,
        rfp_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build context in priority order until budget exhausted.
        Returns (context_string, metadata_about_what_was_included)
        """
        context_parts: list[str] = []
        included: dict[str, Any] = {
            "recent_messages": 0,
            "active_blocks": 0,
            "episodic_memories": 0,
            "semantic_memories": 0,
            "procedural_memories": 0,
            "archival_memories": 0,
        }

        # Priority 1: Recent messages (if available)
        if token_budget_tracker.remaining() > 1000:
            messages = get_recent_messages(user_sub=user_sub, limit=10)
            for msg in messages:
                msg_text = format_message(msg)
                if token_budget_tracker.can_add(msg_text):
                    context_parts.append(f"Recent: {msg_text}")
                    included["recent_messages"] += 1
                    token_budget_tracker.add(msg_text)

        # Priority 2: Active memory blocks (high importance, recent access)
        if token_budget_tracker.remaining() > 500:
            blocks = get_active_memory_blocks(
                user_sub=user_sub,
                query=query,
                limit=5,
            )
            for block in blocks:
                block_text = format_block(block)
                if token_budget_tracker.can_add(block_text):
                    context_parts.append(f"Memory Block: {block_text}")
                    included["active_blocks"] += 1
                    token_budget_tracker.add(block_text)

        # Priority 3: Relevant episodic memories
        if token_budget_tracker.remaining() > 500:
            episodic = retrieve_relevant_memories(
                scope_id=f"USER#{user_sub}",
                memory_types=[MemoryType.EPISODIC],
                query_text=query,
                limit=5,
            )
            for mem in episodic:
                mem_text = format_memory(mem)
                if token_budget_tracker.can_add(mem_text):
                    context_parts.append(f"Episodic: {mem_text}")
                    included["episodic_memories"] += 1
                    token_budget_tracker.add(mem_text)

        # Continue with semantic, procedural, archival...

        return "\n\n".join(context_parts), included
```

## Testing Strategy

1. **Unit Tests**: Test each new function in isolation
2. **Integration Tests**: Test memory tools with agent interactions
3. **E2E Tests**: Test full memory lifecycle (store → retrieve → update → compress)
4. **Performance Tests**: Measure retrieval latency, compression time
5. **Accuracy Tests**: Validate autonomous memory decisions

## Migration Path

1. **Backward Compatibility**: All new features should work alongside existing system
2. **Gradual Rollout**: Enable features per-agent or per-tenant
3. **Monitoring**: Track memory usage, retrieval patterns, compression effectiveness
4. **Rollback Plan**: Feature flags for easy disable if issues arise

## Success Metrics

- **Memory Update Rate**: % of memories that are updated vs. new
- **Retrieval Relevance**: User satisfaction with memory-based responses
- **Compression Effectiveness**: % of old memories successfully compressed
- **Autonomous Decision Accuracy**: % of correct autonomous memory decisions
- **Context Quality**: Token efficiency (relevant info per token)

## Conclusion

Your memory system is already strong. The Letta-inspired improvements focus on making it more autonomous, persistent, and agent-centric. The highest-impact changes are:

1. **Self-editing memory** - Agents can update existing memories
2. **Autonomous decisions** - Agents decide what to remember
3. **Memory blocks** - Durable, editable memory entities
4. **Context hierarchy** - Intelligent, budget-aware context loading

These changes will make your agents more stateful, persistent, and capable of building long-term relationships with users.
