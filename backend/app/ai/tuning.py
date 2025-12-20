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
    """
    a = max(1, int(attempt or 1))
    b = str(base or "").strip().lower() or "low"
    if a <= 1:
        return b
    if not _is_parse_failure(prev_err):
        return b
    # Parse failures: give the model more deliberation on retry.
    if a == 2:
        return "medium"
    return "high"


def tuning_for(
    *,
    purpose: str,
    kind: AiKind,
    attempt: int,
    prev_err: Exception | None = None,
    recent_tools: list[str] | None = None,
) -> AiTuning:
    """
    Choose adaptive reasoning/verbosity by task kind, retry attempt, and task complexity.

    - Attempt 1 uses configured defaults (with complexity adjustments).
    - Attempt >=2 escalates reasoning effort ONLY for parse/validation failures.
    - For tools: complexity is inferred from recent tool calls and step count.
    
    Args:
        purpose: AI purpose string (e.g., "slack_agent")
        kind: Task kind ("text", "json", "tools")
        attempt: Step/attempt number (for tools, this is the step count)
        prev_err: Previous error (if retrying)
        recent_tools: List of tool names called in recent steps (for complexity detection)
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
        
        # Determine base effort: start higher for complex operations
        # Default base is now "medium" instead of "low" for better quality on agent tasks
        base_eff = str(settings.openai_reasoning_effort_json or settings.openai_reasoning_effort or "medium")
        if base_eff == "low":
            # Upgrade low to medium as default for tools (agent tasks are inherently more complex)
            base_eff = "medium"
        
        # Escalate based on steps and complexity
        if has_complex_tool:
            # Complex operations: escalate faster
            if steps >= 4:
                eff = "high"
            elif steps >= 2:
                eff = "medium"
            else:
                eff = "medium"  # Start at medium for complex ops
        elif has_medium_tool:
            # Medium complexity: moderate escalation
            if steps >= 5:
                eff = "high"
            elif steps >= 2:
                eff = "medium"
            else:
                eff = base_eff
        else:
            # Simple operations: step-based escalation (improved thresholds)
            if steps >= 6:
                eff = "high"
            elif steps >= 3:
                eff = "medium"
            else:
                eff = base_eff
        
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

