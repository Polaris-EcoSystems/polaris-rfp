from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TraceViolation:
    code: str
    message: str
    step_index: int | None = None


def replay_tool_call_trace(
    *,
    records: Iterable[dict[str, Any]],
    allowed_tools: set[str],
    max_steps: int = 50,
) -> dict[str, Any]:
    """
    Offline validator for an agent tool-call trace.

    This is intentionally conservative: it checks structural invariants and safety
    constraints that should *always* hold, independent of model quality.
    """
    viols: list[TraceViolation] = []
    steps = 0
    for idx, r in enumerate(records):
        if steps >= max_steps:
            viols.append(TraceViolation(code="too_many_steps", message="trace exceeds max_steps", step_index=idx))
            break
        steps += 1
        if not isinstance(r, dict):
            viols.append(TraceViolation(code="invalid_record", message="record must be an object", step_index=idx))
            continue
        tool = str(r.get("tool") or r.get("name") or "").strip()
        if not tool:
            viols.append(TraceViolation(code="missing_tool", message="missing tool name", step_index=idx))
            continue
        if tool not in allowed_tools:
            viols.append(TraceViolation(code="tool_not_allowed", message=f"tool {tool!r} not in allowlist", step_index=idx))
        dur = r.get("durationMs")
        try:
            d = int(dur) if dur is not None else 0
        except Exception:
            d = -1
        if d < 0:
            viols.append(TraceViolation(code="invalid_duration", message="durationMs must be >= 0", step_index=idx))
        if d > 180_000:
            viols.append(TraceViolation(code="slow_step", message="durationMs unusually high", step_index=idx))

        # argsKeys is the stable redacted input surface we want for auditability
        args_keys = r.get("argsKeys")
        if args_keys is not None:
            if not isinstance(args_keys, list):
                viols.append(TraceViolation(code="invalid_args_keys", message="argsKeys must be a list", step_index=idx))
            elif len(args_keys) > 80:
                viols.append(TraceViolation(code="too_many_args_keys", message="argsKeys too large", step_index=idx))

    return {
        "ok": len(viols) == 0,
        "steps": steps,
        "violations": [v.__dict__ for v in viols],
    }

