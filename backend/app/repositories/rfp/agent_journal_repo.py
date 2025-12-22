from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ...db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pk(*, rfp_id: str) -> str:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    return f"OPPORTUNITY#{rid}"


def journal_key(*, rfp_id: str, entry_id: str, created_at: str) -> dict[str, str]:
    rid = str(rfp_id or "").strip()
    eid = str(entry_id or "").strip()
    ts = str(created_at or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    if not eid:
        raise ValueError("entry_id is required")
    if not ts:
        raise ValueError("created_at is required")
    return {"pk": _pk(rfp_id=rid), "sk": f"JOURNAL#{ts}#{eid}"}


def normalize_entry(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "entityType", "gsi1pk", "gsi1sk"):
        out.pop(k, None)
    out["_id"] = str(out.get("entryId") or "").strip() or None
    return out


def append_entry(
    *,
    rfp_id: str,
    topics: list[str] | None = None,
    user_stated: str | None = None,
    agent_intent: str | None = None,
    what_changed: str | None = None,
    why: str | None = None,
    assumptions: list[str] | None = None,
    sources: list[dict[str, Any]] | None = None,
    created_by_user_sub: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    now = _now_iso()
    eid = "j_" + uuid.uuid4().hex[:18]

    item: dict[str, Any] = {
        **journal_key(rfp_id=rid, entry_id=eid, created_at=now),
        "entityType": "AgentJournalEntry",
        "rfpId": rid,
        "entryId": eid,
        "createdAt": now,
        "topics": [str(t).strip() for t in (topics or []) if str(t).strip()][:25],
        "userStated": str(user_stated).strip() if user_stated else None,
        "agentIntent": str(agent_intent).strip() if agent_intent else None,
        "whatChanged": str(what_changed).strip() if what_changed else None,
        "why": str(why).strip() if why else None,
        "assumptions": [str(a).strip() for a in (assumptions or []) if str(a).strip()][:50],
        "sources": [s for s in (sources or []) if isinstance(s, dict)][:50],
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
        "meta": meta if isinstance(meta, dict) else {},
    }
    item = {k: v for k, v in item.items() if v is not None}
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    return normalize_entry(item) or {}


def list_recent_entries(*, rfp_id: str, limit: int = 20) -> list[dict[str, Any]]:
    rid = str(rfp_id or "").strip()
    if not rid:
        return []
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(_pk(rfp_id=rid)) & Key("sk").begins_with("JOURNAL#"),
        scan_index_forward=False,
        limit=max(1, min(100, int(limit or 20))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_entry(it)
        if norm:
            out.append(norm)
    return out

