from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ...db.dynamodb.table import get_main_table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def scraped_rfp_key(candidate_id: str) -> dict[str, str]:
    return {"pk": f"SCRAPEDRFP#{candidate_id}", "sk": "CANDIDATE"}


def _scraped_rfp_type_item(candidate_id: str, source: str, created_at: str) -> dict[str, str]:
    return {
        "gsi1pk": f"SCRAPEDRFP_SOURCE#{source}",
        "gsi1sk": f"{created_at}#{candidate_id}",
    }


def normalize_scraped_rfp_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize a scraped RFP item for API responses."""
    if not item:
        return None

    obj = dict(item)
    obj["_id"] = item.get("candidateId")
    obj["id"] = item.get("candidateId")

    # Remove internal keys
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "candidateId"):
        obj.pop(k, None)

    return obj


def create_scraped_rfp(*, source: str, source_url: str, title: str, detail_url: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a scraped RFP candidate record."""
    candidate_id = new_id("scraped")
    created_at = now_iso()

    item: dict[str, Any] = {
        **scraped_rfp_key(candidate_id),
        "entityType": "ScrapedRfp",
        "candidateId": candidate_id,
        "source": source,
        "sourceUrl": source_url,
        "title": title,
        "detailUrl": detail_url,
        "metadata": metadata or {},
        "status": "pending",  # pending, imported, skipped, failed
        "importedRfpId": None,
        "createdAt": created_at,
        "updatedAt": created_at,
        **_scraped_rfp_type_item(candidate_id, source, created_at),
    }

    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_scraped_rfp_for_api(item) or {}


def get_scraped_rfp_by_id(candidate_id: str) -> dict[str, Any] | None:
    """Get a scraped RFP by ID."""
    item = get_main_table().get_item(key=scraped_rfp_key(candidate_id))
    return normalize_scraped_rfp_for_api(item)


def list_scraped_rfps(
    *,
    source: str | None = None,
    status: str | None = None,
    limit: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    """
    List scraped RFPs, optionally filtered by source and status.
    
    If source is provided, uses GSI1. Otherwise, would need a scan (not implemented yet).
    """
    lim = max(1, min(200, int(limit or 50)))

    t = get_main_table()

    if source:
        # Use GSI1 to filter by source
        page_resp = t.query_page(
            index_name="GSI1",
            key_condition_expression=Key("gsi1pk").eq(f"SCRAPEDRFP_SOURCE#{source}"),
            scan_index_forward=False,
            limit=lim,
            next_token=next_token,
        )
    else:
        # For now, raise an error if source is not provided (we'd need a different index for global listing)
        raise ValueError("source parameter is required for listing")

    data: list[dict[str, Any]] = []
    for it in page_resp.items:
        norm = normalize_scraped_rfp_for_api(it)
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


def update_scraped_rfp(candidate_id: str, updates_obj: dict[str, Any]) -> dict[str, Any] | None:
    """Update a scraped RFP candidate."""
    allowed = {
        "status",
        "importedRfpId",
        "title",
        "detailUrl",
        "metadata",
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
        key=scraped_rfp_key(candidate_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )

    return normalize_scraped_rfp_for_api(updated)


def mark_scraped_rfp_imported(candidate_id: str, rfp_id: str) -> dict[str, Any] | None:
    """Mark a scraped RFP as imported and link it to the created RFP."""
    return update_scraped_rfp(
        candidate_id,
        {
            "status": "imported",
            "importedRfpId": rfp_id,
        },
    )


def delete_scraped_rfp(candidate_id: str) -> None:
    """Delete a scraped RFP candidate."""
    get_main_table().delete_item(key=scraped_rfp_key(candidate_id))

