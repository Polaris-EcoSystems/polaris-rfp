from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table

AiJobStatus = Literal["queued", "running", "completed", "failed"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_job_id(prefix: str = "ai") -> str:
    return f"{prefix}_{uuid.uuid4()}"


def job_key(job_id: str) -> dict[str, str]:
    return {"pk": f"AIJOB#{job_id}", "sk": "JOB"}


def type_pk(t: str) -> str:
    return f"TYPE#{t}"


def _job_type_item(job_id: str, created_at: str) -> dict[str, str]:
    return {"gsi1pk": type_pk("AI_JOB"), "gsi1sk": f"{created_at}#{job_id}"}


def normalize_job_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    obj = dict(item)
    obj["jobId"] = obj.get("jobId") or ""
    # Never expose internal keys.
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "userSub"):
        obj.pop(k, None)
    return obj


def create_job(*, user_sub: str | None, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    jid = new_job_id("ai_job")
    created_at = now_iso()
    item: dict[str, Any] = {
        **job_key(jid),
        "entityType": "AI_JOB",
        "jobId": jid,
        "jobType": str(job_type or "unknown"),
        "status": "queued",
        "createdAt": created_at,
        "updatedAt": created_at,
        "userSub": str(user_sub) if user_sub else None,
        "payload": payload or {},
        **_job_type_item(jid, created_at),
    }
    # Strip nulls for DynamoDB cleanliness
    item = {k: v for k, v in item.items() if v is not None}
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_job_for_api(item) or {}


def get_job_item(job_id: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key=job_key(job_id))


def get_job(job_id: str) -> dict[str, Any] | None:
    return normalize_job_for_api(get_job_item(job_id))


def update_job(*, job_id: str, updates_obj: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "status",
        "updatedAt",
        "startedAt",
        "finishedAt",
        "error",
        "result",
    }
    updates = {k: v for k, v in (updates_obj or {}).items() if k in allowed}
    if "updatedAt" not in updates:
        updates["updatedAt"] = now_iso()

    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {}

    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        expr_names[nk] = k
        expr_values[vk] = v
        expr_parts.append(f"{nk} = {vk}")

    updated = get_main_table().update_item(
        key=job_key(job_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )
    return normalize_job_for_api(updated)


def list_recent_jobs(*, limit: int = 50, next_token: str | None = None) -> dict[str, Any]:
    t = get_main_table()
    page = t.query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("AI_JOB")),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=next_token,
    )
    out = [normalize_job_for_api(it) for it in page.items]
    return {"data": [x for x in out if x], "nextToken": page.next_token}

