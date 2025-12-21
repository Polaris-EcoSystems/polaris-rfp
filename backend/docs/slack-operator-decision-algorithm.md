# Slack Operator Agent Decision Algorithm

This document describes the algorithm used by the Slack operator agent (`run_slack_operator_for_mention`) to determine how to respond to user mentions.

## High-Level Flow

```
User mentions @Polaris RFP
  ↓
1. Validate inputs (question, channel_id, thread_ts)
  ↓
2. Resolve actor context (Slack user → platform user identity)
  ↓
3. Check for thread utilities ("link rfp_...", "where")
  ↓
4. Extract/derive RFP scope (from message or thread binding)
  ↓
5. Determine if RFP scope is required
  ↓
6. Decision Tree:
   ├─ No RFP ID + requires_rfp = False → Delegate to slack_agent (conversational)
   ├─ No RFP ID + requires_rfp = None → Delegate to slack_agent (unclear)
   ├─ No RFP ID + requires_rfp = True → Ask user for RFP ID
   └─ Has RFP ID (or doesn't need it) → Continue to operator agent
  ↓
7. Build comprehensive context
  ↓
8. Generate metaprompt (analyze request)
  ↓
9. Build system prompt with context
  ↓
10. Execute agent loop (tool calling)
```

## Detailed Steps

### Step 1: Input Validation

- Normalize question text (whitespace, max 5000 chars)
- Validate required params: `question`, `channel_id`, `thread_ts`
- If missing → return early with error

### Step 2: Actor Context Resolution

- Resolve Slack user ID → platform user identity
- Uses `resolve_actor_context()` to get:
  - Email
  - Display name
  - User profile (Cognito user sub)
- Best-effort: failures are non-fatal

### Step 3: Thread Utilities (Early Returns)

Checks for special commands that return immediately:

**Thread Binding:**

- Pattern: `"link rfp_..."` or `"bind rfp_..."`
- Action: Binds thread to RFP, posts confirmation, returns

**Thread Query:**

- Pattern: `"where"` or `"where?"`
- Action: Shows current thread binding, returns

### Step 4: RFP Scope Resolution

Two-step process:

1. **Extract from message:**

   - Uses regex to find `rfp_...` pattern in question text
   - Returns first match if found

2. **Fall back to thread binding:**
   - If no RFP ID in message, checks thread binding
   - Uses `get_thread_binding()` to retrieve stored binding

Result: `rfp_id` may be `None` (global operations allowed)

### Step 5: RFP Scope Requirement Detection

Calls `_operations_requiring_rfp_scope(question)` which analyzes the question text using **keyword/phrase matching** in order of priority:

### Evaluation Order (Priority-Based):

**1. First: Check for explicit "False" indicators** (returns early)

- "new rfp", "brand new", "it's new"
- "upload the file", "upload this", "can you upload"
- "search for", "find a new"
- Bot capability questions ("what can you", "what tools")
- If matched → Returns `False` immediately

**2. Second: Check for job-related operations** (special case)

- "schedule job", "agent job", "job list", "job status", "query jobs", "runner"
- **Exception:** If job-related phrase found AND question contains RFP ID (`rfp_...`)
  - Returns `True` (RFP-scoped job operation)
- Otherwise → Returns `False` (global job operation)

**3. Third: Check for explicit "True" indicators** (RFP-scoped write operation keywords)

- **Highly specific phrases that ALWAYS return `True` (very conservative):**
  - "journal entry" / "add to journal" / "append journal" → `journal_append` requires RFP
  - "opportunity state" / "update opportunity" / "patch opportunity" → `opportunity_patch` requires RFP
  - "update rfp" / "update the rfp" → Explicit RFP update operations
