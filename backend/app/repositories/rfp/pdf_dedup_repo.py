from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from ...db.dynamodb.table import get_main_table

DedupStatus = Literal["reserved", "processing", "completed", "failed"]


_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_sha256(value: str) -> str:
    sha = str(value or "").strip().lower()
    if not _SHA256_RE.match(sha):
        raise ValueError("Invalid sha256 (expected 64 lowercase hex chars)")
    return sha


def dedup_key(sha256: str) -> dict[str, str]:
    sha = normalize_sha256(sha256)
    return {"pk": f"RFPFILE#{sha}", "sk": "PDF"}


def get_by_sha256(sha256: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key=dedup_key(sha256))


def ensure_record(*, sha256: str, s3_key: str) -> dict[str, Any]:
    """
    Ensure a de-dupe record exists for this sha256. If it already exists, this is a no-op.

    Returns the record (best-effort; if a race happens, we read after conflict).
    """
    t = get_main_table()
    sha = normalize_sha256(sha256)
    item: dict[str, Any] = {
        **dedup_key(sha),
        "entityType": "RfpPdfDedup",
        "sha256": sha,
        "s3Key": str(s3_key or "").strip(),
        "status": "reserved",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    try:
        t.put_item(item=item, condition_expression="attribute_not_exists(pk)")
        return item
    except Exception:
        # If the conditional put fails (already exists) or transient errors occur,
        # fall back to reading.
        existing = t.get_item(key=dedup_key(sha))
        return existing or item


def mark_processing(*, sha256: str) -> dict[str, Any] | None:
    sha = normalize_sha256(sha256)
    return get_main_table().update_item(
        key=dedup_key(sha),
        update_expression="SET #s = :s, updatedAt = :u",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={":s": "processing", ":u": now_iso()},
        return_values="ALL_NEW",
    )


def mark_failed(*, sha256: str, error: str) -> dict[str, Any] | None:
    sha = normalize_sha256(sha256)
    err = str(error or "").strip()
    if len(err) > 1200:
        err = err[:1200]
    return get_main_table().update_item(
        key=dedup_key(sha),
        update_expression="SET #s = :s, #e = :e, updatedAt = :u",
        expression_attribute_names={"#s": "status", "#e": "error"},
        expression_attribute_values={":s": "failed", ":e": err, ":u": now_iso()},
        return_values="ALL_NEW",
    )


def mark_completed(*, sha256: str, rfp_id: str, s3_key: str) -> dict[str, Any] | None:
    sha = normalize_sha256(sha256)
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    return get_main_table().update_item(
        key=dedup_key(sha),
        update_expression="SET #s = :s, rfpId = :r, s3Key = :k, updatedAt = :u",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": "completed",
            ":r": rid,
            ":k": str(s3_key or "").strip(),
            ":u": now_iso(),
        },
        return_values="ALL_NEW",
    )


def reset_stale_mapping(*, sha256: str, s3_key: str, reason: str) -> dict[str, Any] | None:
    """
    Clear an invalid/stale `rfpId` mapping on a de-dupe record.

    This is used when a record claims a completed `rfpId`, but that RFP no longer exists
    (e.g., it was deleted or a prior write was partial). We REMOVE `rfpId` so future
    uploads can complete the transactional write (which requires `attribute_not_exists(rfpId)`).
    """
    sha = normalize_sha256(sha256)
    key = str(s3_key or "").strip()
    msg = str(reason or "").strip()
    if len(msg) > 1200:
        msg = msg[:1200]

    # Ensure the record exists so the update has a target.
    try:
        ensure_record(sha256=sha, s3_key=key)
    except Exception:
        pass

    return get_main_table().update_item(
        key=dedup_key(sha),
        # DynamoDB supports combined SET/REMOVE expressions.
        update_expression="SET #s = :s, #e = :e, s3Key = :k, updatedAt = :u REMOVE rfpId",
        expression_attribute_names={"#s": "status", "#e": "error"},
        expression_attribute_values={
            ":s": "reserved",
            ":e": msg or "stale_dedup_mapping",
            ":k": key,
            ":u": now_iso(),
        },
        return_values="ALL_NEW",
    )

