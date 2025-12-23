from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ....repositories.agent.events_repo import list_recent_events_global
from ....observability.logging import get_logger

log = get_logger("agent_telemetry")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def track_agent_operation(
    *,
    operation_type: str,
    purpose: str,
    duration_ms: int,
    steps: int | None = None,
    success: bool = True,
    error: str | None = None,
    reasoning_effort: str | None = None,
    context_length: int | None = None,
    tool_count: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Track agent operation metrics for observability.
    
    Args:
        operation_type: Type of operation (e.g., "slack_agent", "slack_operator", "long_running_job")
        purpose: AI purpose string
        duration_ms: Operation duration in milliseconds
        steps: Number of steps taken
        success: Whether operation succeeded
        error: Error message if failed
        reasoning_effort: Reasoning effort used
        context_length: Context length in characters
        tool_count: Number of tools called
        metadata: Additional metadata
    """
    try:
        payload: dict[str, Any] = {
            "operationType": operation_type,
            "purpose": purpose,
            "durationMs": duration_ms,
            "success": success,
        }
        
        if steps is not None:
            payload["steps"] = steps
        if error:
            payload["error"] = str(error)[:500]
        if reasoning_effort:
            payload["reasoningEffort"] = reasoning_effort
        if context_length is not None:
            payload["contextLength"] = context_length
        if tool_count is not None:
            payload["toolCount"] = tool_count
        if metadata:
            payload["metadata"] = metadata
        
        log.info(
            "agent_operation_telemetry",
            operation_type=operation_type,
            purpose=purpose,
            duration_ms=duration_ms,
            steps=steps,
            success=success,
            reasoning_effort=reasoning_effort,
        )
    except Exception:
        # Never fail on telemetry
        pass


def get_agent_metrics(
    *,
    since_iso: str,
    operation_type: str | None = None,
) -> dict[str, Any]:
    """
    Get aggregated agent metrics for a time period.
    
    Args:
        since_iso: ISO timestamp to query from
        operation_type: Filter by operation type (optional)
    
    Returns:
        Dict with aggregated metrics
    """
    try:
        events = list_recent_events_global(since_iso=since_iso, limit=1000)
        
        # Filter by operation type if specified
        if operation_type:
            events = [
                e for e in events
                if isinstance(e, dict) and str(e.get("type") or "").strip() == "agent_completion"
                and str(e.get("tool") or "").strip() == operation_type
            ]
        else:
            events = [
                e for e in events
                if isinstance(e, dict) and str(e.get("type") or "").strip() == "agent_completion"
            ]
        
        if not events:
            return {
                "count": 0,
                "avg_duration_ms": 0,
                "avg_steps": 0,
                "success_rate": 0.0,
            }
        
        durations: list[int] = []
        steps_list: list[int] = []
        successes = 0
        
        for event in events:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            
            dur = payload.get("durationMs")
            if isinstance(dur, (int, float)):
                durations.append(int(dur))
            
            step = payload.get("steps")
            if isinstance(step, int):
                steps_list.append(step)
            
            if payload.get("success") is True:
                successes += 1
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        avg_steps = sum(steps_list) / len(steps_list) if steps_list else 0
        success_rate = successes / len(events) if events else 0.0
        
        return {
            "count": len(events),
            "avg_duration_ms": int(avg_duration),
            "avg_steps": int(avg_steps),
            "success_rate": success_rate,
            "p50_duration_ms": sorted(durations)[len(durations) // 2] if durations else 0,
            "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)] if durations else 0,
            "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)] if durations else 0,
        }
    except Exception:
        return {
            "count": 0,
            "avg_duration_ms": 0,
            "avg_steps": 0,
            "success_rate": 0.0,
        }


def track_token_usage(
    *,
    purpose: str,
    model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> None:
    """
    Track token usage for cost monitoring.
    
    Args:
        purpose: AI purpose string
        model: Model used
        input_tokens: Input tokens consumed
        output_tokens: Output tokens generated
        reasoning_tokens: Reasoning tokens (if applicable)
    """
    try:
        total_tokens = (input_tokens or 0) + (output_tokens or 0) + (reasoning_tokens or 0)
        
        log.info(
            "agent_token_usage",
            purpose=purpose,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
        )
    except Exception:
        pass


def track_error_pattern(
    *,
    error_type: str,
    error_category: str,
    operation_type: str,
    retryable: bool,
    context: dict[str, Any] | None = None,
) -> None:
    """
    Track error patterns for analysis and improvement.
    
    Args:
        error_type: Type of error (exception class name)
        error_category: Error category from classification
        operation_type: Type of operation that failed
        retryable: Whether error is retryable
        context: Additional context about the error
    """
    try:
        log.warning(
            "agent_error_pattern",
            error_type=error_type,
            error_category=error_category,
            operation_type=operation_type,
            retryable=retryable,
            context=context,
        )
    except Exception:
        pass
