from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ...db.dynamodb.table import get_main_table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def type_pk(t: str) -> str:
    return f"TYPE#{t}"


def _normalize(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    return out


# --- Connection ---

def _connection_key(user_id: str) -> dict[str, str]:
    return {"pk": f"USER#{user_id}", "sk": "CANVA#CONNECTION"}


def upsert_connection_for_user(user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    item: dict[str, Any] = {
        **_connection_key(user_id),
        "entityType": "CanvaConnection",
        "userId": str(user_id),
        "accessTokenEnc": fields.get("accessTokenEnc"),
        "refreshTokenEnc": fields.get("refreshTokenEnc"),
        "tokenType": fields.get("tokenType") or "bearer",
        "scopes": fields.get("scopes") if isinstance(fields.get("scopes"), list) else [],
        "expiresAt": fields.get("expiresAt"),
        "updatedAt": now,
        "gsi1pk": type_pk("CANVA_CONNECTION"),
        "gsi1sk": f"{now}#{user_id}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item) or {}


def upsert_pkce_for_user(user_id: str, pkce_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    item: dict[str, Any] = {
        "pk": f"USER#{user_id}",
        "sk": f"CANVA#PKCE#{pkce_id}",
        "entityType": "CanvaPkce",
        "userId": str(user_id),
        "pkceId": str(pkce_id),
        "codeVerifierEnc": fields.get("codeVerifierEnc"),
        "expiresAt": fields.get("expiresAt"),
        "createdAt": now,
        "updatedAt": now,
        "gsi1pk": type_pk("CANVA_PKCE"),
        "gsi1sk": f"{now}#{user_id}#{pkce_id}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item) or {}


def get_pkce_for_user(user_id: str, pkce_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key={"pk": f"USER#{user_id}", "sk": f"CANVA#PKCE#{pkce_id}"})
    return _normalize(item)


def delete_pkce_for_user(user_id: str, pkce_id: str) -> None:
    get_main_table().delete_item(key={"pk": f"USER#{user_id}", "sk": f"CANVA#PKCE#{pkce_id}"})


# --- Proposal design cache (for create-design + export reuse) ---


def upsert_proposal_design_cache(
    *,
    proposal_id: str,
    company_id: str,
    brand_template_id: str,
    design_id: str,
    design_url: str | None,
    meta: dict[str, Any] | None,
) -> dict[str, Any]:
    now = now_iso()
    item: dict[str, Any] = {
        "pk": f"PROPOSAL#{proposal_id}",
        "sk": f"CANVA#DESIGN#{company_id}#{brand_template_id}",
        "entityType": "CanvaProposalDesign",
        "proposalId": str(proposal_id),
        "companyId": str(company_id),
        "brandTemplateId": str(brand_template_id),
        "designId": str(design_id),
        "designUrl": str(design_url) if design_url else None,
        "meta": meta if isinstance(meta, dict) else {},
        "updatedAt": now,
        "gsi1pk": type_pk("CANVA_PROPOSAL_DESIGN"),
        "gsi1sk": f"{now}#{proposal_id}#{company_id}#{brand_template_id}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item) or {}


def get_proposal_design_cache(
    *, proposal_id: str, company_id: str, brand_template_id: str
) -> dict[str, Any] | None:
    item = get_main_table().get_item(
        key={
            "pk": f"PROPOSAL#{proposal_id}",
            "sk": f"CANVA#DESIGN#{company_id}#{brand_template_id}",
        }
    )
    return _normalize(item)


def delete_proposal_design_cache(
    *, proposal_id: str, company_id: str, brand_template_id: str
) -> None:
    get_main_table().delete_item(
        key={
            "pk": f"PROPOSAL#{proposal_id}",
            "sk": f"CANVA#DESIGN#{company_id}#{brand_template_id}",
        }
    )

def get_connection_for_user(user_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=_connection_key(user_id))
    return _normalize(item)


def delete_connection_for_user(user_id: str) -> None:
    get_main_table().delete_item(key=_connection_key(user_id))


# --- Company mappings ---

def _company_mapping_key(company_id: str) -> dict[str, str]:
    return {"pk": f"COMPANY#{company_id}", "sk": "CANVA#MAPPING"}


def upsert_company_mapping(company_id: str, brand_template_id: str, field_mapping: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    item: dict[str, Any] = {
        **_company_mapping_key(company_id),
        "entityType": "CanvaCompanyTemplate",
        "companyId": str(company_id),
        "brandTemplateId": str(brand_template_id),
        "fieldMapping": field_mapping if isinstance(field_mapping, dict) else {},
        "updatedAt": now,
        "gsi1pk": type_pk("CANVA_COMPANY_TEMPLATE"),
        "gsi1sk": f"{now}#{company_id}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item) or {}


def get_company_mapping(company_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=_company_mapping_key(company_id))
    return _normalize(item)


def list_company_mappings(limit: int = 200) -> list[dict[str, Any]]:
    t = get_main_table()
    pg = t.query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("CANVA_COMPANY_TEMPLATE")),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 200))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items:
        norm = _normalize(it)
        if norm:
            out.append(norm)
    return out


# --- Asset links ---

def _asset_link_key(owner_type: str, owner_id: str, kind: str) -> dict[str, str]:
    return {"pk": f"CANVA_ASSET#{owner_type}#{owner_id}", "sk": f"KIND#{kind}"}


def upsert_asset_link(owner_type: str, owner_id: str, kind: str, canva_asset_id: str, meta: dict[str, Any] | None, source_url: str | None) -> dict[str, Any]:
    now = now_iso()
    item: dict[str, Any] = {
        **_asset_link_key(owner_type, owner_id, kind),
        "entityType": "CanvaAssetLink",
        "ownerType": str(owner_type),
        "ownerId": str(owner_id),
        "kind": str(kind),
        "canvaAssetId": str(canva_asset_id),
        "sourceUrl": str(source_url) if source_url else None,
        "meta": meta if isinstance(meta, dict) else {},
        "updatedAt": now,
        "gsi1pk": type_pk("CANVA_ASSET_LINK"),
        "gsi1sk": f"{now}#{owner_type}#{owner_id}#{kind}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item) or {}


def get_asset_link(owner_type: str, owner_id: str, kind: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=_asset_link_key(owner_type, owner_id, kind))
    return _normalize(item)
