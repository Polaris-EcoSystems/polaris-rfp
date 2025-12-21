# Token Budget Implementation Plan

## Overview

Implement a token budget system for long-running agent jobs that:

1. Tracks token usage across LLM calls
2. Converts time/cost budgets to token budgets
3. Provides budget awareness to agents
4. Continues working until budget is exhausted (refining, validating, generating insights)
5. Supports checkpointing and resuming with budget state

## Implementation Components

### 1. ✅ Token Counter Service (`token_counter.py`)

- Counts tokens using tiktoken
- Model detection and tokenizer selection
- Cost calculation based on OpenAI pricing
- Time-to-tokens conversion heuristics
- Cost-to-tokens conversion (conservative, using output pricing)

### 2. ✅ Token Budget Tracker (`token_budget_tracker.py`)

- Tracks usage vs budget
- Supports checkpointing (to_dict/from_dict)
- Provides budget status messages for agent awareness
- Calculates remaining budget

### 3. 🔄 LLM Call Wrapper Integration

**Status: Need to extract token usage from OpenAI responses**

- Modify `call_text()` and `call_json()` to:
  - Accept optional `token_budget_tracker` parameter
  - Extract token usage from OpenAI response (usage.prompt_tokens, usage.completion_tokens)
  - Record usage to tracker
  - Check budget before expensive calls

**Challenge**: OpenAI Responses API may return usage differently than Chat Completions API. Need to handle both.

### 4. 🔄 LongRunningOrchestrator Integration

**Status: Need to add token_budget_tracker parameter**

- Add `token_budget_tracker: TokenBudgetTracker | None = None` to `__init__`
- Pass tracker to step execution context
- Include budget status in step context
- Checkpoint tracker state along with other checkpoint data

### 5. 🔄 Agent Universal Executor Integration

**Status: Need to initialize tracker from payload**

- Extract time/cost budget from payload:
  ```python
  time_budget_minutes = payload.get("timeBudgetMinutes")
  cost_budget_usd = payload.get("costBudgetUsd", 10.0)  # Default $10
  ```
- Initialize `TokenBudgetTracker` from budget
- Restore tracker from checkpoint if resuming
- Pass tracker to orchestrator
- Include budget status in agent context/prompts

### 6. 🔄 Agent Context/Prompt Integration

**Status: Need to add budget status to prompts**

- Add budget status message to agent system prompts or context
- Format: Use `TokenBudgetTracker.get_budget_status_message()`
- Include in context builder or prompt construction

### 7. 🔄 Logging and Metrics

**Status: Need to add logging**

- Log token usage per LLM call
- Log budget exhaustion events
- Track efficiency metrics (tokens per result quality)
- Include in job completion results

## Token Usage Extraction Strategy

OpenAI API responses have different structures:

### Chat Completions API:

```python
completion.usage.prompt_tokens
completion.usage.completion_tokens
completion.usage.total_tokens
```

### Responses API (GPT-5):

May return usage in response metadata. Need to check actual response structure.

**Fallback**: If usage not available, count tokens manually using tiktoken.

## Budget Awareness in Agent Prompts

Add to system prompt or context:

```
TOKEN_BUDGET_STATUS:
{budget_status_message}

IMPORTANT:
- Continue working on the problem until the budget is exhausted
- If you have an answer but budget remains:
  1. Validate and verify your solution
  2. Generate additional insights from other context
  3. Explore alternative approaches
  4. Acknowledge any uncertainty and explain why
- When budget is critical (≤10% remaining), prioritize providing final answer
- If budget exhausted, provide best answer available
```

## Checkpointing Strategy

1. Store token budget tracker state in checkpoint metadata:

   ```python
   checkpoint_data["token_budget"] = tracker.to_dict()
   ```

2. Restore on resume:

   ```python
   if "token_budget" in checkpoint_data:
       tracker = TokenBudgetTracker.from_dict(checkpoint_data["token_budget"])
   ```

3. Include in orchestrator checkpoint method

## Testing Strategy

1. Unit tests for token counting
2. Unit tests for budget tracker
3. Integration tests for LLM wrapper tracking
4. End-to-end test for full job execution with budget
5. Test checkpoint/resume with budget state

## Rollout Plan

1. ✅ Add tiktoken dependency
2. ✅ Implement token counter
3. ✅ Implement budget tracker
4. 🔄 Integrate into LLM wrappers (need to handle OpenAI response format)
5. 🔄 Integrate into orchestrator
6. 🔄 Integrate into universal executor
7. 🔄 Add budget awareness to prompts
8. 🔄 Add logging/metrics
9. Test with sample jobs
10. Deploy and monitor

## Open Questions / Next Steps

1. **Need to verify OpenAI Responses API usage format** - May need to inspect actual response structure
2. **Fallback token counting** - If usage not in response, count manually (already implemented in token_counter)
3. **Budget exhaustion behavior** - Should we raise exception or return gracefully? (Planning to return gracefully with best answer)
4. **Default budget** - Should all jobs get default $10 budget, or only if specified? (Current plan: only if specified in payload)
