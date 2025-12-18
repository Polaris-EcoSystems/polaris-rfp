from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from .ddb import table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def attachment_key(rfp_id: str, attachment_id: str) -> dict[str, str]:
    return {"pk": f"RFP#{rfp_id}", "sk": f"ATTACHMENT#{attachment_id}"}


def normalize_attachment(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    # Frontend legacy shape expects `_id`; keep `id` too.
    out["_id"] = item.get("attachmentId")
    out["id"] = item.get("attachmentId")
    for k in ("pk", "sk", "entityType", "attachmentId"):
        out.pop(k, None)
    return out


def add_attachments(rfp_id: str, attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for a in attachments or []:
        attachment_id = new_id("att")
        uploaded_at = now_iso()
        item = {
            **attachment_key(rfp_id, attachment_id),
            "entityType": "RfpAttachment",
            "attachmentId": attachment_id,
            "rfpId": str(rfp_id),
            "uploadedAt": uploaded_at,
            **(a or {}),
        }
        table().put_item(Item=item)
        norm = normalize_attachment(item)
        if norm:
            created.append(norm)
    return created


def list_attachments(rfp_id: str) -> list[dict[str, Any]]:
    resp = table().query(
        KeyConditionExpression=Key("pk").eq(f"RFP#{rfp_id}") & Key("sk").begins_with("ATTACHMENT#"),
        ScanIndexForward=False,
    )
    out: list[dict[str, Any]] = []
    for it in resp.get("Items") or []:
        norm = normalize_attachment(it)
        if norm:
            out.append(norm)
    return out


def get_attachment(rfp_id: str, attachment_id: str) -> dict[str, Any] | None:
    resp = table().get_item(Key=attachment_key(rfp_id, attachment_id))
    return normalize_attachment(resp.get("Item"))


def delete_attachment(rfp_id: str, attachment_id: str) -> None:
    table().delete_item(Key=attachment_key(rfp_id, attachment_id))
