from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pk(*, rfp_id: str) -> str:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    return f"OPPORTUNITY#{rid}"


def event_key(*, rfp_id: str, event_id: str, created_at: str) -> dict[str, str]:
    rid = str(rfp_id or "").strip()
    eid = str(event_id or "").strip()
    ts = str(created_at or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    if not eid:
        raise ValueError("event_id is required")
    if not ts:
        raise ValueError("created_at is required")
    return {"pk": _pk(rfp_id=rid), "sk": f"EVENT#{ts}#{eid}"}


def normalize_event(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "entityType", "gsi1pk", "gsi1sk"):
        out.pop(k, None)
    out["_id"] = str(out.get("eventId") or "").strip() or None
    return out


def append_event(
    *,
    rfp_id: str,
    type: str,
    payload: dict[str, Any] | None,
    tool: str | None = None,
    inputs_redacted: dict[str, Any] | None = None,
    outputs_redacted: dict[str, Any] | None = None,
    policy_checks: list[dict[str, Any]] | None = None,
    confidence_flags: list[str] | None = None,
    downstream_effects: list[dict[str, Any]] | None = None,
    created_by: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    now = _now_iso()
    eid = "e_" + uuid.uuid4().hex[:18]

    item: dict[str, Any] = {
        **event_key(rfp_id=rid, event_id=eid, created_at=now),
        "entityType": "AgentEvent",
        "rfpId": rid,
        "eventId": eid,
        "createdAt": now,
        # Global time index for reporting (GSI1)
        "gsi1pk": "TYPE#AGENT_EVENT",
        "gsi1sk": f"{now}#{eid}",
        "tsEpochMs": int(time.time() * 1000),
        "type": str(type or "").strip() or "event",
        "tool": str(tool or "").strip() or None,
        "payload": payload if isinstance(payload, dict) else {},
        "inputsRedacted": inputs_redacted if isinstance(inputs_redacted, dict) else {},
        "outputsRedacted": outputs_redacted if isinstance(outputs_redacted, dict) else {},
        "policyChecks": [x for x in (policy_checks or []) if isinstance(x, dict)][:50],
        "confidenceFlags": [str(x).strip() for x in (confidence_flags or []) if str(x).strip()][:25],
        "downstreamEffects": [x for x in (downstream_effects or []) if isinstance(x, dict)][:50],
        "createdBy": str(created_by).strip() if created_by else None,
        "correlationId": str(correlation_id).strip() if correlation_id else None,
    }
    item = {k: v for k, v in item.items() if v is not None}
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    return normalize_event(item) or {}


def list_recent_events_global(*, since_iso: str, limit: int = 200) -> list[dict[str, Any]]:
    """
    Query AgentEvents across all opportunities using GSI1 time index.
    Only events written after this feature shipped will be indexed (best-effort).
    """
    since = str(since_iso or "").strip()
    if not since:
        return []
    # Lexicographic ordering matches ISO timestamps.
    hi = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z") + "#~"
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq("TYPE#AGENT_EVENT") & Key("gsi1sk").between(f"{since}#", hi),
        scan_index_forward=True,
        limit=max(1, min(500, int(limit or 200))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_event(it)
        if norm:
            out.append(norm)
    return out


def list_recent_events(*, rfp_id: str, limit: int = 30) -> list[dict[str, Any]]:
    rid = str(rfp_id or "").strip()
    if not rid:
        return []
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(_pk(rfp_id=rid)) & Key("sk").begins_with("EVENT#"),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 30))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_event(it)
        if norm:
            out.append(norm)
    return out

