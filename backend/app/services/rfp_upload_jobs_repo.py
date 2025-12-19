from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table

JobStatus = Literal["queued", "processing", "completed", "failed"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def type_pk(t: str) -> str:
    return f"TYPE#{t}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def job_key(job_id: str) -> dict[str, str]:
    return {"pk": f"RFPUPLOAD#{job_id}", "sk": "JOB"}


def _job_type_item(job_id: str, created_at: str) -> dict[str, str]:
    return {"gsi1pk": type_pk("RFP_UPLOAD_JOB"), "gsi1sk": f"{created_at}#{job_id}"}


def normalize_job_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None

    obj = dict(item)
    obj["jobId"] = obj.get("jobId") or ""

    # Never expose internal keys or user identity fields.
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "userSub"):
        obj.pop(k, None)

    return obj


def create_job(*, user_sub: str, s3_key: str, file_name: str) -> dict[str, Any]:
    jid = new_id("rfp_upload")
    created_at = now_iso()

    item: dict[str, Any] = {
        **job_key(jid),
        "entityType": "RFP_UPLOAD_JOB",
        "jobId": jid,
        "status": "queued",
        "createdAt": created_at,
        "updatedAt": created_at,
        "userSub": user_sub,
        "s3Key": s3_key,
        "fileName": file_name or "upload.pdf",
        **_job_type_item(jid, created_at),
    }

    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_job_for_api(item) or {}

def get_job_item(job_id: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key=job_key(job_id))


def get_job(job_id: str) -> dict[str, Any] | None:
    return normalize_job_for_api(get_job_item(job_id))


def update_job(
    *,
    job_id: str,
    updates_obj: dict[str, Any],
) -> dict[str, Any] | None:
    allowed = {
        "status",
        "updatedAt",
        "startedAt",
        "finishedAt",
        "rfpId",
        "error",
        "sourceS3Uri",
    }

    updates = {k: v for k, v in (updates_obj or {}).items() if k in allowed}

    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {}

    if not expr_parts and not updates:
        updates = {"updatedAt": now_iso()}

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
        update_expression="SET " + ", ".join(expr_parts) if expr_parts else "SET updatedAt = :u",
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values if expr_values else {":u": now_iso()},
        return_values="ALL_NEW",
    )

    return normalize_job_for_api(updated)


def list_jobs_for_user(*, user_sub: str, limit: int = 50, next_token: str | None = None) -> dict[str, Any]:
    # Optional helper: list recent jobs (uses GSI1 global list then filters in app).
    # We keep it simple; this can be improved with a user-scoped GSI later.
    t = get_main_table()
    page = t.query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("RFP_UPLOAD_JOB")),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=next_token,
    )

    out: list[dict[str, Any]] = []
    for it in page.items:
        if str(it.get("userSub") or "") != str(user_sub):
            continue
        norm = normalize_job_for_api(it)
        if norm:
            out.append(norm)

    return {"data": out, "nextToken": page.next_token}
