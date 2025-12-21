# Slack Operator Agent Enhancement Ideas

This document outlines potential improvements to refine and enhance various steps in the decision algorithm.

## 1. RFP Scope Detection (`_operations_requiring_rfp_scope`)

### Current Approach

- Keyword/phrase matching with priority-based evaluation
- Returns: `True`, `False`, or `None`

### Enhancement Ideas

#### A. Confidence Scoring

Instead of binary/ternary, return a confidence score:

```python
def _operations_requiring_rfp_scope(question: str) -> dict[str, Any]:
    """
    Returns:
    {
        "requires_rfp": bool | None,
        "confidence": float,  # 0.0 to 1.0
        "indicators": list[str],  # Which phrases matched
        "reasoning": str  # Brief explanation
    }
    """
```

**Benefits:**

- Can make nuanced decisions (e.g., "requires_rfp=True with low confidence, try conversational agent first")
- Better debugging and explainability
- Can track which patterns are most reliable over time

#### B. ML-Based Intent Classification

Use a lightweight classifier (fine-tuned small model or few-shot learning):

```python
def _classify_rfp_scope_intent(question: str) -> dict[str, Any]:
    """
    Uses semantic understanding rather than keyword matching.
    Could use:
    - Embedding similarity to known patterns
    - Fine-tuned classifier on historical data
    - Few-shot learning with examples
    """
```

**Benefits:**

- Handles paraphrasing better ("change the opportunity status" vs "update opportunity state")
- Learns from corrections (when user says "no, I didn't mean that")
- More maintainable than growing keyword lists

#### C. Context-Aware Detection

Consider thread history and user patterns:

```python
def _operations_requiring_rfp_scope(
    question: str,
    thread_context: str | None = None,
    user_history: list[str] | None = None
) -> bool | None:
    """
    Analyzes question in context of:
    - Recent messages in thread
    - User's typical patterns (do they often work with RFPs?)
    - Thread binding history
    """
```

**Benefits:**

- "What's the status?" in an RFP thread → likely needs RFP scope
- "What's the status?" in general channel → likely global query
- Better handling of pronoun references ("update it", "change that")

#### D. Pattern Learning

Track which patterns lead to successful outcomes:

```python
# Store pattern → outcome mappings
# When user corrects: "no, I meant global" → learn that pattern
# When operation succeeds without RFP scope → reinforce False classification
```

**Benefits:**

- Continuously improves from user feedback
- Adapts to organization-specific language
- Reduces false positives/negatives over time

---

## 2. Routing Decision (Step 6)

### Current Approach

- Simple branching: `requires_rfp` → route to conversational agent or ask for RFP

### Enhancement Ideas

#### A. Multi-Agent Orchestration

Route to specialized sub-agents based on intent:

```python
# Current: operator_agent OR conversational_agent
# Enhanced: route to specialized agents:
- rfp_state_agent: RFP-scoped operations (opportunity_patch, journal_append)
- query_agent: Read-only queries (list_rfps, search)
- job_agent: Job scheduling and management
- file_agent: File uploads and document processing
- admin_agent: Infrastructure/ops queries
```

**Benefits:**

- Each agent has focused system prompt (smaller, more accurate)
- Specialized toolsets per agent
- Better token efficiency
- Can optimize each agent independently

#### B. Adaptive Routing with Fallback

Try lightweight path first, escalate if needed:

```python
def route_request(question: str, requires_rfp: bool | None) -> RoutingDecision:
    """
    1. Try lightweight conversational agent first (fast, cheap)
    2. If it indicates need for write operations → escalate to operator agent
    3. If unclear → ask user for clarification
    """
```

**Benefits:**

- Faster responses for simple queries
- Cost-efficient (use cheaper model for routing)
- Better UX (immediate feedback vs. waiting for full context building)

#### C. Predictive Routing

Pre-fetch context based on predicted needs:

```python
def route_with_prediction(question: str) -> RoutingDecision:
    """
    Predict likely tools/context needed:
    - If predicts RFP scope → start building RFP context in parallel
    - If predicts file upload → check for files immediately
    - Reduces latency by doing work in parallel
    """
```

