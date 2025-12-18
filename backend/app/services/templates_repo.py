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
    resp = table().get_item(Key=template_key(template_id))
    return normalize_template(resp.get("Item"))


def list_templates(limit: int = 200) -> list[dict[str, Any]]:
    resp = table().query(
        IndexName="GSI1",
        KeyConditionExpression=Key("gsi1pk").eq(type_pk("TEMPLATE")),
        ScanIndexForward=False,
        Limit=max(1, min(200, int(limit or 200))),
    )
    out: list[dict[str, Any]] = []
    for it in resp.get("Items") or []:
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

    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
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

    resp = table().update_item(
        Key=template_key(template_id),
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=expr_names if expr_names else None,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )

    return normalize_template(resp.get("Attributes"))


def delete_template(template_id: str) -> None:
    table().delete_item(Key=template_key(template_id))
