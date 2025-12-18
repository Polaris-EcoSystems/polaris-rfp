from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from .ddb import table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def type_pk(t: str) -> str:
    return f"TYPE#{t}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def proposal_key(proposal_id: str) -> dict[str, str]:
    return {"pk": f"PROPOSAL#{proposal_id}", "sk": "PROFILE"}


def proposal_type_item(proposal_id: str, updated_at: str) -> dict[str, str]:
    return {"gsi1pk": type_pk("PROPOSAL"), "gsi1sk": f"{updated_at}#{proposal_id}"}


def proposal_rfp_link_key(rfp_id: str, proposal_id: str) -> dict[str, str]:
    return {"pk": f"RFP#{rfp_id}", "sk": f"PROPOSAL#{proposal_id}"}


def normalize_proposal_for_api(item: dict[str, Any] | None, include_sections: bool = True) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    out["_id"] = item.get("proposalId")
    out["rfpId"] = item.get("rfpId")

    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "proposalId"):
        out.pop(k, None)

    if not include_sections:
        out.pop("sections", None)

    return out


def create_proposal(
    *,
    rfp_id: str,
    company_id: str | None,
    template_id: str,
    title: str,
    sections: dict[str, Any],
    custom_content: dict[str, Any],
    rfp_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    proposal_id = new_id("proposal")
    created_at = now_iso()
    updated_at = created_at

    item: dict[str, Any] = {
        **proposal_key(proposal_id),
        "entityType": "Proposal",
        "proposalId": proposal_id,
        "rfpId": str(rfp_id),
        "companyId": str(company_id) if company_id else None,
        "templateId": str(template_id),
        "title": str(title),
        "status": "draft",
        "sections": sections or {},
        "customContent": custom_content or {},
        "review": {
            "score": None,
            "decision": "",
            "notes": "",
            "rubric": {},
            "updatedAt": None,
        },
        "createdAt": created_at,
        "updatedAt": updated_at,
        "rfpSummary": rfp_summary if isinstance(rfp_summary, dict) else None,
        **proposal_type_item(proposal_id, updated_at),
    }

    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")

    link = {
        **proposal_rfp_link_key(rfp_id, proposal_id),
        "entityType": "RfpProposalLink",
        "proposalId": proposal_id,
        "rfpId": str(rfp_id),
        "title": item["title"],
        "status": item["status"],
        "companyId": item.get("companyId"),
        "templateId": item.get("templateId"),
        "review": item.get("review"),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }
    table().put_item(Item=link)

    return normalize_proposal_for_api(item, include_sections=True) or {}


def get_proposal_by_id(proposal_id: str, include_sections: bool = True) -> dict[str, Any] | None:
    resp = table().get_item(Key=proposal_key(proposal_id))
    return normalize_proposal_for_api(resp.get("Item"), include_sections=include_sections)


def list_proposals(page: int = 1, limit: int = 20) -> dict[str, Any]:
    p = max(1, int(page or 1))
    lim = max(1, min(200, int(limit or 20)))
    desired = p * lim

    items: list[dict[str, Any]] = []
    last_key = None

    while len(items) < desired:
        resp = table().query(
            IndexName="GSI1",
            KeyConditionExpression=Key("gsi1pk").eq(type_pk("PROPOSAL")),
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
        "data": [
            normalize_proposal_for_api(it, include_sections=False)
            for it in slice_items
            if normalize_proposal_for_api(it, include_sections=False)
        ],
        "pagination": {
            "page": p,
            "limit": lim,
            "total": total,
            "pages": max(1, (total + lim - 1) // lim),
        },
    }


def update_proposal(proposal_id: str, updates_obj: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "title",
        "status",
        "sections",
        "customContent",
        "budgetBreakdown",
        "timelineDetails",
        "teamAssignments",
        "companyId",
        "templateId",
        "lastModifiedBy",
    }
    updates = {k: v for k, v in (updates_obj or {}).items() if k in allowed}

    now = now_iso()
    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {":u": now, ":g": f"{now}#{proposal_id}"}

    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        expr_names[nk] = k
        expr_values[vk] = v
        expr_parts.append(f"{nk} = {vk}")

    expr_parts.append("updatedAt = :u")
    expr_parts.append("gsi1sk = :g")

    resp = table().update_item(
        Key=proposal_key(proposal_id),
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=expr_names if expr_names else None,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )

    updated = resp.get("Attributes")

    # best-effort update link item
    if updated and updated.get("rfpId"):
        try:
            table().put_item(
                Item={
                    **proposal_rfp_link_key(updated["rfpId"], proposal_id),
                    "entityType": "RfpProposalLink",
                    "proposalId": proposal_id,
                    "rfpId": str(updated["rfpId"]),
                    "title": updated.get("title"),
                    "status": updated.get("status"),
                    "companyId": updated.get("companyId"),
                    "templateId": updated.get("templateId"),
                    "review": updated.get("review"),
                    "createdAt": updated.get("createdAt"),
                    "updatedAt": updated.get("updatedAt"),
                }
            )
        except Exception:
            pass

    return normalize_proposal_for_api(updated, include_sections=True)


def update_proposal_review(proposal_id: str, review_patch: dict[str, Any]) -> dict[str, Any] | None:
    now = now_iso()
    resp = table().update_item(
        Key=proposal_key(proposal_id),
        UpdateExpression="SET review = :r, updatedAt = :u, gsi1sk = :g",
        ExpressionAttributeValues={":r": review_patch, ":u": now, ":g": f"{now}#{proposal_id}"},
        ReturnValues="ALL_NEW",
    )

    updated = resp.get("Attributes")
    if updated and updated.get("rfpId"):
        try:
            table().put_item(
                Item={
                    **proposal_rfp_link_key(updated["rfpId"], proposal_id),
                    "entityType": "RfpProposalLink",
                    "proposalId": proposal_id,
                    "rfpId": str(updated["rfpId"]),
                    "title": updated.get("title"),
                    "status": updated.get("status"),
                    "companyId": updated.get("companyId"),
                    "templateId": updated.get("templateId"),
                    "review": updated.get("review"),
                    "createdAt": updated.get("createdAt"),
                    "updatedAt": updated.get("updatedAt"),
                }
            )
        except Exception:
            pass

    return normalize_proposal_for_api(updated, include_sections=True)


def delete_proposal(proposal_id: str) -> None:
    existing = get_proposal_by_id(proposal_id, include_sections=False)
    table().delete_item(Key=proposal_key(proposal_id))
    if existing and existing.get("rfpId"):
        try:
            table().delete_item(Key=proposal_rfp_link_key(existing["rfpId"], proposal_id))
        except Exception:
            pass


def list_proposals_by_rfp(rfp_id: str) -> list[dict[str, Any]]:
    resp = table().query(
        KeyConditionExpression=Key("pk").eq(f"RFP#{rfp_id}") & Key("sk").begins_with("PROPOSAL#"),
        ScanIndexForward=False,
    )

    items = resp.get("Items") or []
    out: list[dict[str, Any]] = []
    for it in items:
        o = dict(it)
        o["_id"] = it.get("proposalId")
        for k in ("pk", "sk", "entityType"):
            o.pop(k, None)
        out.append(o)
    return out
