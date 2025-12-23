from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, TypeVar

from ...observability.logging import get_logger

log = get_logger("agent_resilience")

T = TypeVar("T")


class ErrorCategory(Enum):
    """Error categories for classification."""
    TRANSIENT = "transient"  # Temporary failures that should retry
    PERMANENT = "permanent"  # Permanent failures that shouldn't retry
    RATE_LIMIT = "rate_limit"  # Rate limiting - needs backoff
    TIMEOUT = "timeout"  # Timeout - may need longer timeout
    RESOURCE = "resource"  # Resource exhaustion - may need simpler operation
    NETWORK = "network"  # Network issues - should retry
    AUTH = "auth"  # Authentication/authorization - permanent without fix
    VALIDATION = "validation"  # Validation error - permanent without fix


@dataclass
class ErrorClassification:
    """Classification of an error."""
    category: ErrorCategory
    retryable: bool
    should_degrade: bool  # Should we try simpler operation?
    backoff_multiplier: float  # Multiplier for backoff (1.0 = normal, 2.0 = double, etc.)
    max_retries: int  # Maximum retries for this error type


def classify_error(exc: Exception) -> ErrorClassification:
    """
    Classify an error to determine retry strategy.
    """
    exc_str = str(exc).lower()
    
    # Rate limiting
    if "rate limit" in exc_str or "429" in exc_str or "too many requests" in exc_str:
        return ErrorClassification(
            category=ErrorCategory.RATE_LIMIT,
            retryable=True,
            should_degrade=False,
            backoff_multiplier=2.0,
            max_retries=5,
        )
    
    # Timeout
    if "timeout" in exc_str or "timed out" in exc_str or "408" in exc_str:
        return ErrorClassification(
            category=ErrorCategory.TIMEOUT,
            retryable=True,
            should_degrade=True,
            backoff_multiplier=1.5,
            max_retries=3,
        )
    
    # Network issues
    if any(k in exc_str for k in ("connection", "network", "dns", "502", "503", "504")):
        return ErrorClassification(
            category=ErrorCategory.NETWORK,
            retryable=True,
            should_degrade=False,
            backoff_multiplier=1.5,
            max_retries=3,
        )
    
    # Authentication/authorization
    if any(k in exc_str for k in ("auth", "unauthorized", "forbidden", "401", "403")):
        return ErrorClassification(
            category=ErrorCategory.AUTH,
            retryable=False,
            should_degrade=False,
            backoff_multiplier=1.0,
            max_retries=0,
        )
    
    # Validation errors
    if any(k in exc_str for k in ("validation", "invalid", "bad request", "400")):
        return ErrorClassification(
            category=ErrorCategory.VALIDATION,
            retryable=False,
            should_degrade=False,
            backoff_multiplier=1.0,
            max_retries=0,
        )
    
    # Resource exhaustion
    if any(k in exc_str for k in ("resource", "quota", "limit exceeded", "507")):
        return ErrorClassification(
            category=ErrorCategory.RESOURCE,
            retryable=True,
            should_degrade=True,
            backoff_multiplier=2.0,
            max_retries=2,
        )
    
    # Default: transient (retryable)
    return ErrorClassification(
        category=ErrorCategory.TRANSIENT,
        retryable=True,
        should_degrade=False,
        backoff_multiplier=1.0,
        max_retries=3,
    )


def exponential_backoff_with_jitter(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    multiplier: float = 2.0,
    jitter: float = 0.1,
) -> float:
    """
    Calculate exponential backoff delay with jitter.
    
    Args:
        attempt: Current attempt number (1-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        multiplier: Exponential multiplier
        jitter: Jitter factor (0.0 to 1.0)
    
    Returns:
        Delay in seconds
    """
    delay = base_delay * (multiplier ** (attempt - 1))
    delay = min(delay, max_delay)
    
    # Add jitter (±jitter%)
    jitter_amount = delay * jitter * (2 * random.random() - 1)
    delay = delay + jitter_amount
    
    return max(0.0, delay)


