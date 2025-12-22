from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ...registry.aws_clients import logs_client
from .aws_logs import _allowed_log_groups, _require_allowed_log_group


def _parse_iso(s: str) -> int:
    # Return epoch seconds. Accepts Z-terminated ISO.
    raw = str(s or "").strip()
    if not raw:
        raise ValueError("missing_iso")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    return int(dt.astimezone(timezone.utc).timestamp())


def _now_s() -> int:
    return int(time.time())


def search_logs(
    *,
    query: str,
    log_group_names: list[str] | None = None,
    since_iso: str | None = None,
    until_iso: str | None = None,
    limit: int = 50,
    timeout_s: int = 15,
) -> dict[str, Any]:
    """
    Run a bounded CloudWatch Logs Insights query.
    """
    q = str(query or "").strip()
    if not q:
        raise ValueError("missing_query")
    lim = max(1, min(200, int(limit or 50)))
    to_s = _parse_iso(until_iso) if until_iso else _now_s()
    from_s = _parse_iso(since_iso) if since_iso else max(0, to_s - 3600)
    # Hard cap window to prevent expensive queries.
    if to_s - from_s > 6 * 3600:
        from_s = to_s - 6 * 3600

    groups = log_group_names if isinstance(log_group_names, list) and log_group_names else _allowed_log_groups()
    groups2 = [_require_allowed_log_group(g) for g in groups[:5]]

    resp = logs_client().start_query(
        logGroupNames=groups2,
        startTime=int(from_s),
        endTime=int(to_s),
        queryString=q,
        limit=lim,
    )
    qid = str((resp or {}).get("queryId") or "").strip()
    if not qid:
        return {"ok": False, "error": "missing_query_id"}

    deadline = time.time() + max(3, min(30, int(timeout_s or 15)))
    status = "Running"
    results: list[Any] = []
    while time.time() < deadline:
        out = logs_client().get_query_results(queryId=qid)
        status = str((out or {}).get("status") or "").strip() or status
        if status in ("Complete", "Failed", "Cancelled", "Timeout"):
            raw_results = out.get("results") if isinstance(out, dict) else None
            results = raw_results if isinstance(raw_results, list) else []
            break
        time.sleep(0.6)

    rows: list[dict[str, Any]] = []
    for r in results[:lim]:
        if not isinstance(r, list):
            continue
        row: dict[str, Any] = {}
        for cell in r:
            if not isinstance(cell, dict):
                continue
            k = str(cell.get("field") or "").strip()
            v = cell.get("value")
            if k:
                row[k] = v
        rows.append(row)

    return {
        "ok": status == "Complete",
        "status": status,
        "queryId": qid,
        "logGroups": groups2,
        "window": {"since": from_s, "until": to_s},
        "rows": rows[:lim],
    }


def top_errors(
    *,
    log_group_name: str,
    lookback_minutes: int = 60,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Simple 'top error signatures' using Logs Insights.
    """
    lg = _require_allowed_log_group(log_group_name)
    lb = max(5, min(360, int(lookback_minutes or 60)))
    lim = max(1, min(25, int(limit or 10)))
    until_s = _now_s()
    since_s = max(0, until_s - (lb * 60))
    # A lightweight query that works across most structured logs.
    q = (
        "fields @timestamp, @message "
        "| filter @message like /ERROR|Error|Exception/ "
        "| stats count() as n by substr(@message, 0, 120) as sig "
        "| sort n desc "
        f"| limit {lim}"
    )
    return search_logs(query=q, log_group_names=[lg], since_iso=datetime.fromtimestamp(since_s, tz=timezone.utc).isoformat().replace("+00:00", "Z"), until_iso=datetime.fromtimestamp(until_s, tz=timezone.utc).isoformat().replace("+00:00", "Z"), limit=lim, timeout_s=15)

