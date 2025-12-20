from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pk(*, user_sub: str) -> str:
    sub = str(user_sub or "").strip()
    if not sub:
        raise ValueError("user_sub is required")
    return f"USERMEMORY#{sub}"


def memory_block_key(*, user_sub: str, block_id: str) -> dict[str, str]:
    sub = str(user_sub or "").strip()
    bid = str(block_id or "").strip()
    if not sub:
        raise ValueError("user_sub is required")
    if not bid:
        raise ValueError("block_id is required")
    return {"pk": _pk(user_sub=sub), "sk": f"BLOCK#{bid}"}


def normalize_block(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "entityType"):
        out.pop(k, None)
    out["_id"] = str(out.get("blockId") or "").strip() or None
    return out


def upsert_block(
    *,
    user_sub: str,
    block_id: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Upsert a user memory block (durable, agent-readable).

    This is an admin/API function; writes should be approval-gated at the agent layer.
    """
    sub = str(user_sub or "").strip()
    bid = str(block_id or "").strip()
    if not sub or not bid:
        raise ValueError("user_sub and block_id are required")
    now = _now_iso()
    key = memory_block_key(user_sub=sub, block_id=bid)

    existing = get_main_table().get_item(key=key) or {}
    created_at = str(existing.get("createdAt") or "").strip() or now

    item: dict[str, Any] = {
        **key,
        "entityType": "UserMemoryBlock",
        "userSub": sub,
        "blockId": bid,
        "title": str(title or "").strip()[:240] or bid,
        "content": str(content or "").strip()[:20000],
        "tags": [str(t).strip().lower() for t in (tags or []) if str(t).strip()][:25],
        "meta": meta if isinstance(meta, dict) else {},
        "createdAt": created_at,
        "updatedAt": now,
    }
    get_main_table().put_item(item=item)
    return normalize_block(item) or {}


def list_blocks(*, user_sub: str, limit: int = 25) -> list[dict[str, Any]]:
    sub = str(user_sub or "").strip()
    if not sub:
        return []
    lim = max(1, min(50, int(limit or 25)))
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(_pk(user_sub=sub)) & Key("sk").begins_with("BLOCK#"),
        scan_index_forward=True,
        limit=lim,
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_block(it if isinstance(it, dict) else None)
        if norm:
            out.append(norm)
    return out[:lim]


def get_block(*, user_sub: str, block_id: str) -> dict[str, Any] | None:
    sub = str(user_sub or "").strip()
    bid = str(block_id or "").strip()
    if not sub or not bid:
        return None
    it = get_main_table().get_item(key=memory_block_key(user_sub=sub, block_id=bid))
    return normalize_block(it)


def new_block_id(*, prefix: str = "b") -> str:
    p = str(prefix or "b").strip() or "b"
    return f"{p}_" + uuid.uuid4().hex[:10]

