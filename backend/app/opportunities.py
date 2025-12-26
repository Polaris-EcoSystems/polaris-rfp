from __future__ import annotations

import importlib
from datetime import datetime, timezone
from typing import Any

from .db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ddb_key() -> Any:
    # Avoid static boto3 import so typecheck/lints don’t depend on boto3 stubs.
    mod = importlib.import_module("boto3.dynamodb.conditions")
    return getattr(mod, "Key")


def _Key(name: str) -> Any:
    return _ddb_key()(name)


def _type_pk(t: str) -> str:
    return f"TYPE#{t}"


def opportunity_key(opportunity_id: str) -> dict[str, str]:
    oid = str(opportunity_id or "").strip()
    if not oid:
        raise ValueError("opportunity_id is required")
    return {"pk": f"OPPORTUNITY#{oid}", "sk": "PROFILE"}


def normalize_opportunity_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    out["_id"] = str(item.get("opportunityId") or "").strip() or None
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "opportunityId"):
        out.pop(k, None)
    return out


def get_opportunity_by_id(opportunity_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=opportunity_key(opportunity_id))
    return normalize_opportunity_for_api(it)


def ensure_opportunity_exists_for_rfp(
    *,
    rfp_id: str,
    created_by_user_sub: str | None = None,
    initial_stage: str | None = None,
) -> dict[str, Any]:
    """
    Ensure the Opportunity profile row exists.

    Back-compat: opportunity_id == rfp_id so Opportunity (PROFILE) can share the
    same pk as existing OpportunityState rows (different sk).
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")

    existing = get_opportunity_by_id(rid)
    if existing:
        return existing

    now = _now_iso()
    item: dict[str, Any] = {
        **opportunity_key(rid),
        "entityType": "Opportunity",
        "opportunityId": rid,
        "rfpId": rid,
        "stage": str(initial_stage).strip() if initial_stage else None,
        "activeProposalId": None,
        "contractingCaseId": None,
        "projectId": None,
        "createdAt": now,
        "updatedAt": now,
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
        "gsi1pk": _type_pk("OPPORTUNITY"),
        "gsi1sk": f"{now}#{rid}",
    }
    item = {k: v for k, v in item.items() if v is not None}
    try:
        get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    except Exception:
        pass
    return get_opportunity_by_id(rid) or {"_id": rid, "rfpId": rid}


def update_opportunity(
    opportunity_id: str,
    patch: dict[str, Any],
    *,
    updated_by_user_sub: str | None = None,
) -> dict[str, Any] | None:
    oid = str(opportunity_id or "").strip()
    if not oid:
        raise ValueError("opportunity_id is required")

    allowed = {"stage", "activeProposalId", "contractingCaseId", "projectId"}
    updates = {k: v for k, v in (patch or {}).items() if k in allowed}

    now = _now_iso()
    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {
        ":u": now,
        ":gsk": f"{now}#{oid}",
        ":by": str(updated_by_user_sub).strip() if updated_by_user_sub else None,
    }

    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        expr_names[nk] = k
        expr_values[vk] = v
        expr_parts.append(f"{nk} = {vk}")

    expr_parts.append("updatedAt = :u")
    expr_parts.append("gsi1sk = :gsk")
    if updated_by_user_sub:
        expr_parts.append("updatedByUserSub = :by")

    updated = get_main_table().update_item(
        key=opportunity_key(oid),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )
    return normalize_opportunity_for_api(updated)


def list_opportunities(*, limit: int = 50, next_token: str | None = None) -> dict[str, Any]:
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=_Key("gsi1pk").eq(_type_pk("OPPORTUNITY")),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=next_token,
    )
    data: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_opportunity_for_api(it)
        if norm:
            data.append(norm)
    return {"data": data, "nextToken": pg.next_token}


# “Service” wrappers (kept for readability; still a single module)
def ensure_from_rfp(
    *,
    rfp_id: str,
    created_by_user_sub: str | None = None,
    initial_stage: str | None = None,
) -> dict[str, Any]:
    return ensure_opportunity_exists_for_rfp(
        rfp_id=rfp_id, created_by_user_sub=created_by_user_sub, initial_stage=initial_stage
    )


def attach_active_proposal(
    *,
    opportunity_id: str,
    proposal_id: str,
    updated_by_user_sub: str | None = None,
) -> dict[str, Any] | None:
    return update_opportunity(
        opportunity_id,
        {"activeProposalId": str(proposal_id or "").strip() or None},
        updated_by_user_sub=updated_by_user_sub,
    )


def attach_contracting_case(
    *,
    opportunity_id: str,
    case_id: str,
    updated_by_user_sub: str | None = None,
) -> dict[str, Any] | None:
    return update_opportunity(
        opportunity_id,
        {"contractingCaseId": str(case_id or "").strip() or None},
        updated_by_user_sub=updated_by_user_sub,
    )


def set_stage(
    *,
    opportunity_id: str,
    stage: str,
    updated_by_user_sub: str | None = None,
) -> dict[str, Any] | None:
    return update_opportunity(
        opportunity_id,
        {"stage": str(stage or "").strip() or None},
        updated_by_user_sub=updated_by_user_sub,
    )


