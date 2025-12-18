from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from .ddb import table
from .rfp_logic import check_disqualification, compute_date_sanity, compute_fit_score


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
    created_at = now_iso()

    item: dict[str, Any] = {
        **rfp_key(rfp_id),
        "entityType": "RFP",
        "rfpId": rfp_id,
        "createdAt": created_at,
        "updatedAt": created_at,
        **(analysis or {}),
        "fileName": source_file_name or "",
        "fileSize": int(source_file_size or 0),
        "clientName": (analysis or {}).get("clientName") or "Unknown Client",
        **_rfp_type_item(rfp_id, created_at),
    }

    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    return normalize_rfp_for_api(item) or {}


def get_rfp_by_id(rfp_id: str) -> dict[str, Any] | None:
    resp = table().get_item(Key=rfp_key(rfp_id))
    return normalize_rfp_for_api(resp.get("Item"))


def list_rfps(page: int = 1, limit: int = 20) -> dict[str, Any]:
    p = max(1, int(page or 1))
    lim = max(1, min(200, int(limit or 20)))
    desired = p * lim

    items: list[dict[str, Any]] = []
    last_key = None

    while len(items) < desired:
        resp = table().query(
            IndexName="GSI1",
            KeyConditionExpression=Key("gsi1pk").eq(type_pk("RFP")),
            ScanIndexForward=False,
            Limit=min(200, desired - len(items)),
            ExclusiveStartKey=last_key,
        )
        batch = resp.get("Items") or []
        items.extend(batch)
        last_key = resp.get("LastEvaluatedKey")
        if not last_key or not batch:
            break

    total = len(items)
    slice_items = items[(p - 1) * lim : p * lim]

    return {
        "data": [normalize_rfp_for_api(it) for it in slice_items if normalize_rfp_for_api(it)],
        "pagination": {
            "page": p,
            "limit": lim,
            "total": total,
            "pages": max(1, (total + lim - 1) // lim),
        },
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

    resp = table().update_item(
        Key=rfp_key(rfp_id),
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=expr_names if expr_names else None,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )

    return normalize_rfp_for_api(resp.get("Attributes"))


def delete_rfp(rfp_id: str) -> None:
    table().delete_item(Key=rfp_key(rfp_id))


def list_rfp_proposal_summaries(rfp_id: str) -> list[dict[str, Any]]:
    resp = table().query(
        KeyConditionExpression=Key("pk").eq(f"RFP#{rfp_id}") & Key("sk").begins_with("PROPOSAL#"),
        ScanIndexForward=False,
    )

    items = resp.get("Items") or []
    out: list[dict[str, Any]] = []
    for it in items:
        o = dict(it)
        o.pop("pk", None)
        o.pop("sk", None)
        out.append(o)
    return out
