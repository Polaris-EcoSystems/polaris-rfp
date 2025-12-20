from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from ..observability.logging import get_logger
from ..settings import settings
from .tuning import Validator, tuning_for

log = get_logger("ai")

T = TypeVar("T", bound=BaseModel)
ParsedValidator = Callable[[BaseModel], str | None]


class AiError(RuntimeError):
    pass


class AiNotConfigured(AiError):
    pass


class AiUpstreamError(AiError):
    pass


class AiParseError(AiError):
    pass


_CIRCUIT_OPEN_UNTIL: float = 0.0
_CONSECUTIVE_FAILURES: int = 0
_LAST_FAILURE_AT: float = 0.0


def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "status", "http_status"):
        try:
            v = getattr(exc, attr, None)
            if v is not None:
                return int(v)
        except Exception:
            pass
    try:
        resp = getattr(exc, "response", None)
        v = getattr(resp, "status_code", None)
        if v is not None:
            return int(v)
    except Exception:
        pass
    return None


def _is_retryable(exc: Exception) -> bool:
    code = _status_code(exc)
    if code in (408, 409, 425, 429, 500, 502, 503, 504):
        return True
    msg = (str(exc) or "").lower()
    if any(k in msg for k in ("timeout", "timed out", "temporarily unavailable", "connection", "rate limit")):
        return True
    return False


def _circuit_check() -> None:
    global _CIRCUIT_OPEN_UNTIL
    now = time.time()
    if _CIRCUIT_OPEN_UNTIL and now < _CIRCUIT_OPEN_UNTIL:
        raise AiUpstreamError("ai_temporarily_unavailable")


def _circuit_record_success() -> None:
    global _CONSECUTIVE_FAILURES, _LAST_FAILURE_AT, _CIRCUIT_OPEN_UNTIL
    _CONSECUTIVE_FAILURES = 0
    _LAST_FAILURE_AT = 0.0
    _CIRCUIT_OPEN_UNTIL = 0.0


def _circuit_record_failure(exc: Exception) -> None:
    """
    Basic circuit breaker:
    - If we see repeated retryable upstream failures, open the circuit briefly to avoid stampedes.
    """
    global _CONSECUTIVE_FAILURES, _LAST_FAILURE_AT, _CIRCUIT_OPEN_UNTIL
    if not _is_retryable(exc):
        return
    now = time.time()
    # If failures are spaced out, decay the counter.
    if _LAST_FAILURE_AT and (now - _LAST_FAILURE_AT) > 60:
        _CONSECUTIVE_FAILURES = 0
    _LAST_FAILURE_AT = now
    _CONSECUTIVE_FAILURES += 1
    if _CONSECUTIVE_FAILURES >= 5:
        # Open for a short period; callers should surface a retryable error.
        _CIRCUIT_OPEN_UNTIL = now + 15


def _is_gpt5_family(model: str) -> bool:
    m = (model or "").strip().lower()
    return m.startswith("gpt-5")


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
    response_id: str | None = None


def _client(*, timeout_s: int = 60) -> Any:
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    try:
        # OpenAI Python SDK v1.x
        from openai import OpenAI
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
        timeout=max(5, int(timeout_s or 60)),
        default_headers=headers or None,
    )


def _supports_responses_api(client: Any) -> bool:
    """
    Some OpenAI SDK versions ship without `client.responses`.
    We treat Responses API as optional and fall back to chat.completions when missing.
    """
    try:
        r = getattr(client, "responses", None)
        return bool(r) and callable(getattr(r, "create", None))
    except Exception:
        return False


def _clip(s: str, max_len: int) -> str:
    s = str(s or "")
    if len(s) <= max_len:
        return s
    return s[:max_len]


def _is_parse_failure(e: Exception | None) -> bool:
    return bool(e) and e.__class__.__name__ == "AiParseError"


def _retry_feedback_message(*, kind: str, purpose: str, prev_err: Exception, last_output: str | None) -> dict[str, str]:
    """
    Build a clipped feedback instruction to improve retries.
    """
    err = _clip(str(prev_err) or "error", 500)
    prev = _clip(str(last_output or ""), 1200)
    k = str(kind or "").strip().lower()
    p = str(purpose or "").strip()
    if k == "json":
        txt = (
            "Your previous attempt did not produce valid JSON for the required schema.\n"
            f"Error: {err}\n"
            "Return ONLY a single JSON object that matches the schema exactly. No markdown, no extra keys."
        )
    else:
        extra_prev = f"\nPrevious output (truncated):\n{prev}" if prev else ""
        txt = (
            "Your previous attempt failed verification.\n"
            f"Error: {err}\n"
            "Fix the output to satisfy the requirement. Return ONLY the corrected final output."
            + extra_prev
        )
    return {"role": "user", "content": f"[RETRY_FEEDBACK purpose={p} kind={k}]\n{txt}".strip()}