def retry_with_classification(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    on_retry: Callable[[Exception, int], None] | None = None,
    should_retry: Callable[[Exception], bool] | None = None,
) -> T:
    """
    Retry a function with error classification and adaptive backoff.
    
    Args:
        fn: Function to retry
        max_retries: Maximum number of retries
        base_delay: Base delay for backoff
        max_delay: Maximum delay
        on_retry: Callback called on each retry
        should_retry: Custom retry predicate (overrides classification)
    
    Returns:
        Result of function call
    
    Raises:
        Last exception if all retries fail
    """
    last_exc: Exception | None = None
    
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            
            # Check custom retry predicate
            if should_retry and not should_retry(e):
                raise
            
            # Classify error
            classification = classify_error(e)
            
            # Check if retryable
            if not classification.retryable:
                raise
            
            # Check if we've exceeded max retries for this error type
            if attempt >= classification.max_retries:
                raise
            
            # Calculate backoff
            delay = exponential_backoff_with_jitter(
                attempt=attempt,
                base_delay=base_delay,
                max_delay=max_delay,
                multiplier=classification.backoff_multiplier,
            )
            
            # Call retry callback
            if on_retry:
                try:
                    on_retry(e, attempt)
                except Exception:
                    pass
            
            # Log retry
            log.warning(
                "agent_resilience_retry",
                attempt=attempt,
                max_retries=max_retries,
                error_type=type(e).__name__,
                error=str(e)[:200],
                category=classification.category.value,
                delay=delay,
            )
            
            # Sleep before retry
            time.sleep(delay)
    
    # All retries exhausted
    if last_exc:
        raise last_exc
    raise RuntimeError("retry_with_classification: no exception but retries exhausted")


def graceful_degradation(
    primary_fn: Callable[[], T],
    fallback_fn: Callable[[], T],
    *,
    max_retries: int = 2,
) -> T:
    """
    Try primary function, fall back to simpler function on failure.
    
    Args:
        primary_fn: Primary function to try
        fallback_fn: Fallback function (simpler operation)
        max_retries: Maximum retries for primary before falling back
    
    Returns:
        Result from primary or fallback
    """
    try:
        return retry_with_classification(
            primary_fn,
            max_retries=max_retries,
        )
    except Exception as e:
        classification = classify_error(e)
        
        # Only degrade if error suggests it would help
        if classification.should_degrade:
            log.info(
                "agent_resilience_degrading",
                error_type=type(e).__name__,
                error=str(e)[:200],
                category=classification.category.value,
            )
            try:
                return fallback_fn()
            except Exception as fallback_exc:
                # If fallback also fails, raise original error
                log.warning(
                    "agent_resilience_fallback_failed",
                    original_error=str(e)[:200],
                    fallback_error=str(fallback_exc)[:200],
                )
                raise e from fallback_exc
        
        # Don't degrade, raise original error
        raise


def partial_success_handler(
    results: list[dict[str, Any]],
    *,
    min_success_count: int = 1,
    continue_on_partial: bool = True,
) -> dict[str, Any]:
    """
    Handle partial success scenarios.
    
    Args:
        results: List of result dicts with 'ok' field
        min_success_count: Minimum number of successes required
        continue_on_partial: Whether to continue with partial results
    
    Returns:
        Combined result dict
    """
    successes = [r for r in results if isinstance(r, dict) and r.get("ok") is True]
    failures = [r for r in results if isinstance(r, dict) and r.get("ok") is False]
    
    if len(successes) >= min_success_count:
        if continue_on_partial:
            return {
                "ok": True,
                "partial": len(failures) > 0,
                "successCount": len(successes),
                "failureCount": len(failures),
                "results": results,
            }
        else:
            return {
                "ok": True,
                "results": successes,
            }
    
    # Not enough successes
    return {
        "ok": False,
        "error": "insufficient_successes",
        "successCount": len(successes),
        "failureCount": len(failures),
        "results": results,
    }


def adaptive_timeout(
    base_timeout: float,
    *,
    complexity_score: float = 1.0,
    previous_failures: int = 0,
    min_timeout: float = 10.0,
    max_timeout: float = 300.0,
) -> float:
    """
    Calculate adaptive timeout based on operation complexity and history.
    
    Args:
        base_timeout: Base timeout in seconds
        complexity_score: Complexity multiplier (1.0 = normal, 2.0 = double time)
        previous_failures: Number of previous timeout failures
        min_timeout: Minimum timeout
        max_timeout: Maximum timeout
    
    Returns:
        Adaptive timeout in seconds
    """
    timeout = base_timeout * complexity_score
    
    # Increase timeout if we've had previous failures
    if previous_failures > 0:
        timeout = timeout * (1.0 + (previous_failures * 0.5))
    
    # Apply bounds
    timeout = max(min_timeout, min(timeout, max_timeout))
    
    return timeout


