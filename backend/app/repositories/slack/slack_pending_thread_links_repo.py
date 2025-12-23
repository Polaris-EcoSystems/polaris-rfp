from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def pending_key(*, channel_id: str, slack_user_id: str) -> dict[str, str]:
    ch = str(channel_id or "").strip()
    u = str(slack_user_id or "").strip()
    if not ch:
        raise ValueError("channel_id is required")
    if not u:
        raise ValueError("slack_user_id is required")
    return {"pk": f"SLACKPENDINGLINK#{ch}#{u}", "sk": "PENDING"}


def create_pending_link(
    *,
    channel_id: str,
    slack_user_id: str,
    rfp_id: str,
    ttl_seconds: int = 10 * 60,
) -> dict[str, Any]:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    now = _now_iso()
    exp = int(time.time()) + max(60, min(24 * 60 * 60, int(ttl_seconds or 600)))
    item: dict[str, Any] = {
        **pending_key(channel_id=channel_id, slack_user_id=slack_user_id),
        "entityType": "SlackPendingThreadLink",
        "channelId": str(channel_id or "").strip(),
        "slackUserId": str(slack_user_id or "").strip(),
        "rfpId": rid,
        "createdAt": now,
        "expiresAt": exp,
        "gsi1pk": "TYPE#SLACK_PENDING_THREAD_LINK",
        "gsi1sk": f"{now}#{rid}",
    }
    get_main_table().put_item(item=item)
    return {k: v for k, v in item.items() if k not in ("pk", "sk")}


def get_pending_link(*, channel_id: str, slack_user_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=pending_key(channel_id=channel_id, slack_user_id=slack_user_id))
    if not it:
        return None
    out = dict(it)
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    return out


def consume_pending_link(*, channel_id: str, slack_user_id: str) -> dict[str, Any] | None:
    """
    Read+delete. Best-effort; if delete fails, still return the link.
    """
    it = get_pending_link(channel_id=channel_id, slack_user_id=slack_user_id)
    if not it:
        return None
    try:
        get_main_table().delete_item(key=pending_key(channel_id=channel_id, slack_user_id=slack_user_id))
    except Exception:
        pass
    return it

