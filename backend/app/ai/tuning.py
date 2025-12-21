from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from ..settings import settings


AiKind = Literal["text", "json", "tools"]


@dataclass(frozen=True)
class AiTuning:
    """
    Per-call tuning inputs for GPT-5 family Responses API.
    """

    reasoning_effort: str
    verbosity: str


def _is_complex_tool(tool_name: str | None) -> bool:
    """
    Classify tools as complex based on their operation type.
    Complex tools require more reasoning effort.
    """
    if not tool_name:
        return False
    name = str(tool_name).strip().lower()
    
    # State management operations (write to durable artifacts)
    if name in ("opportunity_patch", "journal_append", "event_append", "create_change_proposal"):
        return True
    
    # Code/infrastructure operations
    if name.startswith(("self_modify_", "ecs_", "github_")):
        return True
    
    # High-risk actions
    if name == "propose_action":
        return True
    
    return False


def _is_medium_complexity_tool(tool_name: str | None) -> bool:
    """
    Classify tools as medium complexity.
    """
    if not tool_name:
        return False
    name = str(tool_name).strip().lower()
    
    # Workflow operations
    if name in ("schedule_job", "slack_post_summary", "slack_ask_clarifying_question"):
        return True
    
    return False


def _is_parse_failure(e: Exception | None) -> bool:
    # Avoid importing AiParseError here to prevent circular imports (client ↔ tuning).
    # We treat any exception named "AiParseError" as a parse/validation failure.
    return bool(e) and e.__class__.__name__ == "AiParseError"


def _escalate_effort(base: str, *, attempt: int, prev_err: Exception | None) -> str:
    """
    Escalate effort only when the *previous* attempt failed in a way that
    suggests "think harder" helps (parse/validation failures).
    
    Supports GPT-5.2 reasoning levels: none, low, medium, high, xhigh
    """
    a = max(1, int(attempt or 1))
    b = str(base or "").strip().lower() or "low"
    if a <= 1:
        return b
    if not _is_parse_failure(prev_err):
        return b
    # Parse failures: give the model more deliberation on retry.
    # Escalate through: low -> medium -> high -> xhigh
    effort_levels = ["none", "low", "medium", "high", "xhigh"]
    try:
        current_idx = effort_levels.index(b) if b in effort_levels else 1
        # Escalate by 1-2 levels on retry
        new_idx = min(len(effort_levels) - 1, current_idx + (2 if a >= 3 else 1))
        return effort_levels[new_idx]
    except (ValueError, IndexError):
        # Fallback escalation
        if a == 2:
            return "medium"
        elif a >= 3:
            return "high"
        return b


def _estimate_context_complexity(
    *,
    context_length: int = 0,
    has_rfp_state: bool = False,
    has_related_rfps: bool = False,
    has_cross_thread: bool = False,
) -> float:
    """
    Estimate context complexity score (0.0 to 2.0).
    Higher score = more complex context = higher reasoning needed.
    """
    score = 0.0
    
    # Base complexity from context length
    if context_length > 30000:
        score += 0.5
    elif context_length > 15000:
        score += 0.3
    elif context_length > 5000:
        score += 0.1
    
    # Additional complexity from context types
    if has_rfp_state:
        score += 0.3
    if has_related_rfps:
        score += 0.2
    if has_cross_thread:
        score += 0.2
    
    return min(2.0, score)


def _is_long_running_job(purpose: str, attempt: int) -> bool:
    """
    Detect if this is a long-running job operation.
    Long-running jobs benefit from higher reasoning.
    """
    purpose_lower = str(purpose or "").strip().lower()
    
    # Long-running job purposes
    if "long_running" in purpose_lower or "analyze_rfps" in purpose_lower:
        return True
    
    # High step count suggests long-running
    if attempt >= 10:
        return True
    
    return False


