from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

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


def _is_model_access_error(e: Exception, *, model: str) -> bool:
    """
    Detect OpenAI errors that indicate the configured model isn't available to this project.
    We treat these as configuration problems and should fail fast (no retries).
    """
    msg = (str(e) or "").lower()
    if not msg:
        return False
    if "model_not_found" in msg:
        return True
    if "does not have access to model" in msg:
        return True
    if "not have access to model" in msg:
        return True
    if model and model.lower() in msg and "access" in msg and "model" in msg:
        return True
    return False


def _models_to_try(purpose: str) -> list[str]:
    """
    Prefer per-purpose model, then fall back to OPENAI_MODEL, then a known-safe default.
    """
    out: list[str] = []
    primary = str(settings.openai_model_for(purpose) or "").strip()
    if primary:
        out.append(primary)
    base = str(settings.openai_model or "").strip()
    if base and base not in out:
        out.append(base)
    if "gpt-4o-mini" not in out:
        out.append("gpt-4o-mini")
    return out


@dataclass(frozen=True)
class AiMeta:
    purpose: str
    model: str
    attempts: int
    used_response_format: str | None


def _client() -> Any:
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    try:
        # OpenAI Python SDK v1.x
        from openai import OpenAI  # type: ignore
    except Exception as e:
        # Avoid crashing the whole app at import-time if the OpenAI SDK isn't present
        # (or is an older incompatible version). We only require it when actually
        # making AI calls.
        raise AiNotConfigured(
            "OpenAI SDK is missing or incompatible. Install a v1.x SDK (e.g. openai>=1.0.0)."
        ) from e
    # We do our own retries; keep OpenAI client retries minimal.
    headers: dict[str, str] = {}
    # Force project routing if configured (matches OpenAI dashboard project id).
    if settings.openai_project_id and str(settings.openai_project_id).strip():
        headers["OpenAI-Project"] = str(settings.openai_project_id).strip()
    # org header is handled by SDK via organization parameter in newer versions,
    # but we also allow forcing it via headers for safety.
    if settings.openai_organization_id and str(settings.openai_organization_id).strip():
        headers["OpenAI-Organization"] = str(settings.openai_organization_id).strip()
    return OpenAI(
        api_key=settings.openai_api_key,
        max_retries=0,
        timeout=60,
        default_headers=headers or None,
    )


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


def _enforce_no_additional_properties(schema: Any) -> Any:
    """
    OpenAI structured outputs require `additionalProperties: false` on objects.
    Pydantic may omit it (implicitly allowing additional fields), so we enforce it.
    """
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
        for v in schema.values():
            _enforce_no_additional_properties(v)
    elif isinstance(schema, list):
        for v in schema:
            _enforce_no_additional_properties(v)
    return schema


