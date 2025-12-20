from __future__ import annotations

from typing import Callable, TypeVar

from pydantic import BaseModel

from .client import AiMeta, call_json, call_text
from .verification import (
    Validator,
    forbid_contains,
    forbid_regex,
    require_max_chars,
    require_nonempty,
)

T = TypeVar("T", bound=BaseModel)
ParsedValidator = Callable[[T], str | None]


def text_validators_for(*, purpose: str) -> list[Validator]:
    """
    Purpose-scoped deterministic validation for text outputs.

    Keep these rules conservative: they should reject clearly-wrong outputs
    (empty, tool/meta chatter, code fences where forbidden), not "style" choices.
    """
    p = str(purpose or "").strip().lower()
    out: list[Validator] = [require_nonempty(what="output")]

    # Very common failure modes we never want in user-facing content.
    if p in ("text_edit", "generate_content", "proposal_sections", "rfp_section_summary"):
        out.append(
            forbid_contains(
                needles=[
                    "As an AI",
                    "as an ai",
                    "I can't",
                    "I cannot",
                    "I’m sorry",
                    "I'm sorry",
                    "I apologize",
                ],
                what="output",
            )
        )

    if p == "text_edit":
        # Must return only edited text, no commentary.
        out.append(
            forbid_regex(pattern=r"(^|\n)\s*(explanation|notes|changes made)\s*:", flags=0, what="output")
        )

    if p == "rfp_section_summary":
        # Plain text only: no headings, bullets, or code fences.
        out.append(require_max_chars(n=1200, what="output"))
        out.append(forbid_regex(pattern=r"(^|\n)\s*#{1,6}\s+", what="output"))
        out.append(forbid_regex(pattern=r"(^|\n)\s*[-*]\s+", what="output"))
        out.append(forbid_regex(pattern=r"```", what="output"))

    if p == "proposal_sections":
        # We expect markdown, but code fences in proposal sections are almost always noise.
        out.append(forbid_regex(pattern=r"(^|\n)\s*```", what="output"))

    return out


def call_text_verified(
    *,
    purpose: str,
    messages: list[dict[str, str]],
    max_tokens: int = 1200,
    temperature: float = 0.4,
    validate: Validator | list[Validator] | None = None,
    validate_extra: Validator | list[Validator] | None = None,
    retries: int = 2,
    timeout_s: int = 60,
    max_prompt_chars: int = 220_000,
) -> tuple[str, AiMeta]:
    base = text_validators_for(purpose=purpose)

    extras: list[Validator] = []
    if validate is not None:
        extras.extend(validate if isinstance(validate, list) else [validate])
    if validate_extra is not None:
        extras.extend(validate_extra if isinstance(validate_extra, list) else [validate_extra])

    return call_text(
        purpose=purpose,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        validate=(base + extras) if (base or extras) else None,
        retries=retries,
        timeout_s=timeout_s,
        max_prompt_chars=max_prompt_chars,
    )


def call_json_verified(
    *,
    purpose: str,
    response_model: type[T],
    messages: list[dict[str, str]],
    max_tokens: int = 1200,
    temperature: float = 0.2,
    retries: int = 3,
    allow_json_extract: bool = True,
    validate_parsed: ParsedValidator[T] | None = None,
    fallback: Callable[[], T] | None = None,
    timeout_s: int = 60,
    max_prompt_chars: int = 220_000,
) -> tuple[T, AiMeta]:
    return call_json(
        purpose=purpose,
        response_model=response_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        retries=retries,
        allow_json_extract=allow_json_extract,
        validate_parsed=validate_parsed,
        fallback=fallback,
        timeout_s=timeout_s,
        max_prompt_chars=max_prompt_chars,
    )

