from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def binding_key(*, channel_id: str, thread_ts: str) -> dict[str, str]:
    ch = str(channel_id or "").strip()
    ts = str(thread_ts or "").strip()
    if not ch:
        raise ValueError("channel_id is required")
    if not ts:
        raise ValueError("thread_ts is required")
    return {"pk": f"SLACKTHREAD#{ch}#{ts}", "sk": "BINDING"}


def normalize(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    out["_id"] = f"{out.get('channelId')}:{out.get('threadTs')}"
    return out


def get_binding(*, channel_id: str, thread_ts: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=binding_key(channel_id=channel_id, thread_ts=thread_ts))
    return normalize(it)


def set_binding(
    *,
    channel_id: str,
    thread_ts: str,
    rfp_id: str,
    bound_by_slack_user_id: str | None = None,
) -> dict[str, Any]:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    now = _now_iso()
    item: dict[str, Any] = {
        **binding_key(channel_id=channel_id, thread_ts=thread_ts),
        "entityType": "SlackThreadBinding",
        "channelId": str(channel_id or "").strip(),
        "threadTs": str(thread_ts or "").strip(),
        "rfpId": rid,
        "boundBySlackUserId": str(bound_by_slack_user_id).strip() if bound_by_slack_user_id else None,
        "createdAt": now,
        "updatedAt": now,
        "gsi1pk": "TYPE#SLACK_THREAD_BINDING",
        "gsi1sk": f"{now}#{rid}",
    }
    item = {k: v for k, v in item.items() if v is not None}
    get_main_table().put_item(item=item)
    return normalize(item) or {}

