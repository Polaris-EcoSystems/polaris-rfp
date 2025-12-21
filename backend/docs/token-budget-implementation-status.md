# Token Budget Implementation Status

## ✅ Completed

1. **tiktoken dependency** - Added to requirements.txt
2. **Token Counter Service** (`backend/app/services/token_counter.py`)

   - Token counting with tiktoken
   - Model detection and tokenizer selection (supports gpt-5.2 via o200k_base, fallback to cl100k_base)
   - Cost calculation ($1.75/1M input, $14.00/1M output for gpt-5.2)
   - Time-to-tokens conversion (heuristic: 10k tokens/minute)
   - Cost-to-tokens conversion (conservative, using output pricing)
   - $10 budget = ~714K tokens (conservative estimate)

3. **Token Budget Tracker** (`backend/app/services/token_budget_tracker.py`)
   - Tracks usage vs budget
   - Supports checkpointing (to_dict/from_dict)
   - Budget status messages for agent awareness
   - Remaining budget calculations
   - Initialization from time/cost budgets

## 🔄 In Progress / Next Steps

### Step 1: Extract Token Usage from OpenAI Responses

**Location**: `backend/app/ai/client.py`

**Changes needed**:

- Extract `usage` object from Chat Completions API responses
- Check if Responses API returns usage (may need to test)
- Add fallback to manual counting if usage not available

**Code pattern**:

```python
# In call_text() and call_json()
# After successful API call:
input_tokens = getattr(resp, 'usage', {}).get('prompt_tokens') or count_tokens(messages, model)
output_tokens = getattr(resp, 'usage', {}).get('completion_tokens') or count_tokens(output, model)

# If token_budget_tracker provided:
if token_budget_tracker:
    tracker.record_llm_call(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
```

### Step 2: Integrate Token Budget into LongRunningOrchestrator

**Location**: `backend/app/services/agent_long_running.py`

**Changes needed**:

1. Add `token_budget_tracker` parameter to `__init__`
2. Pass tracker to step execution context
3. Include budget status in checkpoint data
4. Restore tracker from checkpoint on resume

### Step 3: Integrate into Agent Universal Executor

**Location**: `backend/app/services/agent_universal_executor.py`

**Changes needed**:

1. Extract budget from payload:
   ```python
   time_budget_minutes = payload.get("timeBudgetMinutes")
   cost_budget_usd = payload.get("costBudgetUsd", 10.0)  # Default $10
   ```
2. Initialize tracker (or restore from checkpoint)
3. Pass tracker to orchestrator

### Step 4: Add Budget Awareness to Agent Prompts

**Location**: `backend/app/services/agent_context_builder.py` or prompt construction

**Changes needed**:

- Add budget status to agent context/prompts
- Format using `tracker.get_budget_status_message()`
- Include instructions about continuing until budget exhausted

### Step 5: Add Logging and Metrics

**Changes needed**:

- Log token usage per call
- Log budget exhaustion
- Include in job results
- Track efficiency metrics

## Implementation Notes

### Token Usage Extraction Strategy

**Chat Completions API**:

```python
completion.usage.prompt_tokens
completion.usage.completion_tokens
completion.usage.total_tokens
```

**Responses API** (GPT-5):

- May have different structure
- Check: `resp.usage` or similar
- Fallback: Manual counting with tiktoken

### Budget Defaults

- Default: $10 cost budget (~714K tokens for gpt-5.2)
- Can be overridden via payload: `costBudgetUsd` or `timeBudgetMinutes`
- Time budget converted to tokens using heuristic

### Checkpointing

- Store tracker state in checkpoint metadata
- Restore on resume from checkpoint
- Preserve budget across job runner cycles

## Testing Checklist

- [ ] Token counting accuracy
- [ ] Budget tracker state management
- [ ] Checkpoint/resume with budget
- [ ] Budget exhaustion handling
- [ ] Agent behavior with budget awareness
- [ ] Cost calculations
- [ ] Logging/metrics

## Questions / Decisions Needed

1. **OpenAI Responses API usage format** - Need to verify actual response structure
2. **Default budget** - Should all long-running jobs get default $10 budget, or only if specified?
3. **Budget exhaustion behavior** - Current plan: return gracefully with best answer
4. **Budget in agent prompts** - Where exactly to inject? System prompt vs context?
