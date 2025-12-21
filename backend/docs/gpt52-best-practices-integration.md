# GPT-5.2 Best Practices Integration

## Overview

This document outlines the GPT-5.2 best practices that have been integrated into the Slack operator agent and AI client infrastructure.

## Key Improvements Implemented

### 1. ✅ Responses API as Primary Path

**Status**: ✅ Implemented

**Changes**:

- Responses API is now the primary path for GPT-5.2 models
- Only falls back to Chat Completions if Responses API is not available (legacy SDK)
- GPT-5.2 works best with Responses API which supports passing chain of thought (CoT) between turns

**Code Locations**:

- `slack_operator_agent.py:1921-1927` - Checks for Responses API support and GPT-5.2 family
- `slack_operator_agent.py:2357-2375` - Uses Responses API with `previous_response_id` for CoT passing
- `slack_operator_agent.py:2580-2596` - Second Responses API call with updated tuning

**Benefits**:

- Improved intelligence through CoT passing
- Fewer generated reasoning tokens
- Higher cache hit rates
- Lower latency

### 2. ✅ XHigh Reasoning Effort Support

**Status**: ✅ Implemented

**Changes**:

- Added `xhigh` reasoning effort level support in `_escalate_effort` function
- Escalation path: `low` → `medium` → `high` → `xhigh`
- Complex operations can now escalate to `xhigh` for very persistent problems

**Code Locations**:

- `ai/tuning.py:67-95` - Enhanced `_escalate_effort` to support xhigh
- `ai/tuning.py:230-280` - Tool complexity escalation can reach xhigh for:
  - Complex tools with 8+ steps or 6+ steps with high context complexity
  - Medium tools with 10+ steps or 7+ steps with high context complexity
  - Simple tools with 12+ steps or 8+ steps with high context complexity
  - Very complex context (>1.5) with high effort
  - Long-running operations with high effort and 5+ steps

**Usage**:

- Automatically escalates to `xhigh` for very complex, persistent operations
- Provides maximum reasoning power when needed

### 3. ✅ GPT-5.2-Pro Fallback

**Status**: ✅ Implemented

**Changes**:

- Added `gpt-5.2-pro` as a fallback model in `_models_to_try`
- Automatically falls back to `gpt-5.2-pro` when:
  - Model access errors occur with GPT-5.2 models
  - Complex operations need more compute
- Uses `xhigh` reasoning effort when falling back to pro model

**Code Locations**:

- `ai/client.py:128-150` - `_models_to_try` includes `gpt-5.2-pro` for GPT-5.2 family
- `slack_operator_agent.py:2382-2392` - Fallback to `gpt-5.2-pro` on model access errors
- `slack_operator_agent.py:2599-2610` - Fallback to `gpt-5.2-pro` on second API call failures

**Benefits**:

- Automatic escalation to more powerful model when needed
- Better handling of complex, persistent problems
- Uses `xhigh` reasoning for maximum problem-solving capability

### 4. ✅ Enhanced Tuning Logic

**Status**: ✅ Implemented

**Changes**:

- Context complexity awareness for reasoning effort selection
- Long-running operation detection
- Step-based escalation that can reach `xhigh`
- Better complexity estimation based on:
  - Tool complexity (complex/medium/simple tools)
  - Context complexity (RFP state, related RFPs, cross-thread)
  - Step count
  - Long-running job detection

**Code Locations**:

- `ai/tuning.py:178-280` - Enhanced tool tuning logic
- `ai/tuning.py:84-131` - Context complexity estimation
- `slack_operator_agent.py:2311-2321` - Passes context complexity to tuning

### 5. ✅ GPT-5.2 Best Practices in System Prompt

**Status**: ✅ Implemented

**Changes**:

- Added GPT-5.2 best practices section to system prompt
- Guidance on:
  - Using Responses API with CoT passing
  - Preambles (explaining tool calls before making them)
  - Reasoning effort levels
  - Verbosity levels
  - When xhigh reasoning is used

**Code Locations**:

- `slack_operator_agent.py:1732-1740` - GPT-5.2 best practices section

### 6. ✅ Improved Error Handling

**Status**: ✅ Implemented

**Changes**:

- Better fallback to `gpt-5.2-pro` on model access errors
- Graceful degradation with adjusted reasoning effort
- Automatic model escalation for complex operations

**Code Locations**:

- `slack_operator_agent.py:2367-2392` - Enhanced error handling with pro fallback
- `slack_operator_agent.py:2597-2610` - Second call error handling with pro fallback

---

## GPT-5.2 Features in Use

### Reasoning Effort Levels

- **none**: Default for simple queries (low latency)
- **low**: Simple operations
- **medium**: Standard operations (default for tools)
- **high**: Complex multi-step tasks
- **xhigh**: Very complex persistent problems (new!)

### Verbosity Levels

- **low**: Concise answers
- **medium**: Balanced responses (default)
- **high**: Thorough explanations

### Model Selection

- Primary: `gpt-5.2` (or configured model)
- Fallback: `gpt-5.2-pro` (for complex operations or model access errors)

### API Selection

- Primary: Responses API (for GPT-5.2 family)
- Fallback: Chat Completions (only if Responses API unavailable)

---

## Migration Notes

### From Chat Completions to Responses API

- ✅ Already using Responses API as primary path
- ✅ Properly using `previous_response_id` for CoT passing
- ✅ Only falls back to Chat Completions for legacy SDKs

### Reasoning Effort Migration

- ✅ Supports all GPT-5.2 reasoning levels including `xhigh`
- ✅ Automatic escalation based on complexity
- ✅ Proper handling of `none` effort (allows temperature)

### Model Migration

- ✅ `gpt-5.2` as primary
- ✅ `gpt-5.2-pro` as intelligent fallback
- ✅ Automatic escalation for complex operations

---

## Best Practices Applied

1. **Use Responses API for GPT-5.2**: ✅ Primary path
2. **Pass CoT between turns**: ✅ Using `previous_response_id`
3. **Use appropriate reasoning effort**: ✅ Dynamic based on complexity
4. **Escalate to xhigh for complex problems**: ✅ Automatic escalation
5. **Use gpt-5.2-pro when needed**: ✅ Automatic fallback
6. **Explain tool calls (preambles)**: ✅ Guidance in system prompt
7. **Control verbosity appropriately**: ✅ Dynamic based on task type

---

## Future Enhancements

1. **Explicit Preambles**: Could add system instruction to always explain tool calls before making them
2. **Custom Tools**: Could leverage freeform custom tools for more flexible tool calling
3. **CFG Constraints**: Could add context-free grammar constraints for specific tool outputs
4. **Allowed Tools**: Already using `tool_choice` with `allowed_tools` - could enhance further
5. **Compaction**: Could leverage GPT-5.2's compaction feature for long-running tasks

---

## Testing Recommendations

1. Verify Responses API is being used (check logs for `responses.create` calls)
2. Verify `xhigh` reasoning is used for very complex operations (8+ steps, high complexity)
3. Verify `gpt-5.2-pro` fallback works on model access errors
4. Verify CoT passing works correctly (check `previous_response_id` usage)
5. Monitor reasoning effort escalation patterns
