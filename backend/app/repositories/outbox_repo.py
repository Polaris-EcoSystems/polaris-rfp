from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.db.dynamodb.errors import DdbConflict
from app.db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _type_pk(t: str) -> str:
    return f"{t}"


def outbox_key(event_id: str) -> dict[str, str]:
    eid = str(event_id or "").strip()
    if not eid:
        raise ValueError("event_id is required")
    return {"pk": f"OUTBOX#{eid}", "sk": "PROFILE"}


def enqueue_event(*, event_type: str, payload: dict[str, Any], dedupe_key: str | None = None) -> dict[str, Any]:
    """
    Enqueue an outbox event for async side effects (Slack, Drive, etc).

    Best-effort dedupe:
    - when dedupe_key is provided, we use it as event_id so retries collapse.
    """
    et = str(event_type or "").strip()
    if not et:
        raise ValueError("event_type is required")
    eid = str(dedupe_key or "").strip() or ("evt_" + uuid.uuid4().hex[:18])

    now = _now_iso()
    item: dict[str, Any] = {
        **outbox_key(eid),
        "entityType": "OutboxEvent",
        "eventId": eid,
        "eventType": et,
        "status": "pending",
        "attempts": 0,
        "maxAttempts": 8,
        "nextAttemptAt": now,
        "createdAt": now,
        "updatedAt": now,
        "payload": payload if isinstance(payload, dict) else {},
        # GSI1: pending queue
        "gsi1pk": "OUTBOX#PENDING",
        "gsi1sk": f"{now}#{eid}",
    }
    try:
        get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    except DdbConflict:
        # Dedupe hit; return existing
        existing = get_main_table().get_item(key=outbox_key(eid)) or {}
        return {k: v for k, v in existing.items() if k not in ("pk", "sk")}
    return {k: v for k, v in item.items() if k not in ("pk", "sk")}


def list_pending(*, limit: int = 50, next_token: str | None = None) -> dict[str, Any]:
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq("OUTBOX#PENDING"),
        scan_index_forward=True,
        limit=max(1, min(200, int(limit or 50))),
        next_token=next_token,
    )
    return {"items": pg.items or [], "nextToken": pg.next_token}


def claim_event(*, event_id: str) -> dict[str, Any] | None:
    """
    Atomically move an event from pending -> processing.
    """
    eid = str(event_id or "").strip()
    if not eid:
        raise ValueError("event_id is required")
    now = _now_iso()
    updated = get_main_table().update_item(
        key=outbox_key(eid),
        update_expression="SET #s = :s, lockedAt = :l, updatedAt = :u, gsi1pk = :gpk",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": "processing",
            ":l": now,
            ":u": now,
            ":gpk": "OUTBOX#PROCESSING",
            ":pending": "pending",
        },
        condition_expression="#s = :pending",
        return_values="ALL_NEW",
    )
    return updated


def mark_done(*, event_id: str, result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    eid = str(event_id or "").strip()
    if not eid:
        raise ValueError("event_id is required")
    now = _now_iso()
    res = result if isinstance(result, dict) else {}
    updated = get_main_table().update_item(
        key=outbox_key(eid),
        update_expression="SET #s = :s, updatedAt = :u, result = :r REMOVE gsi1pk, gsi1sk",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={":s": "done", ":u": now, ":r": res},
        return_values="ALL_NEW",
    )
    return updated


def mark_retry(*, event_id: str, error: str) -> dict[str, Any] | None:
    """
    Mark a processing event back to pending with exponential backoff.
    """
    eid = str(event_id or "").strip()
    if not eid:
        raise ValueError("event_id is required")
    raw = get_main_table().get_item(key=outbox_key(eid)) or {}
    attempts = int(raw.get("attempts") or 0) + 1
    max_attempts = int(raw.get("maxAttempts") or 8)
    now = _now_iso()

    if attempts >= max_attempts:
        updated = get_main_table().update_item(
            key=outbox_key(eid),
            update_expression="SET #s = :s, attempts = :a, lastError = :e, updatedAt = :u REMOVE gsi1pk, gsi1sk",
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={":s": "failed", ":a": attempts, ":e": str(error or "")[:800], ":u": now},
            return_values="ALL_NEW",
        )
        return updated

    # Exponential backoff capped at 5 minutes
    delay_s = min(300, int(2 ** min(10, attempts)))
    next_at = datetime.fromtimestamp(time.time() + delay_s, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    updated = get_main_table().update_item(
        key=outbox_key(eid),
        update_expression="SET #s = :s, attempts = :a, lastError = :e, nextAttemptAt = :n, updatedAt = :u, gsi1pk = :gpk, gsi1sk = :gsk",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": "pending",
            ":a": attempts,
            ":e": str(error or "")[:800],
            ":n": next_at,
            ":u": now,
            ":gpk": "OUTBOX#PENDING",
            ":gsk": f"{now}#{eid}",
        },
        return_values="ALL_NEW",
    )
    return updated


