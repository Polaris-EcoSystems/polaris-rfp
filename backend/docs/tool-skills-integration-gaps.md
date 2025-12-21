# Tool and Skills Integration Gaps Analysis

## Current State

### ✅ What's Working

1. **Tool Registration**: Tools are properly registered in `OPERATOR_TOOLS` and `READ_TOOLS`
2. **Tool Tracking**: Agent tracks `recent_tools` for complexity detection
3. **Metaprompting**: Agent generates metaprompts that extract relevant tool categories
4. **Tool Categories**: System prompt includes relevant tool categories based on metaprompt
5. **Skills System Exists**: Skills repository and tools (`skills_search`, `skills_get`, `skills_load`) are available

### ❌ What's Missing

1. **Procedural Memory Storage**: Agent tracks tools but never stores procedural memory from successful sequences
2. **Procedural Memory Retrieval**: Agent doesn't retrieve past successful workflows to guide tool selection
3. **Skills Integration**: Skills system exists but isn't integrated into agent awareness or recommendations
4. **Tool Usage Patterns in Context**: Procedural memories aren't included in context to guide tool selection
5. **Tool Success/Failure Learning**: Agent doesn't learn from tool failures or track tool effectiveness
6. **Tool Recommendations**: No memory-based tool recommendations based on similar past requests

---

## Missing Integrations

### 1. Store Procedural Memory After Successful Tool Sequences

**Current**: Agent tracks `recent_tools` but never stores them as procedural memory.

**Should Do**: After a successful interaction (when `did_post=True` or user confirms success), store procedural memory with the tool sequence.

**Implementation**:

- Call `store_procedural_memory_from_tool_sequence()` after successful interactions
- Include tool sequence, outcome, and context
- Link to episodic memory for the interaction

### 2. Retrieve Procedural Memories for Tool Guidance

**Current**: Agent doesn't retrieve procedural memories to guide tool selection.

**Should Do**: When building context, retrieve relevant procedural memories that match the current request pattern.

**Implementation**:

- Query procedural memories by keywords from user query
- Include successful tool sequences in system prompt
- Show patterns like: "For similar requests, this tool sequence worked: X → Y → Z"

### 3. Skills System Integration

**Current**: Skills exist but agent isn't aware of them or doesn't recommend them.

**Should Do**:

- Include skills in tool inventory awareness
- Retrieve relevant skills based on user query
- Suggest skills when appropriate
- Link skills to tool sequences in procedural memory

**Implementation**:

- Add skills context to system prompt when relevant
- Use `skills_search` to find relevant skills
- Include skills in metaprompt analysis

### 4. Tool Usage Patterns in Context

**Current**: System prompt mentions tools but doesn't include past successful patterns.

**Should Do**: Include procedural memories in context to show what worked before.

**Implementation**:

- Query procedural memories in `build_comprehensive_context`
- Format successful tool sequences for system prompt
- Include in "Relevant Tool Patterns" section

### 5. Tool Success/Failure Tracking

**Current**: Agent doesn't track which tools succeed or fail.

**Should Do**:

- Track tool outcomes (success/failure)
- Store failure patterns in procedural memory (with `success=False`)
- Use failure patterns to avoid repeating mistakes

**Implementation**:

- Detect tool failures (error responses)
- Store procedural memory with `success=False` for failures
- Include failure patterns in context to avoid repeating mistakes

### 6. Memory-Based Tool Recommendations

**Current**: Tool selection is based on metaprompt keywords only.

**Should Do**: Use memory to recommend tools based on similar past requests.

**Implementation**:

- Query episodic memories for similar requests
- Extract tool sequences from related procedural memories
- Include in system prompt as "Similar past requests used these tools: ..."

---

## Implementation Status

### ✅ Completed

1. **Store procedural memory after successful sequences** ✅

   - Implemented in both chat_tools and Responses API paths
   - Stores tool sequence, outcome, and context
   - Only stores if `did_post=True` (successful completion)

2. **Retrieve procedural memories for tool guidance** ✅

   - Retrieves relevant procedural memories based on user query
   - Includes successful tool patterns in system prompt
   - Shows top 3 patterns with tool sequences

3. **Include procedural memories in context** ✅

   - Procedural memories included in `build_memory_context`
   - Tool sequences displayed in memory context
   - Formatted as "Tools: X → Y → Z | Workflow description"

4. **Skills system integration** ✅

   - Skills guidance added to system prompt when query mentions skills
   - Suggests using `skills_search`, `skills_get`, `skills_load` tools
   - Integrated into metaprompt analysis

5. **Tool success/failure tracking** ✅
   - Tracks tool failures and stores procedural memory with `success=False`
   - Stores failure patterns to avoid repeating mistakes
   - Includes error messages in failure memories

### 🔄 Future Enhancements

6. **Memory-based tool recommendations** - Could be enhanced further
   - Currently procedural memories are retrieved and shown
   - Could add more sophisticated pattern matching
   - Could suggest tools based on similar past requests more explicitly

---

## Implementation Details

### Store Procedural Memory

```python
# After successful interaction in run_slack_operator_for_mention
if did_post and recent_tools and actor_user_sub:
    try:
        from .agent_memory_hooks import store_procedural_memory_from_tool_sequence
        store_procedural_memory_from_tool_sequence(
            user_sub=actor_user_sub,
            tool_sequence=recent_tools,
            success=True,
            outcome=text or "Action completed",
            context={
                "rfpId": rfp_id,
                "channelId": ch,
                "threadTs": th,
                "steps": steps,
                "userQuery": q,
            },
            cognito_user_id=cognito_user_id_for_memory,
            slack_user_id=slack_user_id_for_memory,
            slack_channel_id=ch,
            slack_thread_ts=th,
            slack_team_id=slack_team_id_for_memory,
            rfp_id=rfp_id,
            source="slack_operator",
        )
    except Exception:
        pass  # Non-critical
```

### Retrieve Procedural Memories

```python
# In build_comprehensive_context or system prompt building
from .agent_memory_retrieval import get_memories_for_context

procedural_memories = get_memories_for_context(
    user_sub=user_sub,
    rfp_id=rfp_id,
    query_text=user_query,
    memory_types=["PROCEDURAL"],
    limit=5,
)

# Format for system prompt
if procedural_memories:
    tool_patterns = []
    for mem in procedural_memories:
        tool_seq = mem.get("metadata", {}).get("toolSequence", [])
        if tool_seq:
            tool_patterns.append(f"- {' → '.join(tool_seq)}")
    if tool_patterns:
        system += "\n\nPast Successful Tool Patterns:\n" + "\n".join(tool_patterns)
```

### Skills Integration

```python
# In metaprompt or system prompt building
if "skill" in user_query.lower() or "capability" in user_query.lower():
    try:
        from .agent_tools.read_registry import READ_TOOLS
        skills_tool = READ_TOOLS.get("skills_search")
        if skills_tool:
            # Suggest using skills_search tool
            system += "\n- Use `skills_search` to find relevant skills for this request"
    except Exception:
        pass
```
