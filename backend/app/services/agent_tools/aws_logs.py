from __future__ import annotations

import time
from typing import Any

from ...settings import settings
from .allowlist import parse_csv, uniq
from .aws_clients import logs_client


def _default_log_groups() -> list[str]:
    env = str(settings.normalized_environment or "").strip() or "production"
    # From CloudFormation templates.
    return [
        f"/ecs/polaris-backend-{env}",
        f"/ecs/polaris-contracting-worker-{env}",
        f"/ecs/northstar-ambient-{env}",
        f"/ecs/northstar-job-runner-{env}",
        f"/ecs/northstar-daily-report-{env}",
    ]


def _allowed_log_groups() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_log_groups))
    if explicit:
        return explicit
    return uniq(_default_log_groups())


def _require_allowed_log_group(name: str) -> str:
    lg = str(name or "").strip()
    if not lg:
        raise ValueError("missing_logGroupName")
    allowed = _allowed_log_groups()
    if allowed and lg not in allowed:
        raise ValueError("log_group_not_allowed")
    return lg


def tail_log_group(
    *,
    log_group_name: str,
    lookback_minutes: int = 15,
    limit: int = 50,
) -> dict[str, Any]:
    lg = _require_allowed_log_group(log_group_name)
    lb = max(1, min(180, int(lookback_minutes or 15)))
    lim = max(1, min(200, int(limit or 50)))
    start_ms = int((time.time() - (lb * 60)) * 1000)
    resp = logs_client().filter_log_events(
        logGroupName=lg,
        startTime=start_ms,
        limit=lim,
    )
    evs = resp.get("events") if isinstance(resp, dict) else None
    rows = evs if isinstance(evs, list) else []
    out: list[dict[str, Any]] = []
    for e in rows[:lim]:
        if not isinstance(e, dict):
            continue
        msg = str(e.get("message") or "")
        out.append(
            {
                "timestamp": int(e.get("timestamp") or 0) or None,
                "ingestionTime": int(e.get("ingestionTime") or 0) or None,
                "message": (msg[:1800] + "…") if len(msg) > 1800 else msg,
            }
        )
    return {"ok": True, "logGroupName": lg, "lookbackMinutes": lb, "events": out}