def tuning_for(
    *,
    purpose: str,
    kind: AiKind,
    attempt: int,
    prev_err: Exception | None = None,
    recent_tools: list[str] | None = None,
    context_length: int = 0,
    has_rfp_state: bool = False,
    has_related_rfps: bool = False,
    has_cross_thread: bool = False,
    is_long_running: bool = False,
) -> AiTuning:
    """
    Choose adaptive reasoning/verbosity by task kind, retry attempt, task complexity, and context.

    - Attempt 1 uses configured defaults (with complexity adjustments).
    - Attempt >=2 escalates reasoning effort ONLY for parse/validation failures.
    - For tools: complexity is inferred from recent tool calls, step count, and context.
    - Context-aware: Higher reasoning for complex contexts.
    - Time-based: Higher reasoning for long-running operations.
    
    Args:
        purpose: AI purpose string (e.g., "slack_agent")
        kind: Task kind ("text", "json", "tools")
        attempt: Step/attempt number (for tools, this is the step count)
        prev_err: Previous error (if retrying)
        recent_tools: List of tool names called in recent steps (for complexity detection)
        context_length: Estimated context length in characters
        has_rfp_state: Whether RFP state context is included
        has_related_rfps: Whether related RFPs context is included
        has_cross_thread: Whether cross-thread context is included
        is_long_running: Whether this is a long-running job operation
    """
    k = str(kind or "").strip().lower()

    if k == "json":
        base_eff = str(settings.openai_reasoning_effort_json or settings.openai_reasoning_effort or "low")
        base_vb = str(settings.openai_text_verbosity_json or settings.openai_text_verbosity or "low")
        return AiTuning(
            reasoning_effort=_escalate_effort(base_eff, attempt=attempt, prev_err=prev_err),
            verbosity=str(base_vb or "low").strip() or "low",
        )

    if k == "tools":
        # Tool-using agents: use step-based escalation with complexity awareness.
        # (We can't pass temperature anyway with GPT-5 effort != none.)
        steps = max(1, int(attempt or 1))
        
        # Check for complex operations in recent tool calls
        has_complex_tool = False
        has_medium_tool = False
        if recent_tools:
            for tool in recent_tools:
                if _is_complex_tool(tool):
                    has_complex_tool = True
                elif _is_medium_complexity_tool(tool):
                    has_medium_tool = True
        
        # Estimate context complexity
        context_complexity = _estimate_context_complexity(
            context_length=context_length,
            has_rfp_state=has_rfp_state,
            has_related_rfps=has_related_rfps,
            has_cross_thread=has_cross_thread,
        )
        
        # Detect long-running operations
        if not is_long_running:
            is_long_running = _is_long_running_job(purpose, steps)
        
        # Determine base effort: start higher for complex operations
        # Default base is now "medium" instead of "low" for better quality on agent tasks
        base_eff = str(settings.openai_reasoning_effort_json or settings.openai_reasoning_effort or "medium")
        if base_eff == "low":
            # Upgrade low to medium as default for tools (agent tasks are inherently more complex)
            base_eff = "medium"
        
        # Adjust base effort for context complexity
        if context_complexity > 1.0:
            # Very complex context: start at high
            if base_eff == "medium":
                base_eff = "high"
        elif context_complexity > 0.5:
            # Moderately complex context: ensure at least medium
            if base_eff == "low":
                base_eff = "medium"
        
        # Adjust for long-running operations
        if is_long_running:
            # Long-running jobs: use higher reasoning throughout
            if base_eff == "medium":
                base_eff = "high"
            elif base_eff == "low":
                base_eff = "medium"
        
        # Escalate based on steps and complexity (GPT-5.2: supports up to xhigh)
        if has_complex_tool:
            # Complex operations: escalate faster, can reach xhigh for very complex cases
            if steps >= 8 or (steps >= 6 and context_complexity > 1.5):
                eff = "xhigh"  # GPT-5.2: use xhigh for very complex multi-step operations
            elif steps >= 4:
                eff = "high"
            elif steps >= 2:
                eff = "medium"
            else:
                eff = base_eff
        elif has_medium_tool:
            # Medium complexity: moderate escalation
            if steps >= 10 or (steps >= 7 and context_complexity > 1.5):
                eff = "xhigh"  # Escalate to xhigh for persistent complex operations
            elif steps >= 5:
                eff = "high"
            elif steps >= 2:
                eff = "medium"
            else:
                eff = base_eff
        else:
            # Simple operations: step-based escalation (improved thresholds)
            if steps >= 12 or (steps >= 8 and context_complexity > 1.5):
                eff = "xhigh"  # Even simple ops can need xhigh if they persist
            elif steps >= 6:
                eff = "high"
            elif steps >= 3:
                eff = "medium"
            else:
                eff = base_eff
        
        # Apply context complexity boost (can push to xhigh)
        if context_complexity > 1.5:
            # Very complex context: escalate to high or xhigh
            if eff == "high" and (steps >= 6 or is_long_running):
                eff = "xhigh"
            elif eff == "medium":
                eff = "high"
            elif eff == "low":
                eff = "medium"
        elif context_complexity > 1.0:
            if eff == "medium":
                eff = "high"
            elif eff == "low":
                eff = "medium"
        elif context_complexity > 0.5:
            if eff == "low":
                eff = "medium"
        
        # Apply long-running boost (can push to xhigh)
        if is_long_running:
            if eff == "high" and steps >= 5:
                eff = "xhigh"  # Long-running + high effort + many steps = xhigh
            elif eff == "medium":
                eff = "high"
            elif eff == "low":
                eff = "medium"
        
        vb = str(settings.openai_text_verbosity_json or settings.openai_text_verbosity or "low")
        return AiTuning(reasoning_effort=str(eff).strip() or "medium", verbosity=str(vb).strip() or "low")

    # text
    base_eff = str(settings.openai_reasoning_effort_text or settings.openai_reasoning_effort or "none")
    base_vb = str(settings.openai_text_verbosity or "medium")

    eff = _escalate_effort(base_eff, attempt=attempt, prev_err=prev_err)

    vb = str(base_vb or "medium").strip() or "medium"
    # For writing-ish tasks, verbosity can be bumped on parse/validation retries.
    if int(attempt or 1) >= 2 and _is_parse_failure(prev_err):
        if str(purpose or "").strip().lower() in ("generate_content", "proposal_sections", "text_edit"):
            vb = "high"

    return AiTuning(reasoning_effort=str(eff).strip() or "none", verbosity=vb)


Validator = Callable[[str], str | None]

