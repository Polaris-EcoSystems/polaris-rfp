# Agent Context Enhancement Guide

## Overview

This document describes the improvements made to contextualize prompts for the AI agent, making responses more relevant, accurate, and contextually aware.

## Key Improvements

### 1. Query-Aware Context Retrieval

**Before**: Context was retrieved based only on scope (user, RFP) without considering what the user is asking about.

**After**: The system now extracts keywords from the user's query and uses them to retrieve the most relevant memories and context.

**Benefits**:

- More relevant context included in prompts
- Better memory retrieval (semantic search)
- Reduced noise from irrelevant context
- Improved response quality

**Implementation**:

- Added `user_query` parameter to `build_comprehensive_context()`
- Keywords extracted from query using `extract_keywords()`
- Memory retrieval uses query text for semantic search via OpenSearch
- Query keywords also used to boost relevance of RFP-related context

### 2. Structured Context Organization

**Before**: Context was concatenated as simple text strings without clear structure.

**After**: Context is organized with:

- Clear section headers (USER_IDENTITY, CONVERSATION_HISTORY, RELEVANT_MEMORIES, etc.)
- Priority-based ordering
- Weight/importance metadata
- Source attribution

**Benefits**:

- Agent can more easily navigate context
- Priority-based truncation preserves important context
- Clear understanding of context sources
- Better context management under length limits

### 3. Enhanced Memory Context Formatting

**Before**: Memories were listed as a flat list with minimal formatting.

**After**: Memories are:

- Grouped by type (Episodic, Semantic, Procedural, Diagnostics)
- Include tags for better categorization
- Show dates for temporal context
- Include query match information

**Benefits**:

- Better organization for the agent to parse
- Easier to understand memory types and relevance
- Tags help agent understand context

### 4. Smart Context Truncation

**Before**: Simple truncation that might cut important context.

**After**: Priority-aware truncation that:

- Always preserves user identity (highest priority)
- Preserves recent conversation (essential for continuity)
- Preserves query-relevant memories
- Truncates lower-priority sections when needed
- Includes metadata about what was truncated

**Benefits**:

- Important context always included
- Better use of token budget
- Agent knows when context is truncated

### 5. Improved Keyword Extraction from Thread Context

**Before**: Memory retrieval didn't use thread context effectively.

**After**:

- Extracts keywords from recent thread messages
- Uses those keywords for memory search
- Better connection between conversation and memory

**Benefits**:

- Memories retrieved are more relevant to ongoing conversation
- Better continuity across conversation turns

## Context Priority Hierarchy

1. **User Identity** (Priority 1, Weight 1.0)

   - User profile, preferences, name, email
   - Always included, never truncated

2. **Conversation History** (Priority 2, Weight 0.9)

   - Recent thread messages
   - Very important for continuity

3. **Relevant Memories** (Priority 3, Weight 0.85-0.95)

   - Query-aware memory retrieval
   - Weight boosted if query keywords match

4. **RFP State** (Priority 4, Weight 0.8-0.9)

   - Current opportunity state
   - Weight boosted for RFP-related queries

5. **Related RFPs** (Priority 5, Weight 0.5)

   - Similar opportunities
   - Reference only, lower priority

6. **Recent Jobs** (Priority 6, Weight 0.6)

   - Agent job history
   - Moderate priority

7. **Cross-Thread Context** (Priority 7, Weight 0.4)
   - Other threads mentioning same RFP
   - Lowest priority

## Usage Examples

### Basic Usage (Query-Aware)

```python
context = build_comprehensive_context(
    user_profile=user_profile,
    user_query="What RFPs are due this week?",
    channel_id=channel_id,
    thread_ts=thread_ts,
    max_total_chars=50000,
)
```

The system will:

1. Extract keywords: ["rfp", "due", "week"]
2. Use those keywords to search memories
3. Boost RFP-related context weight
4. Retrieve most relevant memories

### Advanced Usage (Structured Context)

```python
from .agent_context_enhancer import build_structured_context

context = build_structured_context(
    user_profile=user_profile,
    user_query=user_query,
    rfp_id=rfp_id,
    prioritize_recent=True,
    max_total_chars=50000,
)
```

## Integration Points

### Slack Agent (`slack_agent.py`)

```python
comprehensive_ctx = build_comprehensive_context(
    user_profile=user_profile,
    user_query=q,  # Pass user query
    channel_id=channel_id,
    thread_ts=thread_ts,
    max_total_chars=50000,
)
```

### Slack Operator Agent (`slack_operator_agent.py`)

```python
comprehensive_ctx = build_comprehensive_context(
    user_profile=actor_ctx.user_profile,
    user_query=q,  # Pass user query
    rfp_id=rfp_id,
    channel_id=channel_id,
    thread_ts=thread_ts,
    max_total_chars=50000,
)
```

## Best Practices

1. **Always pass user_query**: Even if it's just the current question, it helps retrieve relevant context
2. **Use appropriate limits**: Balance context richness with token limits
3. **Monitor context quality**: Check what context is being retrieved for common queries
4. **Tune keyword extraction**: Adjust keyword extraction parameters if needed
5. **Use structured context**: For complex scenarios, use `build_structured_context()`

## Future Enhancements

Potential future improvements:

1. **Context compression**: Summarize old context using LLM
2. **Relevance scoring**: Use embeddings for better relevance scoring
3. **Context caching**: Cache common context queries
4. **Dynamic context selection**: More sophisticated context selection based on query type
5. **Context validation**: Verify context accuracy and freshness
6. **Context analytics**: Track which context is most useful for responses

## Files Modified

- `backend/app/services/agent_context_builder.py`: Added query-aware retrieval, improved truncation
- `backend/app/services/slack_agent.py`: Pass user_query to context builder
- `backend/app/services/slack_operator_agent.py`: Pass user_query to context builder
- `backend/app/services/agent_context_enhancer.py`: New module with advanced context building
- `backend/app/services/agent_context_guidance.py`: New module with best practices documentation
