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


def template_key(template_id: str) -> dict[str, str]:
    return {"pk": f"TEMPLATE#{template_id}", "sk": "PROFILE"}


def normalize_template(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    out["id"] = item.get("templateId")
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "templateId"):
        out.pop(k, None)
    return out


def get_template_by_id(template_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=template_key(template_id))
    return normalize_template(item)


def list_templates(limit: int = 200) -> list[dict[str, Any]]:
    t = get_main_table()
    pg = t.query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("TEMPLATE")),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 200))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items:
        norm = normalize_template(it)
        if norm:
            out.append(norm)
    return out


def create_template(doc: dict[str, Any]) -> dict[str, Any]:
    template_id = new_id("tpl")
    now = now_iso()

    item = {
        **template_key(template_id),
        "entityType": "Template",
        "templateId": template_id,
        "name": str(doc.get("name") or ""),
        "description": str(doc.get("description") or ""),
        "projectType": str(doc.get("projectType") or ""),
        "sections": doc.get("sections") or [],
        "tags": doc.get("tags") or [],
        "isActive": bool(doc.get("isActive", True)),
        "version": int(doc.get("version") or 1),
        "createdBy": str(doc.get("createdBy") or "user"),
        "lastModifiedBy": str(doc.get("lastModifiedBy") or "user"),
        "createdAt": now,
        "updatedAt": now,
        "gsi1pk": type_pk("TEMPLATE"),
        "gsi1sk": f"{now}#{template_id}",
    }

    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_template(item) or {}


def update_template(template_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "name",
        "description",
        "projectType",
        "sections",
        "isActive",
        "tags",
        "version",
        "lastModifiedBy",
    }

    updates: dict[str, Any] = {k: v for k, v in (patch or {}).items() if k in allowed}
    now = now_iso()

    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {":u": now, ":g": f"{now}#{template_id}"}

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
        key=template_key(template_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )

    return normalize_template(updated)


def delete_template(template_id: str) -> None:
    get_main_table().delete_item(key=template_key(template_id))
