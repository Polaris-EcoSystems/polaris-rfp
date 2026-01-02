from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.db.dynamodb.errors import DdbConflict
from app.db.dynamodb.table import get_main_table
from app.repositories import rfp_intake_queue_repo


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


def _norm_url(u: str) -> str:
    s = str(u or "").strip()
    if not s:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit

        sp = urlsplit(s)
        scheme = (sp.scheme or "").lower()
        netloc = (sp.netloc or "").lower()
        path = (sp.path or "").rstrip("/")
        query = sp.query or ""
        return urlunsplit((scheme, netloc, path, query, ""))  # drop fragment
    except Exception:
        return s.rstrip("/")


def _dedup_hash(*, source: str, detail_url: str, source_url: str) -> str:
    d = _norm_url(detail_url)
    s = _norm_url(source_url)
    src = str(source or "").strip().lower()
    basis = d or s
    raw = f"{src}|{basis}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _dedup_key(*, dedup_sha: str) -> dict[str, str]:
    h = str(dedup_sha or "").strip().lower()
    if not h:
        raise ValueError("dedup_sha is required")
    return {"pk": f"SCRAPEDRFP_DEDUP#{h}", "sk": "MAP"}


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
    cand, _created = create_scraped_rfp_deduped(
        source=source,
        source_url=source_url,
        title=title,
        detail_url=detail_url,
        metadata=metadata,
    )
    return cand


def create_scraped_rfp_deduped(
    *,
    source: str,
    source_url: str,
    title: str,
    detail_url: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """
    Create a scraped candidate, de-duping by (source, normalized detailUrl|sourceUrl).

    Returns: (candidate, created_new)
    """
    candidate_id = new_id("scraped")
    created_at = now_iso()

    src = str(source or "").strip()
    su = str(source_url or "").strip()
    du = str(detail_url or "").strip()
    ttl = str(title or "").strip() or "Untitled RFP"
    md = metadata if isinstance(metadata, dict) else {}

    dedup_sha = _dedup_hash(source=src, detail_url=du, source_url=su)

    candidate_item: dict[str, Any] = {
        **scraped_rfp_key(candidate_id),
        "entityType": "ScrapedRfp",
        "candidateId": candidate_id,
        "source": src,
        "sourceUrl": su,
        "title": ttl,
        "detailUrl": du,
        "metadata": md,
        "status": "pending",  # pending, imported, skipped, failed
        "importedRfpId": None,
        "createdAt": created_at,
        "updatedAt": created_at,
        **_scraped_rfp_type_item(candidate_id, src, created_at),
    }

    dedup_item: dict[str, Any] = {
        **_dedup_key(dedup_sha=dedup_sha),
        "entityType": "ScrapedRfpDedup",
        "dedupSha": dedup_sha,
        "candidateId": candidate_id,
        "source": src,
        "detailUrl": _norm_url(du) or None,
        "sourceUrl": _norm_url(su) or None,
        "createdAt": created_at,
        "updatedAt": created_at,
    }
    dedup_item = {k: v for k, v in dedup_item.items() if v is not None}

    t = get_main_table()
    try:
        t.transact_write(
            puts=(
                t.tx_put(item=dedup_item, condition_expression="attribute_not_exists(pk)"),
                t.tx_put(item=candidate_item, condition_expression="attribute_not_exists(pk)"),
            )
        )
        norm = normalize_scraped_rfp_for_api(candidate_item) or {}
        try:
            rfp_intake_queue_repo.upsert_from_candidate(candidate=norm)
        except Exception:
            pass
        return norm, True
    except DdbConflict:
        existing_map = t.get_item(key=_dedup_key(dedup_sha=dedup_sha)) or {}
        existing_id = str(existing_map.get("candidateId") or "").strip()
        if existing_id:
            existing = get_scraped_rfp_by_id(existing_id) or {}
            try:
                rfp_intake_queue_repo.upsert_from_candidate(candidate=existing)
            except Exception:
                pass
            return existing, False
        raise


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

    norm = normalize_scraped_rfp_for_api(updated)
    if norm:
        try:
            rfp_intake_queue_repo.upsert_from_candidate(candidate=norm)
        except Exception:
            pass
    return norm


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