def should_retry_with_adjusted_params(
    exc: Exception,
    attempt: int,
    *,
    max_adjustments: int = 2,
) -> tuple[bool, dict[str, Any]]:
    """
    Determine if we should retry with adjusted parameters (e.g., lower reasoning, simpler query).
    
    Returns:
        Tuple of (should_retry, adjusted_params)
    """
    if attempt > max_adjustments:
        return False, {}
    
    classification = classify_error(exc)
    
    if not classification.should_degrade:
        return False, {}
    
    adjusted: dict[str, Any] = {}
    
    # Adjust reasoning effort downward
    if attempt == 1:
        adjusted["reasoning_effort"] = "medium"  # Down from high
    elif attempt == 2:
        adjusted["reasoning_effort"] = "low"  # Down from medium
    
    # Reduce max steps
    adjusted["max_steps"] = max(3, 10 - (attempt * 2))
    
    # Reduce max tokens
    adjusted["max_tokens"] = max(500, 2000 - (attempt * 500))
    
    return True, adjusted


def adaptive_retry_with_alternatives(
    primary_fn: Callable[[], T],
    alternatives: list[Callable[[], T]],
    context: dict[str, Any] | None = None,
    *,
    max_retries: int = 3,
) -> T:
    """
    Try primary function, then try alternatives if primary fails.
    Learn from which alternative succeeds.
    
    Args:
        primary_fn: Primary function to try first
        alternatives: List of alternative functions to try if primary fails
        context: Optional context dict for logging/learning
        max_retries: Maximum retries for primary before trying alternatives
    
    Returns:
        Result from primary or first successful alternative
    
    Raises:
        Last exception if all attempts fail
    """
    last_exc: Exception | None = None
    
    # Try primary with retries
    try:
        return retry_with_classification(
            primary_fn,
            max_retries=max_retries,
        )
    except Exception as e:
        last_exc = e
        classification = classify_error(e)
        
        # Only try alternatives if error suggests it would help
        if not classification.retryable:
            # Try alternatives for non-retryable errors
            pass
        else:
            # For retryable errors, only try alternatives if we've exhausted retries
            # (retry_with_classification already did retries)
            pass
    
    # Try alternatives
    for i, alt_fn in enumerate(alternatives):
        try:
            result = alt_fn()
            log.info(
                "adaptive_retry_alternative_succeeded",
                alternative_index=i,
                context=context,
            )
            # TODO: Store success pattern in memory for learning
            return result
        except Exception as alt_exc:
            last_exc = alt_exc
            log.warning(
                "adaptive_retry_alternative_failed",
                alternative_index=i,
                error=str(alt_exc)[:200],
            )
            continue
    
    # All attempts failed
    if last_exc:
        raise last_exc
    raise RuntimeError("adaptive_retry_with_alternatives: all attempts failed")


def analyze_failure_and_recover(
    error: Exception,
    context: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """
    Analyze failure, determine recovery strategy, execute recovery.
    Store analysis for future learning.
    
    Args:
        error: The exception that occurred
        context: Context about the failure (step, tool, args, etc.)
        job_id: Job ID for tracking
    
    Returns:
        Dict with recovery result
    """
    classification = classify_error(error)
    
    recovery_strategies: list[str] = []
    
    # Determine recovery strategies based on error type
    if classification.category == ErrorCategory.RATE_LIMIT:
        recovery_strategies.append("wait_and_retry")
    elif classification.category == ErrorCategory.NETWORK:
        recovery_strategies.append("retry_with_backoff")
    elif classification.category == ErrorCategory.RESOURCE:
        recovery_strategies.append("simplify_operation")
    elif classification.category == ErrorCategory.VALIDATION:
        recovery_strategies.append("refine_approach")
    
    log.info(
        "failure_analysis",
        job_id=job_id,
        error_category=classification.category.value,
        error=str(error)[:200],
        recovery_strategies=recovery_strategies,
        context_keys=list(context.keys())[:10],
    )
    
    # TODO: Store failure analysis in memory for learning
    # TODO: Execute automatic recovery based on strategies
    
    return {
        "analyzed": True,
        "error_category": classification.category.value,
        "retryable": classification.retryable,
        "recovery_strategies": recovery_strategies,
        "recovered": False,  # Placeholder - actual recovery not implemented yet
    }
