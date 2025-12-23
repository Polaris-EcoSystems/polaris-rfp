from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.errors import DdbConflict
from ..db.dynamodb.table import get_main_table

ContractingJobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_job_id(prefix: str = "contract_job") -> str:
    return f"{prefix}_{uuid.uuid4()}"


def job_key(job_id: str) -> dict[str, str]:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id is required")
    return {"pk": f"JOB#{jid}", "sk": "PROFILE"}


def idempotency_key_key(idempotency_key: str) -> dict[str, str]:
    k = str(idempotency_key or "").strip()
    if not k:
        raise ValueError("idempotency_key is required")
    # Avoid gigantic keys in pk; normalize by hashing.
    h = hashlib.sha256(k.encode("utf-8")).hexdigest()
    return {"pk": f"IDEMPOTENCY#{h}", "sk": "PROFILE"}


def case_jobs_gsi_pk(case_id: str) -> str:
    cid = str(case_id or "").strip()
    if not cid:
        raise ValueError("case_id is required")
    return f"CASE_JOBS#{cid}"


def normalize_job_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    obj = dict(item)
    obj["jobId"] = obj.get("jobId") or ""
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "idempotencyKeyHash"):
        obj.pop(k, None)
    return obj


def get_job_item(job_id: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key=job_key(job_id))


def get_job(job_id: str) -> dict[str, Any] | None:
    return normalize_job_for_api(get_job_item(job_id))


def list_jobs_for_case(*, case_id: str, limit: int = 50, next_token: str | None = None) -> dict[str, Any]:
    cid = str(case_id or "").strip()
    if not cid:
        return {"data": [], "nextToken": None}
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(case_jobs_gsi_pk(cid)),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=next_token,
    )
    out = [normalize_job_for_api(it) for it in pg.items or []]
    return {"data": [x for x in out if x], "nextToken": pg.next_token}


def _job_case_index_item(*, job_id: str, created_at: str, case_id: str) -> dict[str, Any]:
    return {"gsi1pk": case_jobs_gsi_pk(case_id), "gsi1sk": f"{created_at}#{job_id}"}


def create_job(
    *,
    idempotency_key: str,
    job_type: str,
    case_id: str,
    proposal_id: str | None,
    requested_by_user_sub: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a job with idempotency.\n
    - If idempotency key is new: create job + map idempotency->job atomically.\n
    - If idempotency key exists: return the existing job.\n
    """
    idem = str(idempotency_key or "").strip()
    if not idem:
        raise ValueError("idempotencyKey is required")
    cid = str(case_id or "").strip()
    if not cid:
        raise ValueError("caseId is required")

    t = get_main_table()

    # Fast path: if mapping exists, return existing job.
    existing_map = t.get_item(key=idempotency_key_key(idem))
    if existing_map and isinstance(existing_map.get("jobId"), str) and existing_map.get("jobId"):
        return get_job(existing_map["jobId"]) or {}

    jid = new_job_id("contracting_job")
    created_at = now_iso()
    job_item: dict[str, Any] = {
        **job_key(jid),
        "entityType": "CONTRACTING_JOB",
        "jobId": jid,
        "jobType": str(job_type or "unknown").strip() or "unknown",
        "status": "queued",
        "createdAt": created_at,
        "updatedAt": created_at,
        "startedAt": None,
        "finishedAt": None,
        "caseId": cid,
        "proposalId": str(proposal_id).strip() if proposal_id else None,
        "requestedByUserSub": str(requested_by_user_sub).strip() if requested_by_user_sub else None,
        "payload": payload or {},
        "progress": {"pct": 0, "step": "queued", "message": "Queued"},
        **_job_case_index_item(job_id=jid, created_at=created_at, case_id=cid),
    }
    job_item = {k: v for k, v in job_item.items() if v is not None}

    map_item: dict[str, Any] = {
        **idempotency_key_key(idem),
        "entityType": "CONTRACTING_JOB_IDEMPOTENCY",
        "jobId": jid,
        "caseId": cid,
        "jobType": str(job_type or "unknown").strip() or "unknown",
        "createdAt": created_at,
    }

    try:
        t.transact_write(
            puts=[
                t.tx_put(item=job_item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)"),
                t.tx_put(item=map_item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)"),
            ]
        )
        return normalize_job_for_api(job_item) or {}
    except DdbConflict:
        # Another request won the race; fetch mapping and return that job.
        m = t.get_item(key=idempotency_key_key(idem)) or {}
        job_id = str(m.get("jobId") or "").strip()
        return get_job(job_id) or {}


def try_mark_running(*, job_id: str) -> dict[str, Any] | None:
    """
    Conditional transition queued->running. Returns updated job or None if not eligible.
    """
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id is required")
    now = now_iso()
    updated = get_main_table().update_item(
        key=job_key(jid),
        update_expression="SET #s = :r, startedAt = :st, updatedAt = :u, progress = :p",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":r": "running",
            ":st": now,
            ":u": now,
            ":p": {"pct": 5, "step": "running", "message": "Running"},
        },
        condition_expression="#s = :q",
        return_values="ALL_NEW",
    )
    return normalize_job_for_api(updated) if updated else None


def update_progress(*, job_id: str, pct: int, step: str, message: str) -> dict[str, Any] | None:
    jid = str(job_id or "").strip()
    now = now_iso()
    p = max(0, min(100, int(pct or 0)))
    updated = get_main_table().update_item(
        key=job_key(jid),
        update_expression="SET updatedAt = :u, progress = :p",
        expression_attribute_names=None,
        expression_attribute_values={":u": now, ":p": {"pct": p, "step": str(step or ""), "message": str(message or "")}},
        return_values="ALL_NEW",
    )
    return normalize_job_for_api(updated)


def complete_job(*, job_id: str, result: dict[str, Any]) -> dict[str, Any] | None:
    jid = str(job_id or "").strip()
    now = now_iso()
    updated = get_main_table().update_item(
        key=job_key(jid),
        update_expression="SET #s = :s, finishedAt = :f, updatedAt = :u, result = :r, progress = :p",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": "completed",
            ":f": now,
            ":u": now,
            ":r": result or {},
            ":p": {"pct": 100, "step": "completed", "message": "Completed"},
        },
        return_values="ALL_NEW",
    )
    return normalize_job_for_api(updated)


def fail_job(*, job_id: str, error: str) -> dict[str, Any] | None:
    jid = str(job_id or "").strip()
    now = now_iso()
    err = (str(error or "").strip() or "failed")[:800]
    updated = get_main_table().update_item(
        key=job_key(jid),
        update_expression="SET #s = :s, finishedAt = :f, updatedAt = :u, error = :e, progress = :p",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": "failed",
            ":f": now,
            ":u": now,
            ":e": err,
            ":p": {"pct": 100, "step": "failed", "message": err},
        },
        return_values="ALL_NEW",
    )
    return normalize_job_for_api(updated)

