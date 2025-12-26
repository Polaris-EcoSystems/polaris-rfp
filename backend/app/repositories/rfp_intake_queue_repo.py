from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table

IntakeStatus = Literal["pending", "imported", "skipped", "failed"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def intake_key(*, candidate_id: str) -> dict[str, str]:
    cid = str(candidate_id or "").strip()
    if not cid:
        raise ValueError("candidate_id is required")
    return {"pk": f"RFPINTAKE#{cid}", "sk": "ITEM"}


def _status_index(*, status: IntakeStatus, created_at: str, candidate_id: str) -> dict[str, str]:
    st = str(status or "").strip().lower()
    if st not in ("pending", "imported", "skipped", "failed"):
        st = "pending"
    ca = str(created_at or "").strip() or now_iso()
    cid = str(candidate_id or "").strip()
    return {"gsi1pk": f"RFPINTAKE_STATUS#{st}", "gsi1sk": f"{ca}#{cid}"}


def normalize_intake_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "entityType", "gsi1pk", "gsi1sk"):
        out.pop(k, None)
    out["_id"] = str(out.get("candidateId") or "").strip() or None
    return out


def upsert_from_candidate(*, candidate: dict[str, Any]) -> dict[str, Any] | None:
    """
    Ensure an intake-queue item exists for a scraped candidate.

    This is best-effort; safe to call repeatedly.
    """
    if not isinstance(candidate, dict):
        return None
    cid = str(candidate.get("_id") or candidate.get("id") or candidate.get("candidateId") or "").strip()
    if not cid:
        return None

    status_raw = str(candidate.get("status") or "pending").strip().lower()
    status: IntakeStatus = "pending"  # type: ignore[assignment]
    if status_raw in ("pending", "imported", "skipped", "failed"):
        status = status_raw  # type: ignore[assignment]

    created_at = str(candidate.get("createdAt") or "").strip() or now_iso()
    updated_at = str(candidate.get("updatedAt") or "").strip() or created_at

    item: dict[str, Any] = {
        **intake_key(candidate_id=cid),
        "entityType": "RfpIntakeItem",
        "candidateId": cid,
        "status": status,
        "source": str(candidate.get("source") or "").strip() or None,
        "title": str(candidate.get("title") or "").strip() or "Untitled RFP",
        "detailUrl": str(candidate.get("detailUrl") or "").strip() or None,
        "sourceUrl": str(candidate.get("sourceUrl") or "").strip() or None,
        "metadata": candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {},
        "importedRfpId": str(candidate.get("importedRfpId") or "").strip() or None,
        "createdAt": created_at,
        "updatedAt": updated_at,
        **_status_index(status=status, created_at=created_at, candidate_id=cid),
    }
    item = {k: v for k, v in item.items() if v is not None}

    # Use UpdateItem (upsert) so we can safely refresh status/title/metadata.
    expr_names = {"#s": "status"}
    expr_values: dict[str, Any] = {
        ":s": item.get("status"),
        ":src": item.get("source"),
        ":t": item.get("title"),
        ":d": item.get("detailUrl"),
        ":su": item.get("sourceUrl"),
        ":m": item.get("metadata") or {},
        ":rfp": item.get("importedRfpId"),
        ":u": now_iso(),
        ":gpk": item.get("gsi1pk"),
        ":gsk": item.get("gsi1sk"),
        ":ca": item.get("createdAt"),
    }
    updated = get_main_table().update_item(
        key=intake_key(candidate_id=cid),
        update_expression=(
            "SET #s = :s, source = :src, title = :t, detailUrl = :d, sourceUrl = :su, "
            "metadata = :m, importedRfpId = :rfp, updatedAt = :u, createdAt = if_not_exists(createdAt, :ca), "
            "gsi1pk = :gpk, gsi1sk = :gsk"
        ),
        expression_attribute_names=expr_names,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )
    return normalize_intake_item(updated)


def update_status(*, candidate_id: str, status: IntakeStatus) -> dict[str, Any] | None:
    cid = str(candidate_id or "").strip()
    if not cid:
        raise ValueError("candidate_id is required")
    st = str(status or "").strip().lower()
    if st not in ("pending", "imported", "skipped", "failed"):
        raise ValueError("invalid status")

    existing = get_main_table().get_item(key=intake_key(candidate_id=cid)) or {}
    created_at = str(existing.get("createdAt") or "").strip() or now_iso()

    updated = get_main_table().update_item(
        key=intake_key(candidate_id=cid),
        update_expression="SET #s = :s, updatedAt = :u, gsi1pk = :gpk, gsi1sk = :gsk",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": st,
            ":u": now_iso(),
            ":gpk": f"RFPINTAKE_STATUS#{st}",
            ":gsk": f"{created_at}#{cid}",
        },
        return_values="ALL_NEW",
    )
    return normalize_intake_item(updated)


def list_intake(
    *,
    status: IntakeStatus = "pending",
    limit: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    st = str(status or "").strip().lower()
    if st not in ("pending", "imported", "skipped", "failed"):
        raise ValueError("invalid status")

    lim = max(1, min(200, int(limit or 50)))
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(f"RFPINTAKE_STATUS#{st}"),
        scan_index_forward=False,
        limit=lim,
        next_token=next_token,
    )
    data: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_intake_item(it)
        if norm:
            data.append(norm)
    return {"data": data, "nextToken": pg.next_token, "pagination": {"limit": lim, "status": st}}


