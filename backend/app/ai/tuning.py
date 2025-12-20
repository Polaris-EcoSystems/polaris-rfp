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


def tuning_for(*, purpose: str, kind: AiKind, attempt: int, prev_err: Exception | None = None) -> AiTuning:
    """
    Choose adaptive reasoning/verbosity by task kind and retry attempt.

    - Attempt 1 uses configured defaults.
    - Attempt >=2 escalates reasoning effort ONLY for parse/validation failures.
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
        # Tool-using agents benefit from a bit more effort when a run takes many steps.
        # (We can't pass temperature anyway with GPT-5 effort != none.)
        steps = max(1, int(attempt or 1))
        if steps >= 6:
            eff = "high"
        elif steps >= 3:
            eff = "medium"
        else:
            eff = str(settings.openai_reasoning_effort_json or "low")
        vb = str(settings.openai_text_verbosity_json or settings.openai_text_verbosity or "low")
        return AiTuning(reasoning_effort=str(eff).strip() or "low", verbosity=str(vb).strip() or "low")

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