def _run_validator(validate: Validator | list[Validator] | None, text: str) -> str | None:
    if validate is None:
        return None
    fns: list[Validator] = validate if isinstance(validate, list) else [validate]
    for fn in fns:
        try:
            msg = fn(text)
        except Exception as e:
            return f"validator_exception: {e}"
        if msg:
            return str(msg)
    return None


def _normalize_messages(messages: list[dict[str, str]], max_chars: int) -> list[dict[str, str]]:
    # Guard against accidentally sending huge prompts (which can time out or explode costs).
    out: list[dict[str, str]] = []
    for m in messages or []:
        role = str(m.get("role") or "user")
        content = _clip(str(m.get("content") or ""), max_chars)
        out.append({"role": role, "content": content})
    return out


def _messages_to_single_input(messages: list[dict[str, str]]) -> str:
    """
    Convert chat-style messages to a single Responses API input string.

    Most callers in this codebase send a single user prompt. When they include a system
    message, we preserve it as a simple transcript prefix.
    """
    msgs = messages or []
    if len(msgs) == 1 and (msgs[0].get("role") or "").strip() == "user":
        return str(msgs[0].get("content") or "")

    parts: list[str] = []
    for m in msgs:
        role = str(m.get("role") or "user").strip().upper()
        content = str(m.get("content") or "")
        parts.append(f"{role}:\n{content}".strip())
    # Give the model a clear "next turn" marker.
    return "\n\n".join(parts) + "\n\nASSISTANT:"


def _extract_first_json_object(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else None


def _normalize_openai_strict_json_schema(schema: Any) -> Any:
    """
    OpenAI structured outputs (`response_format: json_schema` with `strict: true`) are
    stricter than vanilla JSON Schema:
    - objects must include `additionalProperties: false`
    - objects must include `required`, and it must list EVERY key in `properties`

    Pydantic may omit these when fields have defaults, so we enforce them recursively.
    """
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            props = schema.get("properties")
            if isinstance(props, dict) and props:
                schema["required"] = list(props.keys())
            schema["additionalProperties"] = False
        for v in schema.values():
            _normalize_openai_strict_json_schema(v)
    elif isinstance(schema, list):
        for v in schema:
            _normalize_openai_strict_json_schema(v)
    return schema


def _should_retry_with_legacy_max_tokens(e: Exception) -> bool:
    msg = (str(e) or "").lower()
    # Some older models/endpoints only accept `max_tokens`.
    return "unsupported parameter" in msg and "max_completion_tokens" in msg


def _responses_text(resp: Any) -> str:
    """
    Best-effort extraction of output text from a Responses API response object.
    """
    # Newer SDKs provide `output_text` convenience property.
    out = getattr(resp, "output_text", None)
    if isinstance(out, str):
        return out

    # Fallback: walk response.output[*].content[*].text
    try:
        output = getattr(resp, "output", None) or []
        chunks: list[str] = []
        for item in output:
            content = getattr(item, "content", None) or []
            for c in content:
                t = getattr(c, "text", None)
                if isinstance(t, str) and t:
                    chunks.append(t)
        return "\n".join(chunks)
    except Exception:
        return ""


def _responses_create_text(
    *,
    client: Any,
    model: str,
    purpose: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    reasoning_effort: str,
    verbosity: str,
) -> tuple[str, AiMeta]:
    """
    Call the Responses API and return plain text.
    """
    inp = _messages_to_single_input(messages)
    kwargs: dict[str, Any] = {
        "model": model,
        "input": inp,
        "max_output_tokens": int(max_tokens),
        "reasoning": {"effort": reasoning_effort},
        "text": {"verbosity": verbosity},
    }
    # Per GPT-5.2 guidance: temperature/top_p/logprobs are only accepted with effort="none".
    if str(reasoning_effort).strip().lower() == "none":
        kwargs["temperature"] = float(temperature)

    resp = client.responses.create(**kwargs)
    out = _responses_text(resp).strip()
    if not out:
        raise AiParseError("empty_model_response")
    return out, AiMeta(
        purpose=purpose,
        model=model,
        attempts=1,
        used_response_format="responses_text",
        response_id=getattr(resp, "id", None),
    )


def _responses_create_json(
    *,
    client: Any,
    model: str,
    purpose: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    reasoning_effort: str,
    verbosity: str,
    response_model: type[T],
) -> tuple[T, AiMeta]:
    """
    Call the Responses API and parse into a Pydantic model.

    We still parse/validate server-side (do not trust the model).
    """
    inp = _messages_to_single_input(messages)

    schema = response_model.model_json_schema()
    schema = _normalize_openai_strict_json_schema(schema)

    # Responses API structured outputs: text.format
    # (If an upstream model doesn't support this, we'll fall back to Chat Completions.)
    fmt: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": {
            "name": response_model.__name__,
            "schema": schema,
            "strict": True,
        },
    }

    kwargs: dict[str, Any] = {
        "model": model,
        "input": inp,
        "max_output_tokens": int(max_tokens),
        "reasoning": {"effort": reasoning_effort},
        "text": {"verbosity": verbosity, "format": fmt},
    }
    if str(reasoning_effort).strip().lower() == "none":
        kwargs["temperature"] = float(temperature)

    resp = client.responses.create(**kwargs)
    content = _responses_text(resp).strip()
    if not content:
        raise AiParseError("empty_model_response")

    raw_json = content
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
        attempts=1,
        used_response_format="responses_json_schema",
        response_id=getattr(resp, "id", None),
    )


