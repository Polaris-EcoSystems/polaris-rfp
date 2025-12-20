from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.errors import DdbConflict
from ..db.dynamodb.table import get_main_table


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def job_key(*, job_id: str) -> dict[str, str]:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id is required")
    return {"pk": f"AGENTJOB#{jid}", "sk": "PROFILE"}


def _due_index(*, due_at: str, job_id: str) -> dict[str, str]:
    # Uses existing GSI1 (pattern already used widely in the app).
    due = str(due_at or "").strip()
    jid = str(job_id or "").strip()
    return {"gsi1pk": "AGENTJOB_DUE", "gsi1sk": f"{due}#{jid}"}


def normalize_job(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "entityType", "gsi1pk", "gsi1sk"):
        out.pop(k, None)
    out["_id"] = str(out.get("jobId") or "").strip() or None
    return out


def create_job(
    *,
    job_type: str,
    scope: dict[str, Any],
    due_at: str,
    payload: dict[str, Any] | None = None,
    requested_by_user_sub: str | None = None,
) -> dict[str, Any]:
    """
    Create a scheduled job.

    Notes:
    - For now, we support one-shot jobs via `due_at` ISO time.
    - Cron-style jobs can be represented via payload fields (future) but are not
      computed here to avoid new deps; use external scheduler to enqueue as needed.
    """
    jid = "aj_" + uuid.uuid4().hex[:18]
    now = _now_iso()
    due = str(due_at or "").strip()
    if not due:
        raise ValueError("due_at is required")

    item: dict[str, Any] = {
        **job_key(job_id=jid),
        "entityType": "AgentJob",
        "jobId": jid,
        "jobType": str(job_type or "").strip() or "unknown",
        "status": "queued",
        "scope": scope if isinstance(scope, dict) else {},
        "payload": payload if isinstance(payload, dict) else {},
        "dueAt": due,
        "createdAt": now,
        "updatedAt": now,
        "requestedByUserSub": str(requested_by_user_sub).strip() if requested_by_user_sub else None,
        **_due_index(due_at=due, job_id=jid),
    }
    item = {k: v for k, v in item.items() if v is not None}
    try:
        get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    except DdbConflict:
        # Extremely unlikely; just retry once.
        return create_job(
            job_type=job_type,
            scope=scope,
            due_at=due_at,
            payload=payload,
            requested_by_user_sub=requested_by_user_sub,
        )
    return normalize_job(item) or {}


def get_job(*, job_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=job_key(job_id=job_id))
    return normalize_job(it)


def claim_due_jobs(*, now_iso: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    """
    Query due jobs (queued) up to the provided now timestamp.
    This does NOT mark them running; callers should transition status themselves.
    """
    now = str(now_iso or _now_iso()).strip()
    # lte works lexicographically for ISO timestamps.
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq("AGENTJOB_DUE") & Key("gsi1sk").lte(f"{now}#~"),
        scan_index_forward=True,
        limit=max(1, min(100, int(limit or 25))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_job(it)
        if not norm:
            continue
        if str(norm.get("status") or "").strip().lower() != "queued":
            continue
        out.append(norm)
    return out


def try_mark_running(*, job_id: str) -> dict[str, Any] | None:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id is required")
    now = _now_iso()
    updated = get_main_table().update_item(
        key=job_key(job_id=jid),
        update_expression="SET #s = :r, startedAt = :st, updatedAt = :u",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={":r": "running", ":st": now, ":u": now, ":q": "queued"},
        condition_expression="#s = :q",
        return_values="ALL_NEW",
    )
    return normalize_job(updated) if updated else None


def complete_job(*, job_id: str, result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    jid = str(job_id or "").strip()
    now = _now_iso()
    updated = get_main_table().update_item(
        key=job_key(job_id=jid),
        update_expression="SET #s = :s, finishedAt = :f, updatedAt = :u, result = :r",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={":s": "completed", ":f": now, ":u": now, ":r": result if isinstance(result, dict) else {}},
        return_values="ALL_NEW",
    )
    return normalize_job(updated)


def fail_job(*, job_id: str, error: str) -> dict[str, Any] | None:
    jid = str(job_id or "").strip()
    now = _now_iso()
    err = (str(error or "").strip() or "failed")[:900]
    updated = get_main_table().update_item(
        key=job_key(job_id=jid),
        update_expression="SET #s = :s, finishedAt = :f, updatedAt = :u, error = :e",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={":s": "failed", ":f": now, ":u": now, ":e": err},
        return_values="ALL_NEW",
    )
    return normalize_job(updated)

