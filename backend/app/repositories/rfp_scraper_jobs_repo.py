from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def scraper_job_key(job_id: str) -> dict[str, str]:
    return {"pk": f"SCRAPERJOB#{job_id}", "sk": "PROFILE"}


def _scraper_job_type_item(job_id: str, source: str, created_at: str) -> dict[str, str]:
    return {
        "gsi1pk": f"SCRAPERJOB_SOURCE#{source}",
        "gsi1sk": f"{created_at}#{job_id}",
    }


def normalize_job_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize a scraper job item for API responses."""
    if not item:
        return None

    obj = dict(item)
    obj["_id"] = item.get("jobId")
    obj["id"] = item.get("jobId")

    # Remove internal keys
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "jobId"):
        obj.pop(k, None)

    return obj


def create_job(
    *,
    source: str,
    search_params: dict[str, Any] | None = None,
    user_sub: str | None = None,
) -> dict[str, Any]:
    """Create a scraper job."""
    job_id = new_id("scraperjob")
    created_at = now_iso()

    item: dict[str, Any] = {
        **scraper_job_key(job_id),
        "entityType": "ScraperJob",
        "jobId": job_id,
        "source": source,
        "searchParams": search_params or {},
        "status": "queued",  # queued, running, completed, failed
        "userSub": user_sub,
        "candidatesFound": 0,
        "candidatesImported": 0,
        "error": None,
        "createdAt": created_at,
        "updatedAt": created_at,
        "startedAt": None,
        "finishedAt": None,
        **_scraper_job_type_item(job_id, source, created_at),
    }

    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_job_for_api(item) or {}


def get_job_item(job_id: str) -> dict[str, Any] | None:
    """Get a scraper job item (raw DynamoDB item)."""
    return get_main_table().get_item(key=scraper_job_key(job_id))


def get_job(job_id: str) -> dict[str, Any] | None:
    """Get a scraper job (normalized for API)."""
    item = get_job_item(job_id)
    return normalize_job_for_api(item)


def update_job(job_id: str, updates_obj: dict[str, Any]) -> dict[str, Any] | None:
    """Update a scraper job."""
    allowed = {
        "status",
        "candidatesFound",
        "candidatesImported",
        "error",
        "startedAt",
        "finishedAt",
    }

    updates = {k: v for k, v in (updates_obj or {}).items() if k in allowed}

    now = now_iso()
    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {":u": now}

    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        expr_names[nk] = k
        expr_values[vk] = v
        expr_parts.append(f"{nk} = {vk}")

    expr_parts.append("updatedAt = :u")

    t = get_main_table()
    updated = t.update_item(
        key=scraper_job_key(job_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )

    return normalize_job_for_api(updated)


def list_jobs(
    *,
    source: str | None = None,
    status: str | None = None,
    limit: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    """
    List scraper jobs, optionally filtered by source and status.
    
    If source is provided, uses GSI1. Otherwise, would need a scan (not implemented yet).
    """
    lim = max(1, min(200, int(limit or 50)))

    t = get_main_table()

    if source:
        # Use GSI1 to filter by source
        page_resp = t.query_page(
            index_name="GSI1",
            key_condition_expression=Key("gsi1pk").eq(f"SCRAPERJOB_SOURCE#{source}"),
            scan_index_forward=False,
            limit=lim,
            next_token=next_token,
        )
    else:
        # For now, raise an error if source is not provided
        raise ValueError("source parameter is required for listing")

    data: list[dict[str, Any]] = []
    for it in page_resp.items:
        norm = normalize_job_for_api(it)
        if norm:
            # Apply status filter if provided
            if status and str(norm.get("status") or "").strip().lower() != status.lower():
                continue
            data.append(norm)

    return {
        "data": data,
        "nextToken": page_resp.next_token,
        "pagination": {"limit": lim, "source": source, "status": status},
    }

