from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ...db.dynamodb.table import get_main_table
from ...domain.rfp.rfp_logic import check_disqualification, compute_date_sanity, compute_fit_score


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def type_pk(t: str) -> str:
    return f"TYPE#{t}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def rfp_key(rfp_id: str) -> dict[str, str]:
    return {"pk": f"RFP#{rfp_id}", "sk": "PROFILE"}


def _rfp_type_item(rfp_id: str, created_at: str) -> dict[str, str]:
    return {"gsi1pk": type_pk("RFP"), "gsi1sk": f"{created_at}#{rfp_id}"}


def normalize_rfp_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None

    obj = dict(item)
    obj["_id"] = item.get("rfpId")

    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "rfpId"):
        obj.pop(k, None)

    disq = check_disqualification(obj)
    obj["isDisqualified"] = bool(disq)

    ds = compute_date_sanity(obj)
    obj["dateWarnings"] = ds.get("warnings")
    obj["dateMeta"] = ds.get("meta")

    fit = compute_fit_score(obj)
    obj["fitScore"] = fit.get("score")
    obj["fitReasons"] = fit.get("reasons")

    return obj


def create_rfp_from_analysis(*, analysis: dict[str, Any], source_file_name: str, source_file_size: int) -> dict[str, Any]:
    rfp_id = new_id("rfp")
    item = build_rfp_item_from_analysis(
        rfp_id=rfp_id,
        analysis=analysis,
        source_file_name=source_file_name,
        source_file_size=source_file_size,
    )
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_rfp_for_api(item) or {}


def build_rfp_item_from_analysis(
    *,
    rfp_id: str,
    analysis: dict[str, Any],
    source_file_name: str,
    source_file_size: int,
) -> dict[str, Any]:
    """
    Build the DynamoDB item for an RFP record.

    This is used by both the normal create path and the de-dupe transactional path.
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    created_at = now_iso()

    item: dict[str, Any] = {
        **rfp_key(rid),
        "entityType": "RFP",
        "rfpId": rid,
        "createdAt": created_at,
        "updatedAt": created_at,
        **(analysis or {}),
        "fileName": source_file_name or "",
        "fileSize": int(source_file_size or 0),
        "clientName": (analysis or {}).get("clientName") or "Unknown Client",
        **_rfp_type_item(rid, created_at),
    }
    return item


def get_rfp_by_id(rfp_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=rfp_key(rfp_id))
    return normalize_rfp_for_api(item)


def list_rfps(page: int = 1, limit: int = 20, next_token: str | None = None) -> dict[str, Any]:
    """List RFPs via cursor pagination.

    - Primary pagination mechanism is `next_token` (opaque encrypted cursor).
    - `page` is kept for backward compatibility but is implemented by advancing
      the cursor `page-1` times, which can be expensive.
    """
    p = max(1, int(page or 1))
    lim = max(1, min(200, int(limit or 20)))

    t = get_main_table()
    token = next_token

    # Back-compat: if a caller requests a deeper \"page\" without providing a token,
    # advance the cursor `page-1` times.
    if not token and p > 1:
        for _ in range(1, p):
            pg = t.query_page(
                index_name="GSI1",
                key_condition_expression=Key("gsi1pk").eq(type_pk("RFP")),
                scan_index_forward=False,
                limit=lim,
                next_token=token,
            )
            token = pg.next_token
            if not token:
                break

    page_resp = t.query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("RFP")),
        scan_index_forward=False,
        limit=lim,
        next_token=token,
    )

    data: list[dict[str, Any]] = []
    for it in page_resp.items:
        norm = normalize_rfp_for_api(it)
        if norm:
            data.append(norm)

    return {
        "data": data,
        "nextToken": page_resp.next_token,
        # Keep a small pagination object for legacy callers. Totals are not computed
        # in cursor mode (would require extra scans/queries).
        "pagination": {"page": p, "limit": lim},
    }


def update_rfp(rfp_id: str, updates_obj: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "title",
        "clientName",
        "submissionDeadline",
        "questionsDeadline",
        "bidMeetingDate",
        "bidRegistrationDate",
        "budgetRange",
        "keyRequirements",
        "deliverables",
        "criticalInformation",
        "timeline",
        "projectDeadline",
        "projectType",
        "contactInformation",
        "location",
        "clarificationQuestions",
        "sectionTitles",
        "buyerProfiles",
        # Source artifact (original PDF) for viewing/downloading
        "sourceS3Key",
        "sourceS3Uri",
        # AI artifacts (only written by server-side flows)
        "rawText",
        "_analysis",
        "aiSummary",
        "aiSummaryUpdatedAt",
        # Review workflow (bid/no-bid decision, notes, etc.)
        "review",
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

    updated = get_main_table().update_item(
        key=rfp_key(rfp_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )

    return normalize_rfp_for_api(updated)


def delete_rfp(rfp_id: str) -> None:
    get_main_table().delete_item(key=rfp_key(rfp_id))


def list_rfp_proposal_summaries(rfp_id: str) -> list[dict[str, Any]]:
    t = get_main_table()
    items: list[dict[str, Any]] = []
    tok: str | None = None
    while True:
        pg = t.query_page(
            key_condition_expression=Key("pk").eq(f"RFP#{rfp_id}")
            & Key("sk").begins_with("PROPOSAL#"),
            scan_index_forward=False,
            limit=200,
            next_token=tok,
        )
        items.extend(pg.items)
        tok = pg.next_token
        if not tok or not pg.items:
            break

    out: list[dict[str, Any]] = []
    for it in items:
        o = dict(it)
        o.pop("pk", None)
        o.pop("sk", None)
        out.append(o)
    return out
