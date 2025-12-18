from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table


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

    # Transactional create: ensure both the proposal and the link item are created
    # atomically, and never overwrite an existing item.
    t = get_main_table()
    t.transact_write(
        puts=[
            t.tx_put(
                item=item,
                condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            ),
            t.tx_put(
                item=link,
                condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            ),
        ]
    )

    return normalize_proposal_for_api(item, include_sections=True) or {}


def get_proposal_by_id(proposal_id: str, include_sections: bool = True) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=proposal_key(proposal_id))
    return normalize_proposal_for_api(item, include_sections=include_sections)


def list_proposals(page: int = 1, limit: int = 20, next_token: str | None = None) -> dict[str, Any]:
    """List proposals via cursor pagination.

    - Primary pagination mechanism is `next_token`.
    - `page` is supported for backward compatibility by advancing the cursor.
    """
    p = max(1, int(page or 1))
    lim = max(1, min(200, int(limit or 20)))

    t = get_main_table()
    token = next_token

    if not token and p > 1:
        for _ in range(1, p):
            pg = t.query_page(
                index_name="GSI1",
                key_condition_expression=Key("gsi1pk").eq(type_pk("PROPOSAL")),
                scan_index_forward=False,
                limit=lim,
                next_token=token,
            )
            token = pg.next_token
            if not token:
                break

    page_resp = t.query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("PROPOSAL")),
        scan_index_forward=False,
        limit=lim,
        next_token=token,
    )

    data: list[dict[str, Any]] = []
    for it in page_resp.items:
        norm = normalize_proposal_for_api(it, include_sections=False)
        if norm:
            data.append(norm)

    return {
        "data": data,
        "nextToken": page_resp.next_token,
        "pagination": {"page": p, "limit": lim},
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

    updated = get_main_table().update_item(
        key=proposal_key(proposal_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )

    # best-effort update link item
    if updated and updated.get("rfpId"):
        try:
            get_main_table().put_item(
                item={
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
    updated = get_main_table().update_item(
        key=proposal_key(proposal_id),
        update_expression="SET review = :r, updatedAt = :u, gsi1sk = :g",
        expression_attribute_names=None,
        expression_attribute_values={":r": review_patch, ":u": now, ":g": f"{now}#{proposal_id}"},
        return_values="ALL_NEW",
    )
    if updated and updated.get("rfpId"):
        try:
            get_main_table().put_item(
                item={
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
    get_main_table().delete_item(key=proposal_key(proposal_id))
    if existing and existing.get("rfpId"):
        try:
            get_main_table().delete_item(key=proposal_rfp_link_key(existing["rfpId"], proposal_id))
        except Exception:
            pass


def list_proposals_by_rfp(rfp_id: str) -> list[dict[str, Any]]:
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
        o["_id"] = it.get("proposalId")
        for k in ("pk", "sk", "entityType"):
            o.pop(k, None)
        out.append(o)
    return out
