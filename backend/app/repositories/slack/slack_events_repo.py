from __future__ import annotations

import time
from typing import Any

from ..db.dynamodb.errors import DdbConflict
from ..db.dynamodb.table import get_main_table


def _key(event_id: str) -> dict[str, str]:
    eid = str(event_id or "").strip()
    if not eid:
        raise ValueError("event_id is required")
    return {"pk": f"SLACK_EVENT#{eid}", "sk": "PROFILE"}


def mark_seen(*, event_id: str, ttl_seconds: int = 600) -> bool:
    """
    Best-effort idempotency marker.

    Returns:
      True if this is the first time we saw the event_id; False if already seen.
    """
    eid = str(event_id or "").strip()
    if not eid:
        return True

    expires_at = int(time.time()) + max(60, min(60 * 60, int(ttl_seconds or 600)))
    item: dict[str, Any] = {
        **_key(eid),
        "entityType": "SlackEvent",
        "eventId": eid,
        "createdAt": int(time.time()),
        "expiresAt": int(expires_at),
    }
    try:
        get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
        return True
    except DdbConflict:
        return False
    except Exception:
        # If Dynamo is unavailable, fail open to avoid breaking Slack.
        return True

