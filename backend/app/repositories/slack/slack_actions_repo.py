from __future__ import annotations

import time
import uuid
from typing import Any

from ...db.dynamodb.errors import DdbConflict
from ...db.dynamodb.table import get_main_table


def _now_iso() -> str:
    # Lightweight; not importing datetime to keep dependencies minimal.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _action_key(action_id: str) -> dict[str, str]:
    aid = str(action_id or "").strip()
    if not aid:
        raise ValueError("action_id is required")
    return {"pk": f"SLACK_ACTION#{aid}", "sk": "PROFILE"}


def create_action(*, kind: str, payload: dict[str, Any], ttl_seconds: int = 600) -> dict[str, Any]:
    """
    Persist a proposed Slack action so confirmations are tamper-resistant.
    """
    aid = "sa_" + uuid.uuid4().hex[:18]
    now = _now_iso()
    expires_at = int(time.time()) + max(60, min(60 * 60, int(ttl_seconds or 600)))

    item: dict[str, Any] = {
        **_action_key(aid),
        "entityType": "SlackAction",
        "actionId": aid,
        "kind": str(kind or "").strip(),
        "payload": payload if isinstance(payload, dict) else {},
        "status": "proposed",
        "createdAt": now,
        "updatedAt": now,
        # TTL (enable TTL on this attribute if desired)
        "expiresAt": int(expires_at),
    }
    try:
        get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    except DdbConflict:
        # Extremely unlikely; regenerate once.
        return create_action(kind=kind, payload=payload, ttl_seconds=ttl_seconds)
    return {k: v for k, v in item.items() if k not in ("pk", "sk")}


def get_action(action_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=_action_key(action_id))
    if not it:
        return None
    # Strip Dynamo keys for API-ish usage
    out = dict(it)
    out.pop("pk", None)
    out.pop("sk", None)
    return out


def mark_action_done(*, action_id: str, status: str, result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    aid = str(action_id or "").strip()
    if not aid:
        raise ValueError("action_id is required")
    now = _now_iso()
    res = result if isinstance(result, dict) else {}
    updated = get_main_table().update_item(
        key=_action_key(aid),
        update_expression="SET #s = :s, #r = :r, updatedAt = :u",
        expression_attribute_names={"#s": "status", "#r": "result"},
        expression_attribute_values={":s": str(status or "").strip() or "done", ":r": res, ":u": now},
        return_values="ALL_NEW",
    )
    out = dict(updated or {})
    out.pop("pk", None)
    out.pop("sk", None)
    return out if out else None

