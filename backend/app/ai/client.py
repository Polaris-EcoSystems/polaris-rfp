from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from ..observability.logging import get_logger
from ..settings import settings

log = get_logger("ai")

T = TypeVar("T", bound=BaseModel)


class AiError(RuntimeError):
    pass


class AiNotConfigured(AiError):
    pass


class AiUpstreamError(AiError):
    pass


class AiParseError(AiError):
    pass


@dataclass(frozen=True)
class AiMeta:
    purpose: str
    model: str
    attempts: int
    used_response_format: str | None


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    # We do our own retries; keep OpenAI client retries minimal.
    return OpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=60)


def _clip(s: str, max_len: int) -> str:
    s = str(s or "")
    if len(s) <= max_len:
        return s
    return s[:max_len]


def _normalize_messages(messages: list[dict[str, str]], max_chars: int) -> list[dict[str, str]]:
    # Guard against accidentally sending huge prompts (which can time out or explode costs).
    out: list[dict[str, str]] = []
    for m in messages or []:
        role = str(m.get("role") or "user")
        content = _clip(str(m.get("content") or ""), max_chars)
        out.append({"role": role, "content": content})
    return out


def _extract_first_json_object(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else None


def call_text(
    *,
    purpose: str,
    messages: list[dict[str, str]],
    max_tokens: int = 1200,
    temperature: float = 0.4,
    retries: int = 2,
    timeout_s: int = 60,
    max_prompt_chars: int = 220_000,
) -> tuple[str, AiMeta]:
    model = settings.openai_model_for(purpose)
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=int(timeout_s or 60))  # type: ignore[arg-type]
    messages = _normalize_messages(messages, max_prompt_chars)

    last_err: Exception | None = None
    for attempt in range(1, max(1, int(retries) + 1) + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            out = (completion.choices[0].message.content or "").strip()
            if not out:
                raise AiParseError("empty_model_response")
            return out, AiMeta(purpose=purpose, model=model, attempts=attempt, used_response_format=None)
        except Exception as e:
            last_err = e
            log.warning(
                "ai_text_failed",
                purpose=purpose,
                model=model,
                attempt=attempt,
                error=str(e),
            )
            time.sleep(min(2.5, 0.3 * (2 ** (attempt - 1)) + random.random() * 0.15))

    raise AiUpstreamError(str(last_err) if last_err else "ai_text_failed")


def call_json(
    *,
    purpose: str,
    response_model: type[T],
    messages: list[dict[str, str]],
    max_tokens: int = 1200,
    temperature: float = 0.2,
    retries: int = 3,
    allow_json_extract: bool = True,
    fallback: Callable[[], T] | None = None,
    timeout_s: int = 60,
    max_prompt_chars: int = 220_000,
) -> tuple[T, AiMeta]:
    """Call OpenAI and parse into a Pydantic model.

    Strategy:
    - Try JSON schema enforcement (response_format json_schema)
    - Then JSON object enforcement (response_format json_object)
    - Then best-effort extraction of first {...} block

    If fallback is provided, returns it on failure instead of raising.
    """

    model = settings.openai_model_for(purpose)
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=int(timeout_s or 60))  # type: ignore[arg-type]
    messages = _normalize_messages(messages, max_prompt_chars)

    schema = response_model.model_json_schema()
    # OpenAI structured output format wrapper.
    rf_json_schema: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": {
            "name": response_model.__name__,
            "schema": schema,
            "strict": True,
        },
    }
    rf_json_object: dict[str, Any] = {"type": "json_object"}

    last_err: Exception | None = None
    last_preview: str | None = None

    # (response_format, temperature)
    modes: list[tuple[dict[str, Any] | None, float]] = [
        (rf_json_schema, 0.0),
        (rf_json_object, 0.0),
        (None, temperature),
    ]

    for attempt in range(1, max(1, int(retries)) + 1):
        for response_format, temp in modes:
            used_rf = response_format.get("type") if isinstance(response_format, dict) else None
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temp,
                }
                if response_format is not None:
                    kwargs["response_format"] = response_format

                completion = client.chat.completions.create(**kwargs)
                content = (completion.choices[0].message.content or "").strip()
                if not content:
                    raise AiParseError("empty_model_response")

                raw_json = content
                if used_rf is None and allow_json_extract:
                    extracted = _extract_first_json_object(content)
                    if extracted:
                        raw_json = extracted

                try:
                    data = json.loads(raw_json)
                except Exception as e:
                    raise AiParseError(f"json_decode_error: {e}")

                try:
                    parsed = response_model.model_validate(data)
                except Exception as e:
                    raise AiParseError(f"schema_validation_error: {e}")

                return parsed, AiMeta(
                    purpose=purpose,
                    model=model,
                    attempts=attempt,
                    used_response_format=used_rf,
                )
            except Exception as e:
                last_err = e
                last_preview = (locals().get("content") or "")[:240]
                log.warning(
                    "ai_json_failed",
                    purpose=purpose,
                    model=model,
                    attempt=attempt,
                    response_format=used_rf,
                    error=str(e),
                    content_preview=last_preview,
                )
                # try next mode without sleeping
                continue

        # Sleep before next attempt round
        time.sleep(min(3.0, 0.4 * (2 ** (attempt - 1)) + random.random() * 0.2))

    if fallback is not None:
        return fallback(), AiMeta(
            purpose=purpose,
            model=model,
            attempts=max(1, int(retries)),
            used_response_format=None,
        )

    raise AiUpstreamError(str(last_err) if last_err else "ai_json_failed")