def _should_retry_with_legacy_max_tokens(e: Exception) -> bool:
    msg = (str(e) or "").lower()
    # Some older models/endpoints only accept `max_tokens`.
    return "unsupported parameter" in msg and "max_completion_tokens" in msg


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
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    client = _client()
    messages = _normalize_messages(messages, max_prompt_chars)

    last_err: Exception | None = None
    for model in _models_to_try(purpose):
        for attempt in range(1, max(1, int(retries) + 1) + 1):
            try:
                try:
                    completion = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_completion_tokens=max_tokens,
                        temperature=temperature,
                    )
                except Exception as e:
                    if _should_retry_with_legacy_max_tokens(e):
                        completion = client.chat.completions.create(
                            model=model,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                    else:
                        raise
                out = (completion.choices[0].message.content or "").strip()
                if not out:
                    raise AiParseError("empty_model_response")
                return out, AiMeta(
                    purpose=purpose, model=model, attempts=attempt, used_response_format=None
                )
            except Exception as e:
                last_err = e
                if _is_model_access_error(e, model=model):
                    log.warning(
                        "ai_model_unavailable",
                        purpose=purpose,
                        model=model,
                        error=str(e),
                    )
                    # Try next fallback model immediately (no retries).
                    break
                log.warning(
                    "ai_text_failed",
                    purpose=purpose,
                    model=model,
                    attempt=attempt,
                    error=str(e),
                )
                time.sleep(
                    min(2.5, 0.3 * (2 ** (attempt - 1)) + random.random() * 0.15)
                )

    # If it looks like a model access issue, surface a config-style error.
    if last_err and _is_model_access_error(last_err, model=str(settings.openai_model_for(purpose) or "")):
        raise AiNotConfigured(
            f"Configured OpenAI model is not available for this project (purpose '{purpose}'). "
            f"Check OPENAI_MODEL / OPENAI_MODEL_* overrides."
        )
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

    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    client = _client()
    messages = _normalize_messages(messages, max_prompt_chars)

    schema = response_model.model_json_schema()
    schema = _enforce_no_additional_properties(schema)
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

    for model in _models_to_try(purpose):
        for attempt in range(1, max(1, int(retries)) + 1):
            model_hard_failed = False
            for response_format, temp in modes:
                used_rf = (
                    response_format.get("type")
                    if isinstance(response_format, dict)
                    else None
                )
                try:
                    kwargs_base: dict[str, Any] = {
                        "model": model,
                        "messages": messages,
                        "temperature": temp,
                    }
                    if response_format is not None:
                        kwargs_base["response_format"] = response_format

                    try:
                        completion = client.chat.completions.create(
                            **(kwargs_base | {"max_completion_tokens": max_tokens})
                        )
                    except Exception as e:
                        if _should_retry_with_legacy_max_tokens(e):
                            completion = client.chat.completions.create(
                                **(kwargs_base | {"max_tokens": max_tokens})
                            )
                        else:
                            raise

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
                    if _is_model_access_error(e, model=model):
                        log.warning(
                            "ai_model_unavailable",
                            purpose=purpose,
                            model=model,
                            error=str(e),
                        )
                        model_hard_failed = True
                        break
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

            if model_hard_failed:
                # Try next fallback model immediately.
                break

            # Sleep before next attempt round (same model)
            time.sleep(min(3.0, 0.4 * (2 ** (attempt - 1)) + random.random() * 0.2))

    if fallback is not None:
        # Use the primary model for meta; even if it failed, this is just telemetry.
        primary = str(settings.openai_model_for(purpose) or "").strip() or "unknown"
        return fallback(), AiMeta(
            purpose=purpose,
            model=primary,
            attempts=max(1, int(retries)),
            used_response_format=None,
        )

    if last_err and _is_model_access_error(last_err, model=str(settings.openai_model_for(purpose) or "")):
        raise AiNotConfigured(
            f"Configured OpenAI model is not available for this project (purpose '{purpose}'). "
            f"Check OPENAI_MODEL / OPENAI_MODEL_* overrides."
        )
    raise AiUpstreamError(str(last_err) if last_err else "ai_json_failed")


def stream_text(
    *,
    purpose: str,
    messages: list[dict[str, str]],
    max_tokens: int = 1200,
    temperature: float = 0.4,
    timeout_s: int = 90,
    max_prompt_chars: int = 220_000,
) -> tuple[object, AiMeta]:
    """
    Stream tokens from OpenAI chat.completions.

    Returns:
      - stream iterator (sync) yielding OpenAI events
      - AiMeta

    Note: This is for text streaming UX. For structured JSON extraction, streaming
    is usually not helpful because validation only happens once you have the full object.
    """
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    client = _client()
    messages = _normalize_messages(messages, max_prompt_chars)

    last_err: Exception | None = None
    for model in _models_to_try(purpose):
        try:
            try:
                stream = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )
            except Exception as e:
                if _should_retry_with_legacy_max_tokens(e):
                    stream = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stream=True,
                    )
                else:
                    raise
            return stream, AiMeta(
                purpose=purpose,
                model=model,
                attempts=1,
                used_response_format="stream",
            )
        except Exception as e:
            last_err = e
            if _is_model_access_error(e, model=model):
                log.warning(
                    "ai_model_unavailable",
                    purpose=purpose,
                    model=model,
                    error=str(e),
                )
                continue
            raise AiUpstreamError(str(e) or "ai_stream_failed")

    raise AiNotConfigured(
        f"Configured OpenAI model is not available for this project (purpose '{purpose}'). "
        f"Check OPENAI_MODEL / OPENAI_MODEL_* overrides."
    ) from last_err
