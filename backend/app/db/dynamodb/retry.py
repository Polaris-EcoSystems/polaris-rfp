from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from botocore.exceptions import BotoCoreError, ClientError

from .errors import (
    DdbConflict,
    DdbError,
    DdbInternal,
    DdbThrottled,
    DdbUnavailable,
    DdbValidation,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 6
    base_delay_s: float = 0.05
    max_delay_s: float = 1.5


_RETRYABLE_CODES = {
    "ProvisionedThroughputExceededException",
    "ThrottlingException",
    "RequestLimitExceeded",
    "InternalServerError",
    "ServiceUnavailable",
    # Can be returned directly by TransactWriteItems under contention.
    "TransactionConflictException",
}

# Transaction-specific retryable cancellation reasons / codes.
_TRANSACTION_RETRYABLE_CODES = {
    "TransactionConflictException",
}


def _sleep_backoff(policy: RetryPolicy, attempt: int) -> None:
    # Full jitter exponential backoff.
    cap = policy.max_delay_s
    base = policy.base_delay_s
    exp = min(cap, base * (2 ** max(0, attempt - 1)))
    time.sleep(random.random() * exp)


def _aws_request_id_from_client_error(e: ClientError) -> str | None:
    try:
        return (e.response or {}).get("ResponseMetadata", {}).get("RequestId")
    except Exception:
        return None


def _err_code_from_client_error(e: ClientError) -> str | None:
    try:
        return (e.response or {}).get("Error", {}).get("Code")
    except Exception:
        return None


def _is_retryable_client_error(e: ClientError) -> bool:
    code = _err_code_from_client_error(e) or ""

    if code in _RETRYABLE_CODES:
        return True

    # TransactWriteItems may raise TransactionCanceledException with structured reasons.
    if code == "TransactionCanceledException":
        try:
            reasons = (e.response or {}).get("CancellationReasons") or []
            for r in reasons:
                rc = (r or {}).get("Code")
                if rc in _TRANSACTION_RETRYABLE_CODES:
                    return True
        except Exception:
            return False

    return False


def _map_botocore_error(
    *,
    operation: str,
    table_name: str | None,
    key: dict[str, Any] | None,
    exc: Exception,
) -> DdbError:
    if isinstance(exc, DdbError):
        return exc

    if isinstance(exc, ClientError):
        code = _err_code_from_client_error(exc) or ""
        aws_request_id = _aws_request_id_from_client_error(exc)

        if code == "ConditionalCheckFailedException":
            return DdbConflict(
                message="DynamoDB conditional check failed",
                operation=operation,
                table_name=table_name,
                key=key,
                aws_request_id=aws_request_id,
                retryable=False,
                cause=exc,
            )

        if code in ("ValidationException", "ParamValidationError"):
            return DdbValidation(
                message="DynamoDB request validation failed",
                operation=operation,
                table_name=table_name,
                key=key,
                aws_request_id=aws_request_id,
                retryable=False,
                cause=exc,
            )

        if code in ("AccessDeniedException", "UnrecognizedClientException"):
            return DdbUnavailable(
                message="DynamoDB access denied",
                operation=operation,
                table_name=table_name,
                key=key,
                aws_request_id=aws_request_id,
                retryable=False,
                cause=exc,
            )

        if code in _RETRYABLE_CODES or _is_retryable_client_error(exc):
            return DdbThrottled(
                message="DynamoDB request throttled or unavailable",
                operation=operation,
                table_name=table_name,
                key=key,
                aws_request_id=aws_request_id,
                retryable=True,
                cause=exc,
            )

        return DdbInternal(
            message=f"DynamoDB request failed ({code or 'ClientError'})",
            operation=operation,
            table_name=table_name,
            key=key,
            aws_request_id=aws_request_id,
            retryable=False,
            cause=exc,
        )

    if isinstance(exc, BotoCoreError):
        return DdbUnavailable(
            message="DynamoDB client error",
            operation=operation,
            table_name=table_name,
            key=key,
            retryable=True,
            cause=exc,
        )

    return DdbInternal(
        message="Unexpected DynamoDB error",
        operation=operation,
        table_name=table_name,
        key=key,
        retryable=False,
        cause=exc,
    )


def ddb_call(
    operation: str,
    fn: Callable[[], T],
    *,
    table_name: str | None = None,
    key: dict[str, Any] | None = None,
    retry_policy: RetryPolicy | None = None,
) -> T:
    policy = retry_policy or RetryPolicy()

    last_exc: Exception | None = None
    for attempt in range(1, max(1, int(policy.max_attempts)) + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            mapped = _map_botocore_error(
                operation=operation,
                table_name=table_name,
                key=key,
                exc=e,
            )
            last_exc = mapped

            # Never retry validation/conflict errors.
            if not getattr(mapped, "retryable", False):
                raise mapped

            if attempt >= policy.max_attempts:
                raise mapped

            _sleep_backoff(policy, attempt)

    # Defensive fallback.
    if isinstance(last_exc, DdbError):
        raise last_exc
    raise DdbInternal(message="DynamoDB request failed", operation=operation, table_name=table_name, key=key)

