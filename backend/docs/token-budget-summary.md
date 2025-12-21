# Token Budget System - Implementation Summary

## ✅ Completed

### 1. Core Infrastructure

- **tiktoken dependency** added to requirements.txt
- **Token Counter Service** (`token_counter.py`)

  - Token counting with model detection (gpt-5.2 → o200k_base, fallback to cl100k_base)
  - Cost calculation ($1.75/1M input, $14.00/1M output for gpt-5.2)
  - **Time-to-tokens conversion**: 4 hours = $10 budget, scaled proportionally
  - **Default**: 15 minutes = ~44.6K tokens (conservative, using output pricing)

- **Token Budget Tracker** (`token_budget_tracker.py`)
  - Tracks usage vs budget
  - Supports checkpointing (to_dict/from_dict)
  - Budget status messages for agent awareness
  - Initialization from time/cost budgets

### 2. Integration Points

- **LongRunningOrchestrator** (`agent_long_running.py`)

  - Accepts `token_budget_tracker` parameter
  - Passes tracker to step execution context
  - Includes budget status in step context
  - Checkpoints tracker state
  - Restores tracker from checkpoint on resume

- **Agent Universal Executor** (`agent_universal_executor.py`)

  - Initializes token budget tracker (default: 15 minutes)
  - Restores from checkpoint if resuming
  - Passes tracker to orchestrator

- **Helper Function** (`long_running_job_helpers.py`)

  - `initialize_token_budget_for_job()` - centralized initialization
  - Restores from checkpoint or creates new tracker
  - Used by all long-running jobs

- **Job Runner** (`agent_job_runner.py`)
  - Initializes token budget for `ai_agent_analyze_rfps` jobs

## Budget Calculation

### Formula

- **4 hours = $10 budget** (conversion scale)
- **Default: 15 minutes**
- Calculation: `cost = (minutes / 240) * $10`
- Token budget: Convert cost to tokens using output pricing (conservative)

### Examples

- **15 minutes**: ~44.6K tokens ($0.625 cost budget)
- **1 hour**: ~178.5K tokens ($2.50 cost budget)
- **4 hours**: ~714K tokens ($10 cost budget)

## 🔄 Remaining Work

### 1. LLM Call Wrapper Integration

**Status**: Pending
**Location**: `backend/app/ai/client.py`

Need to:

- Extract token usage from OpenAI API responses
- Record usage to tracker (if provided)
- Handle both Chat Completions and Responses API formats

**Chat Completions API**:

```python
completion.usage.prompt_tokens
completion.usage.completion_tokens
```

**Responses API** (GPT-5):

- Need to verify actual response structure
- Fallback: Manual counting with tiktoken (already implemented)

### 2. Agent Prompt Integration

**Status**: Pending
**Location**: `backend/app/services/agent_context_builder.py` or prompt construction

Need to:

- Add budget status to agent context/prompts
- Include instructions about continuing until budget exhausted
- Format using `tracker.get_budget_status_message()`

### 3. Logging and Metrics

**Status**: Pending

Need to:

- Log token usage per LLM call
- Log budget exhaustion events
- Include usage in job completion results
- Track efficiency metrics

## Usage

### For Long-Running Jobs

All long-running jobs automatically get a **15-minute default budget** unless specified:

```python
# Default: 15 minutes (~44.6K tokens)
payload = {"request": "Find RFPs matching criteria"}

# Custom time budget
payload = {"request": "...", "timeBudgetMinutes": 60}  # 1 hour

# Custom cost budget (overrides time budget)
payload = {"request": "...", "costBudgetUsd": 5.0}  # $5 budget
```

### Budget Scale

- 4 hours = $10 budget
- Proportional scaling for any time duration
- Conservative token calculation (uses output pricing)

## Next Steps

1. **Test token usage extraction** from OpenAI responses
2. **Integrate into LLM wrappers** (call_text, call_json)
3. **Add budget awareness to prompts**
4. **Add logging/metrics**
5. **Test end-to-end** with sample jobs