def call_text(
    *,
    purpose: str,
    messages: list[dict[str, str]],
    max_tokens: int = 1200,
    temperature: float = 0.4,
    validate: Validator | list[Validator] | None = None,
    retries: int = 2,
    timeout_s: int = 60,
    max_prompt_chars: int = 220_000,
) -> tuple[str, AiMeta]:
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    _circuit_check()
    # Clamp token output to reduce accidental cost explosions.
    max_tokens = int(min(int(max_tokens), int(settings.openai_max_output_tokens_cap or max_tokens)))
    client = _client(timeout_s=timeout_s)
    messages = _normalize_messages(messages, max_prompt_chars)

    last_err: Exception | None = None
    for model in _models_to_try(purpose):
        prev_err: Exception | None = None
        prev_output: str | None = None
        for attempt in range(1, max(1, int(retries) + 1) + 1):
            attempt_messages = list(messages)
            if attempt >= 2 and _is_parse_failure(prev_err) and prev_err is not None:
                attempt_messages.append(
                    _retry_feedback_message(kind="text", purpose=purpose, prev_err=prev_err, last_output=prev_output)
                )
            # Give retries more room when validation fails (bounded by cap).
            mt = max_tokens
            if attempt >= 2 and _is_parse_failure(prev_err):
                mt = int(min(int(settings.openai_max_output_tokens_cap or mt), int(mt * 1.5)))
            try:
                # Prefer Responses API for GPT-5 family (supports reasoning/verbosity).
                if _is_gpt5_family(model) and _supports_responses_api(client):
                    t = tuning_for(purpose=purpose, kind="text", attempt=attempt, prev_err=prev_err)
                    out, meta = _responses_create_text(
                        client=client,
                        model=model,
                        purpose=purpose,
                        messages=attempt_messages,
                        max_tokens=mt,
                        temperature=temperature,
                        reasoning_effort=t.reasoning_effort,
                        verbosity=t.verbosity,
                    )
                    msg = _run_validator(validate, out)
                    if msg:
                        raise AiParseError(f"validation_failed: {msg}")
                    # Preserve retry semantics: stamp attempt count.
                    _circuit_record_success()
                    try:
                        log.info(
                            "ai_call_ok",
                            purpose=purpose,
                            model=model,
                            attempts=attempt,
                            response_format=meta.used_response_format,
                            response_id=meta.response_id,
                        )
                    except Exception:
                        pass
                    return out, AiMeta(**(meta.__dict__ | {"attempts": attempt}))

                # Fallback: Chat Completions (older models / streaming UX parity).
                try:
                    completion = client.chat.completions.create(
                        model=model,
                        messages=attempt_messages,
                        max_completion_tokens=mt,
                        temperature=temperature,
                    )
                except Exception as e:
                    if _should_retry_with_legacy_max_tokens(e):
                        completion = client.chat.completions.create(
                            model=model,
                            messages=attempt_messages,
                            max_tokens=mt,
                            temperature=temperature,
                        )
                    else:
                        raise
                out = (completion.choices[0].message.content or "").strip()
                if not out:
                    raise AiParseError("empty_model_response")
                msg = _run_validator(validate, out)
                if msg:
                    raise AiParseError(f"validation_failed: {msg}")
                _circuit_record_success()
                try:
                    log.info(
                        "ai_call_ok",
                        purpose=purpose,
                        model=model,
                        attempts=attempt,
                        response_format="chat_text",
                    )
                except Exception:
                    pass
                return out, AiMeta(
                    purpose=purpose, model=model, attempts=attempt, used_response_format="chat_text"
                )
            except Exception as e:
                last_err = e
                prev_err = e
                prev_output = locals().get("out") if isinstance(locals().get("out"), str) else prev_output
                _circuit_record_failure(e)
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
                    status_code=_status_code(e),
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
    validate_parsed: Callable[[T], str | None] | None = None,
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
    _circuit_check()
    max_tokens = int(min(int(max_tokens), int(settings.openai_max_output_tokens_cap or max_tokens)))
    client = _client(timeout_s=timeout_s)
    messages = _normalize_messages(messages, max_prompt_chars)

    schema = response_model.model_json_schema()
    schema = _normalize_openai_strict_json_schema(schema)
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
        prev_err: Exception | None = None
        prev_output: str | None = None
        for attempt in range(1, max(1, int(retries)) + 1):
            attempt_messages = list(messages)
            if attempt >= 2 and _is_parse_failure(prev_err) and prev_err is not None:
                attempt_messages.append(
                    _retry_feedback_message(kind="json", purpose=purpose, prev_err=prev_err, last_output=None)
                )
            # Prefer Responses API for GPT-5 family.
            if _is_gpt5_family(model) and _supports_responses_api(client):
                try:
                    t = tuning_for(purpose=purpose, kind="json", attempt=attempt, prev_err=prev_err)
                    # If we failed to parse/validate previously, allow a bit more room.
                    mt = max_tokens
                    if isinstance(prev_err, AiParseError) and attempt >= 2:
                        mt = int(min(int(settings.openai_max_output_tokens_cap or mt), int(mt * 1.5)))
                    parsed, meta = _responses_create_json(
                        client=client,
                        model=model,
                        purpose=purpose,
                        messages=attempt_messages,
                        max_tokens=mt,
                        temperature=temperature,
                        reasoning_effort=t.reasoning_effort,
                        verbosity=t.verbosity,
                        response_model=response_model,
                    )
                    if validate_parsed is not None:
                        msg = validate_parsed(parsed)
                        if msg:
                            raise AiParseError(f"validation_failed: {msg}")
                    _circuit_record_success()
                    try:
                        log.info(
                            "ai_call_ok",
                            purpose=purpose,
                            model=model,
                            attempts=attempt,
                            response_format=meta.used_response_format,
                            response_id=meta.response_id,
                        )
                    except Exception:
                        pass
                    return parsed, AiMeta(**(meta.__dict__ | {"attempts": attempt}))
                except Exception as e:
                    # If Responses structured outputs aren't supported for the chosen model,
                    # fall through to the Chat Completions path (which we know works for many models).
                    last_err = e
                    prev_err = e
                    last_preview = None
                    prev_output = None
                    log.warning(
                        "ai_json_responses_failed",
                        purpose=purpose,
                        model=model,
                        attempt=attempt,
                        error=str(e),
                        status_code=_status_code(e),
                    )
                    # Continue with chat.completions modes below for this attempt.

            model_hard_failed = False
            for response_format, temp in modes:
                used_rf = (
                    response_format.get("type")
                    if isinstance(response_format, dict)
                    else None
                )
                try:
                    mt = max_tokens
                    if isinstance(prev_err, AiParseError) and attempt >= 2:
                        mt = int(min(int(settings.openai_max_output_tokens_cap or mt), int(mt * 1.5)))
                    kwargs_base: dict[str, Any] = {
                        "model": model,
                        "messages": attempt_messages,
                        "temperature": temp,
                    }
                    if response_format is not None:
                        kwargs_base["response_format"] = response_format

                    try:
                        completion = client.chat.completions.create(
                            **(kwargs_base | {"max_completion_tokens": mt})
                        )
                    except Exception as e:
                        if _should_retry_with_legacy_max_tokens(e):
                            completion = client.chat.completions.create(
                                **(kwargs_base | {"max_tokens": mt})
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

                    if validate_parsed is not None:
                        msg = validate_parsed(parsed)
                        if msg:
                            raise AiParseError(f"validation_failed: {msg}")

                    _circuit_record_success()
                    try:
                        log.info(
                            "ai_call_ok",
                            purpose=purpose,
                            model=model,
                            attempts=attempt,
                            response_format=f"chat_{used_rf or 'none'}",
                        )
                    except Exception:
                        pass
                    return parsed, AiMeta(
                        purpose=purpose,
                        model=model,
                        attempts=attempt,
                        used_response_format=f"chat_{used_rf or 'none'}",
                    )
                except Exception as e:
                    last_err = e
                    prev_err = e
                    _circuit_record_failure(e)
                    last_preview = (locals().get("content") or "")[:240]
                    prev_output = str(locals().get("content") or "") if isinstance(locals().get("content"), str) else prev_output
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
                        status_code=_status_code(e),
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
    _circuit_check()
    max_tokens = int(min(int(max_tokens), int(settings.openai_max_output_tokens_cap or max_tokens)))
    client = _client(timeout_s=timeout_s)
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
            _circuit_record_success()
            return stream, AiMeta(
                purpose=purpose,
                model=model,
                attempts=1,
                used_response_format="stream",
            )
        except Exception as e:
            last_err = e
            _circuit_record_failure(e)
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