---

## 3. Context Building (Step 7-8)

### Current Approach

- Builds comprehensive context with multiple layers
- Fixed max character limits
- Query-aware memory retrieval

### Enhancement Ideas

#### A. Adaptive Context Sizing

Dynamically adjust context based on query complexity:

```python
def build_context_with_adaptive_sizing(
    query: str,
    metaprompt: str,
    base_context: str
) -> str:
    """
    - Simple queries → minimal context (fast, cheap)
    - Complex queries → comprehensive context
    - Use metaprompt analysis to determine needed depth
    """
```

**Benefits:**

- Faster responses for simple queries
- More thorough for complex requests
- Cost optimization (fewer tokens for simple queries)

#### B. Context Relevance Scoring

Rank context chunks by relevance to query:

```python
def build_context_with_relevance_scoring(
    query: str,
    context_sources: list[dict[str, Any]]
) -> str:
    """
    - Score each context chunk by semantic similarity to query
    - Include only top-N most relevant chunks
    - Ensures most useful context within token limits
    """
```

**Benefits:**

- Better quality context (more signal, less noise)
- Can include more diverse context types within limits
- Reduces hallucination from irrelevant context

#### C. Incremental Context Loading

Load context progressively as needed:

```python
def execute_with_incremental_context(question: str):
    """
    1. Start with minimal context (user, basic thread)
    2. Agent requests specific context as needed ("I need RFP state")
    3. Load that context and continue
    - Reduces initial latency
    - More token-efficient
    """
```

**Benefits:**

- Faster time-to-first-response
- Only load what's actually needed
- Better for long-running conversations

#### D. Context Compression

Use summarization for long context:

```python
def compress_context(context: str, target_length: int) -> str:
    """
    - Summarize thread history (keep key points)
    - Summarize journal entries (focus on recent decisions)
    - Keep full detail only for most recent/relevant items
    """
```

**Benefits:**

- Fit more information in token budget
- Prioritize recent/relevant information
- Maintains essential context while reducing verbosity

---

## 4. Metaprompt Generation (Step 9)

### Current Approach

- AI-generated analysis of request
- Simple keyword-based fallback
- Single-shot generation

### Enhancement Ideas

#### A. Structured Metaprompt Analysis

Generate structured analysis instead of free-form text:

```python
def _generate_structured_metaprompt(question: str) -> dict[str, Any]:
    """
    Returns:
    {
        "intent": "update_rfp_state" | "query" | "schedule_job" | ...
        "complexity": "simple" | "moderate" | "complex",
        "required_tools": ["opportunity_load", "opportunity_patch"],
        "likely_steps": 3,
        "missing_info": ["rfp_id"],  # If not in context
        "confidence": 0.85
    }
    """
```

**Benefits:**

- More actionable guidance for agent
- Can programmatically use analysis (e.g., pre-load tools)
- Easier to validate and improve

#### B. Multi-Turn Metaprompt Refinement

Refine analysis based on tool execution results:

```python
def refine_metaprompt_after_tool_call(
    original_metaprompt: dict[str, Any],
    tool_called: str,
    tool_result: dict[str, Any]
) -> dict[str, Any]:
    """
    - If tool failed → update analysis with why
    - If partial success → adjust expectations
    - Provides better guidance for subsequent steps
    """
```

#### C. Template-Based Metaprompts

Use templates for common patterns:

```python
METAPROMPT_TEMPLATES = {
    "update_rfp_status": "User wants to update RFP status. Requires: opportunity_load → opportunity_patch → journal_append",
    "query_rfp_info": "User wants information about an RFP. Requires: get_rfp (read-only, no RFP scope needed if query is general)",
    # ...
}

def _generate_metaprompt_from_template(question: str) -> str:
    # Match to template, customize with query details
```

**Benefits:**

- Faster (no LLM call for common cases)
- More consistent
- Can be manually curated for accuracy

---

## 5. Protocol Enforcement (`_inject_and_enforce`)

### Current Approach