- **Key principle:** Only matches phrases that unambiguously indicate write operations on OpportunityState or Journal (which require `opportunity_load` first)
- **Removed from True indicators:**
  - ❌ "opportunity" (too broad - could be read-only queries)
  - ❌ "journal" (too broad - could be asking "what's in the journal?")
  - ❌ "state" (too broad - could mean any state)
  - ❌ "patch" (too broad - could be code patches)
  - ❌ "rfp review" (read-only, doesn't require RFP scope)
  - ❌ "seed tasks" / "assign task" / "complete task" (too ambiguous, could be global operations)
- If matched → Returns `True` immediately

**4. Fourth: Check for RFP-related terms** (ambiguous case)

- If question contains: "rfp", "proposal", "opportunity", or "bid"
- **Sub-check:** Is it a general query?
  - If contains: "what is", "tell me about", "show me", "list", "search"
  - → Returns `False` (general query, no binding needed)
- Otherwise → Returns `None` (unclear, might need RFP scope)

**5. Default: No matches found**

- Returns `False` (treat as general question, no RFP scope required)

### Key Points:

- **`True` is returned ONLY when:**

  1. Question contains explicit RFP-scoped operation keywords (step 3), OR
  2. Question mentions job operations AND contains an RFP ID (step 2 exception)

- **The function is conservative:** It only returns `True` when there are clear indicators that an RFP-scoped tool will be needed (`opportunity_load`, `opportunity_patch`, `journal_append`, `event_append`)

- **Default is `False`:** If no clear indicators are found, it assumes a global operation (read-only queries, job scheduling, etc.)

### Step 6: Decision Tree

#### Branch A: No RFP ID + requires_rfp = False

- **Action:** Delegate to `run_slack_agent_question()` (conversational agent)
- **Why:** Clearly a global operation or general query
- **Result:** Conversational agent handles it, posts response, returns

#### Branch B: No RFP ID + requires_rfp = None

- **Action:** Try delegating to conversational agent first
- **Why:** Unclear intent, let conversational agent handle if possible
- **Result:** If delegation succeeds, return. Otherwise fall through.

#### Branch C: No RFP ID + requires_rfp = True

- **Action:** Ask user for RFP ID
- **Message:** "Which RFP is this about? Include an id like `rfp_...` or bind this thread with: `@polaris link rfp_...`"
- **Result:** Return early (don't proceed with agent)

#### Branch D: Has RFP ID (or doesn't need it)

- **Action:** Continue to operator agent execution
- **Note:** Can proceed with `rfp_id=None` for global operations

### Step 7: State Initialization

If `rfp_id` exists:

- Call `ensure_state_exists(rfp_id)` to initialize OpportunityState if needed

### Step 8: Context Building

Builds comprehensive context using `build_comprehensive_context()`:

**Includes:**

- User context (profile, display name, email)
- Thread context (conversation history)
- RFP state context (if `rfp_id` present):
  - OpportunityState
  - Recent journal entries
  - Recent event log
- Related RFPs context
- Cross-thread context (other threads for same RFP)
- Memory retrieval (query-aware):
  - Episodic memories
  - Semantic memories
  - Procedural memories
- External context (if query-aware retrieval suggests it)

**Team awareness context:**

- Added if query mentions: "team", "member", "biography", "capability", "skill", etc.
- Includes current user context and team member summaries

### Step 9: Metaprompt Generation

Calls `_generate_metaprompt()` which uses AI to analyze the request:

**Analyzes:**

1. User's true intent/goal
2. Type of operation (query, action, multi-step workflow)
3. Relevant tools/skills needed
4. Complexity (simple vs. multi-turn)
5. Missing information
6. Entities to consider (team members, RFPs, etc.)

**Output:** 2-4 sentence analysis guide included in system prompt

### Step 10: Procedural Memory Retrieval

If actor user_sub exists:

- Retrieves top 5 relevant procedural memories
- Filters by query text for relevance
- Shows successful tool patterns from past similar requests
- Formats as guidance: "Past Successful Tool Patterns"

### Step 11: System Prompt Construction

Assembles comprehensive system prompt with:

**Core identity:**

- "You are Polaris Operator"
- Stateless: must reconstruct context via tools

**Capabilities:**

- Team awareness, RFP/proposal/opportunity awareness
- Read/write platform data, schedule jobs, execute workflows

**Metaprompt analysis:**

- AI-generated analysis of the request

**Tool guidance:**

- Relevant tool categories
- Past successful tool patterns
- Skills system guidance (if relevant)

**Documentation:**

- Slack permissions
- Agent jobs system
- Available job types
- Tool categories overview

**Critical rules:**

- Don't trust Slack chat history (use platform tools)
- RFP scope requirements
- When to use different tools
- State-before-talk protocol
- Never invent IDs/dates

**Runtime context:**

- channel, thread_ts, slack_user_id
- rfp_id_scope (or "none - global operations allowed")
- correlation_id

**Comprehensive context:**

- All context layers (user, thread, RFP state, memory, etc.)
- Team member awareness (if relevant)

### Step 12: Agent Execution Loop

**Protocol Enforcement (`_inject_and_enforce`):**

Before each tool call:

1. **Load-first protocol (RFP-scoped operations):**

   - If `rfp_id` exists AND tool requires RFP scope AND `opportunity_load` hasn't been called
   - Force `opportunity_load` first (return error if other tool attempted)

2. **Write-it-down protocol (before posting):**

   - If `rfp_id` exists AND tool is `slack_post_summary` or `slack_ask_clarifying_question`
   - Require that `opportunity_patch` or `journal_append` was called first
   - Ensures durable artifacts are written before communicating

3. **Correlation ID injection:**
   - Automatically injects `correlation_id` into relevant tools for traceability

**Tool Execution:**

- Iterates up to `max_steps` (default 8)
- Uses GPT-5.2 Responses API (preferred) or Chat Completions (fallback)
- Model makes tool calls → tools executed → results fed back → repeat

**Tool Categories:**

- **Read tools:** No protocol enforcement (read-only)
- **Global tools:** `schedule_job`, `agent_job_*`, `job_plan`, etc. (no RFP required)
- **RFP-scoped tools:** `opportunity_load`, `opportunity_patch`, `journal_append`, `event_append` (require RFP scope)

**Tool Result Handling:**

- Success: Update protocol flags (`did_load`, `did_patch`, `did_journal`)
- Failure: Classify error, potentially store as procedural memory for learning
- Retry logic: Uses `retry_with_classification()` for transient failures

**Termination Conditions:**

- Max steps reached
- Model returns text (no tool calls)
- `slack_post_summary` or `slack_ask_clarifying_question` called (did_post = True)
- `propose_action` called (handled specially with risk assessment)

### Step 13: Final Response

**If agent posted (did_post = True):**

- Return `SlackOperatorResult(did_post=True, text=..., meta={...})`

**If agent didn't post but has text:**

- Post text to thread (with or without RFP scope)
- Return result

**Episodic Memory Storage:**

- Best-effort storage of interaction for future context
- Non-blocking (failures don't affect response)

## Key Design Decisions

### 1. Two-Agent Architecture

- **Operator agent:** State-aware, writes durable artifacts, protocol-enforced
- **Conversational agent:** General-purpose, read-only, flexible

### 2. Scope Detection Before Execution

- Determines RFP requirement early
- Avoids unnecessary context building
- Provides clear user guidance when RFP needed

### 3. Protocol Enforcement

- **Load-first:** Ensures state is reconstructed before operations
- **Write-it-down:** Ensures durability before communication
- Prevents inconsistent state

### 4. Comprehensive Context

- Query-aware memory retrieval
- Multi-layer context (user, thread, RFP, related, cross-thread)
- Team awareness when relevant
- Balances completeness with token limits

### 5. Metaprompt Analysis

- Uses AI to analyze request before execution
- Guides tool selection and approach
- Improves accuracy and reduces unnecessary steps

### 6. Procedural Memory Learning

- Stores successful tool patterns
- Retrieves relevant patterns for similar requests
- Learns from failures to avoid repeating mistakes

### 7. Resilience and Error Handling

- Retry logic with classification
- Error categorization (retryable vs. permanent)
- Graceful degradation on failures
- Non-blocking memory operations

## Example Flows

### Example 1: "Update the status to proposal submitted for rfp_abc123"

1. Extract `rfp_abc123` → `rfp_id = "rfp_abc123"`
2. `requires_rfp_scope()` → Returns `None` (but we have RFP ID, so proceed)
3. Build context (includes RFP state)
4. Agent executes:
   - `opportunity_load` (protocol enforced)
   - `opportunity_patch` (updates status)
   - `journal_append` (records decision)
   - `slack_post_summary` (posts confirmation)

### Example 2: "What can you do?"

1. No RFP ID extracted
2. `requires_rfp_scope()` → Returns `False` (capability question)
3. Delegate to conversational agent
4. Conversational agent responds with capabilities list

### Example 3: "Upload this file as a new opportunity"

1. No RFP ID extracted
2. `requires_rfp_scope()` → Returns `False` (matches "upload.\*new" pattern)
3. Delegate to conversational agent
4. Conversational agent uses `slack_get_thread` → finds file → uses `rfp_create_from_slack_file`

### Example 4: "What's the status?"

1. No RFP ID in message, but thread is bound to `rfp_xyz789`
2. `rfp_id = "rfp_xyz789"` (from thread binding)
3. `requires_rfp_scope()` → Returns `None` (but we have RFP ID, so proceed)
4. Build context (includes RFP state)
5. Agent executes:
   - `opportunity_load` (protocol enforced)
   - `slack_post_summary` (posts status from OpportunityState)
