# Reasoning Effort Configuration

This document describes how reasoning effort is configured for various AI agent/slackbot functionality.

## Overview

Reasoning effort controls how much the GPT-5 model "thinks" before answering. Higher reasoning effort improves quality for complex tasks but increases latency and cost.

## Current Configuration

### Settings Defaults

- `openai_reasoning_effort`: `"none"` (general default)
- `openai_reasoning_effort_json`: `"low"` (for JSON extraction tasks)
- `openai_reasoning_effort_text`: `"none"` (for text generation tasks)

### Task Type Classifications

#### Tools (Agent Tool-Using Tasks)

**Purpose**: `slack_agent`  
**Kind**: `tools`

**Enhanced Logic** (complexity-aware escalation):

- **Base effort**: `"medium"` (upgraded from `"low"` for better quality on agent tasks)
- **Simple operations** (read-only, basic queries):
  - Steps 1-2: `"medium"`
  - Steps 3-5: `"medium"`
  - Steps 6+: `"high"`
- **Medium complexity operations** (workflow ops, multi-tool queries):
  - Steps 1: `"medium"`
  - Steps 2-4: `"medium"`
  - Steps 5+: `"high"`
- **Complex operations** (state management, code changes, infrastructure):
  - Steps 1: `"medium"` (starts higher)
  - Steps 2-3: `"medium"`
  - Steps 4+: `"high"` (escalates faster)

**Complexity Detection**:
The system automatically detects complex operations based on tool names:

- **High complexity**: `opportunity_patch`, `journal_append`, `event_append`, `create_change_proposal`, `self_modify_*`, `ecs_*`, `github_*`, `propose_action`
- **Medium complexity**: `schedule_job`, `slack_post_summary`, `slack_ask_clarifying_question`

**Used by**:

- `slack_agent.py` - Read-only Q&A agent
- `slack_operator_agent.py` - Stateful operator agent with write capabilities

#### JSON Tasks

**Kind**: `json`

**Current Logic**:

- Base: `"low"` (from `openai_reasoning_effort_json`)
- On parse/validation retry (attempt >= 2): Escalates to `"medium"` → `"high"`

**Used by**:

- RFP analysis tasks
- Buyer enrichment
- Section titles

#### Text Tasks

**Kind**: `text`

**Current Logic**:

- Base: `"none"` (from `openai_reasoning_effort_text`)
- On parse/validation retry (attempt >= 2): Escalates to `"medium"` → `"high"`

**Used by**:

- Proposal section generation
- Text editing
- Content generation

## Task Complexity Classification

### High Complexity Tasks (Should use "high" or "medium" reasoning)

1. **State Management Operations**

   - `opportunity_patch` - Modifies durable OpportunityState
   - `journal_append` - Creates decision narratives
   - `event_append` - Logs explainability events

2. **Code/Infrastructure Changes**

   - `create_change_proposal` - Creates code change proposals
   - `self_modify_*` actions - Self-modifying pipeline operations
   - `ecs_*` actions - ECS service operations
   - `github_*` actions - GitHub operations

3. **Complex Multi-Step Operations**

   - Operations requiring 4+ tool calls
   - Operations involving multiple data sources
   - Operations with cross-system dependencies

4. **High-Risk Actions**
   - Actions classified as "high" or "destructive" risk
   - Actions requiring confirmation
   - Infrastructure modifications

### Medium Complexity Tasks (Should use "medium" reasoning)

1. **Workflow Operations**

   - `seed_tasks_for_rfp`
   - `assign_task`
   - `complete_task`
   - `update_rfp_review`

2. **Multi-Tool Queries**
   - Queries requiring 2-3 tool calls
   - Cross-referencing multiple data sources

### Low Complexity Tasks (Can use "low" reasoning)

1. **Simple Read Operations**

   - Single tool calls
   - Simple lookups
   - Basic data retrieval

2. **Personal Preferences**
   - `update_user_profile` (low risk)

## Enhancement Strategy

The system has been enhanced to:

1. **Start with higher base reasoning** for tools (medium instead of low) - agent tasks are inherently more complex
2. **Escalate faster** for complex operations (high at step 4 instead of step 6)
3. **Detect complex tool patterns** automatically based on tool names and increase reasoning accordingly
4. **Track recent tool calls** to provide context-aware reasoning effort
5. **Use complexity-based reasoning** - different escalation paths for simple vs complex operations

## Implementation Details

### Complexity Detection

The `tuning_for()` function now accepts a `recent_tools` parameter that tracks the last 5 tool calls. This allows the system to:

- Detect when complex operations are being performed
- Adjust reasoning effort dynamically based on operation complexity
- Escalate reasoning faster for operations that require more careful consideration

### Tool Classification

Tools are classified into complexity levels:

**High Complexity** (escalates to high at step 4):

- State management: `opportunity_patch`, `journal_append`, `event_append`
- Code/infrastructure: `create_change_proposal`, `self_modify_*`, `ecs_*`, `github_*`
- High-risk actions: `propose_action`

**Medium Complexity** (escalates to high at step 5):

- Workflow operations: `schedule_job`
- Communication: `slack_post_summary`, `slack_ask_clarifying_question`

**Low Complexity** (standard escalation):

- Read operations and simple queries

## Configuration

Reasoning effort can be adjusted via environment variables:

- `OPENAI_REASONING_EFFORT` - General default
- `OPENAI_REASONING_EFFORT_JSON` - For JSON tasks
- `OPENAI_REASONING_EFFORT_TEXT` - For text tasks

Valid values: `"none"`, `"low"`, `"medium"`, `"high"`