- Hard requirements: must call `opportunity_load` before other RFP tools
- Must write before posting

### Enhancement Ideas

#### A. Protocol Relaxation Based on Context

Relax protocols when context is already loaded:

```python
def _inject_and_enforce(
    tool_name: str,
    tool_args: dict[str, Any],
    context_already_loaded: bool = False
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """
    - If comprehensive context includes fresh RFP state → skip opportunity_load
    - If this is a read-only query → skip write requirement
    - More flexible while maintaining safety
    """
```

**Benefits:**

- Faster for read-only operations
- Reduces redundant API calls
- Still enforces for write operations

#### B. Protocol Suggestions Instead of Errors

Guide agent instead of blocking:

```python
# Instead of returning error, return warning suggestion:
{
    "ok": True,
    "warning": "Consider calling opportunity_load first for better context",
    "suggestion": "opportunity_load"
}
```

**Benefits:**

- Agent can choose (sometimes it knows better)
- Better for learning (agent sees consequences)
- More flexible for edge cases

#### C. Context-Aware Protocol Bypass

Detect when protocol is unnecessary:

```python
def _should_bypass_load_protocol(
    tool_name: str,
    recent_tool_calls: list[str],
    context_freshness: datetime
) -> bool:
    """
    - If opportunity_load was called recently → bypass
    - If context is fresh (within last 30s) → bypass
    - Reduces redundant loads in multi-turn conversations
    """
```

---

## 6. Tool Selection & Execution

### Current Approach

- Agent chooses tools freely
- Procedural memory provides patterns
- Retry logic for failures

### Enhancement Ideas

#### A. Tool Recommendation Engine

Actively recommend tools based on query and context:

```python
def recommend_tools(
    query: str,
    context: dict[str, Any],
    procedural_memories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Returns:
    [
        {"tool": "opportunity_load", "confidence": 0.95, "reason": "Required for RFP operations"},
        {"tool": "get_rfp", "confidence": 0.70, "reason": "May need RFP details"},
        # ...
    ]
    """
```

**Benefits:**

- Guides agent toward correct tools
- Reduces trial-and-error
- Faster task completion

#### B. Tool Chain Prediction

Predict likely tool sequences:

```python
def predict_tool_chain(
    query: str,
    similar_queries: list[dict[str, Any]]
) -> list[list[str]]:
    """
    Returns likely tool sequences:
    [
        ["opportunity_load", "opportunity_patch", "journal_append"],
        ["get_rfp", "opportunity_load", "opportunity_patch"],
        # Ranked by likelihood
    ]
    """
```

**Benefits:**

- Agent can follow proven patterns
- Reduces mistakes
- Faster execution

#### C. Tool Execution Planning

Generate execution plan before starting:

```python
def generate_execution_plan(
    query: str,
    available_context: dict[str, Any]
) -> ExecutionPlan:
    """
    {
        "steps": [
            {"tool": "opportunity_load", "args": {...}, "reason": "..."},
            {"tool": "opportunity_patch", "args": {...}, "dependencies": ["opportunity_load"]},
        ],
        "estimated_steps": 3,
        "risk_level": "low"
    }
    """
```

**Benefits:**

