from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from ..db.dynamodb.errors import DdbConflict
from ..db.dynamodb.table import get_main_table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def tracker_map_key(*, row_key_sha: str) -> dict[str, str]:
    h = str(row_key_sha or "").strip().lower()
    if not h:
        raise ValueError("row_key_sha is required")
    return {"pk": f"OPPTRACKER#{h}", "sk": "MAP"}


def compute_row_key_sha(*, parts: list[str]) -> str:
    # Stable idempotency key for CSV rows: sha256 over normalized concatenation.
    norm = [str(p or "").strip().lower() for p in (parts or [])]
    raw = "|".join(norm).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def get_mapping(*, row_key_sha: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key=tracker_map_key(row_key_sha=row_key_sha))


def put_mapping(*, row_key_sha: str, rfp_id: str) -> dict[str, Any]:
    h = str(row_key_sha or "").strip().lower()
    rid = str(rfp_id or "").strip()
    if not h:
        raise ValueError("row_key_sha is required")
    if not rid:
        raise ValueError("rfp_id is required")
    now = now_iso()
    item: dict[str, Any] = {
        **tracker_map_key(row_key_sha=h),
        "entityType": "OpportunityTrackerMap",
        "rowKeySha": h,
        "rfpId": rid,
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    except DdbConflict:
        # Dedupe hit; return existing mapping.
        existing = get_mapping(row_key_sha=h)
        return existing or item
    return item


def touch_mapping(*, row_key_sha: str) -> None:
    # Best-effort updatedAt refresh.
    h = str(row_key_sha or "").strip().lower()
    if not h:
        return
    get_main_table().update_item(
        key=tracker_map_key(row_key_sha=h),
        update_expression="SET updatedAt = :u",
        expression_attribute_names=None,
        expression_attribute_values={":u": now_iso()},
        return_values="NONE",
    )