- Can validate plan before execution
- User can preview/approve complex operations
- Better error handling (know what's coming)

#### D. Adaptive Max Steps

Dynamically adjust `max_steps` based on complexity:

```python
def determine_max_steps(
    query: str,
    metaprompt: dict[str, Any],
    procedural_patterns: list[dict[str, Any]]
) -> int:
    """
    - Simple queries → 3-4 steps
    - Moderate complexity → 6-8 steps
    - Complex workflows → 12-15 steps
    - Based on metaprompt analysis and historical patterns
    """
```

**Benefits:**

- Prevents premature termination for complex requests
- Faster completion for simple requests
- Better resource utilization

#### E. Tool Result Validation

Validate tool results before passing to next step:

```python
def validate_tool_result(
    tool_name: str,
    result: dict[str, Any],
    expected_schema: dict[str, Any]
) -> ValidationResult:
    """
    - Check result has expected fields
    - Validate data types and ranges
    - Catch errors early before they propagate
    """
```

---

## 7. Learning & Improvement

### Current Approach

- Procedural memory storage
- Failure pattern tracking
- Best practices extraction

### Enhancement Ideas

#### A. Online Learning from Corrections

Learn immediately from user feedback:

```python
def learn_from_correction(
    original_query: str,
    user_correction: str,
    attempted_tools: list[str],
    correct_approach: str
):
    """
    When user says "no, I meant X":
    - Store correction pattern
    - Update intent classification
    - Adjust tool recommendations
    - Immediate effect (no batch processing needed)
    """
```

#### B. A/B Testing Framework

Test different approaches:

```python
def route_with_ab_test(query: str) -> RoutingDecision:
    """
    - 10% of requests → use experimental routing
    - Track success metrics
    - Gradually roll out better approaches
    """
```

#### C. Performance Monitoring & Optimization

Track and optimize:

```python
def track_operation_metrics(
    query: str,
    routing_decision: dict[str, Any],
    execution_time: float,
    steps_taken: int,
    success: bool,
    user_satisfaction: float | None
):
    """
    - Identify slow queries
    - Find inefficient patterns
    - Optimize hot paths
    - Measure improvement over time
    """
```

---

## 8. User Experience Enhancements

### Current Approach

- Silent execution (posts results)
- Clarifying questions when blocking

### Enhancement Ideas

#### A. Progressive Disclosure

Show progress for long operations:

```python
def execute_with_progress_updates(question: str):
    """
    1. "Analyzing your request..." (immediate)
    2. "Loading RFP context..." (after context decision)
    3. "Updating opportunity state..." (during tool execution)
    4. "Done!" (final result)
    """
```

#### B. Explanatory Responses

Explain what was done and why:

```python
def format_response_with_explanation(
    result: dict[str, Any],
    tools_used: list[str],
    reasoning: str
) -> str:
    """
    "I updated the opportunity status to 'proposal submitted'
    (used opportunity_patch) and added a journal entry documenting
    the decision. This is based on the information from opportunity_load."
    """
```

#### C. Confidence Indicators

Show confidence in response:

```python
def format_response_with_confidence(
    result: dict[str, Any],
    confidence: float
) -> str:
    """
    High confidence: "The RFP status is 'proposal submitted'."
    Low confidence: "Based on available information, the RFP status
    appears to be 'proposal submitted' (please verify)."
    """
```

---

## Implementation Priority

### Quick Wins (Low effort, high impact)

1. ✅ **Tighter RFP scope detection** (already done)
2. **Confidence scoring for RFP scope** (enhancement 1A)
3. **Context relevance scoring** (enhancement 3B)
4. **Structured metaprompt** (enhancement 4A)
5. **Adaptive max steps** (enhancement 6D)

### Medium-term (Moderate effort, high impact)

1. **Context-aware scope detection** (enhancement 1C)
2. **Adaptive context sizing** (enhancement 3A)
3. **Tool recommendation engine** (enhancement 6A)
4. **Protocol relaxation** (enhancement 5A)
5. **Progressive disclosure** (enhancement 8A)

### Long-term (Higher effort, strategic value)

1. **ML-based intent classification** (enhancement 1B)
2. **Multi-agent orchestration** (enhancement 2A)
3. **Online learning from corrections** (enhancement 7A)
4. **A/B testing framework** (enhancement 7B)
5. **Tool execution planning** (enhancement 6C)

---

## Metrics to Track

To measure improvement:

1. **Accuracy:**

   - RFP scope detection accuracy (% correct)
   - Tool selection accuracy (% appropriate tools used)
   - Routing accuracy (% correctly routed)

2. **Performance:**

   - Average response time
   - Steps taken per request
   - Token usage per request

3. **User Experience:**

   - User satisfaction (thumbs up/down)
   - Correction rate (% of responses that need correction)
   - Task completion rate (% of requests fully satisfied)

4. **Efficiency:**
   - Redundant tool calls (opportunity_load called multiple times)
   - Context size vs. actual usage
   - Cache hit rates
