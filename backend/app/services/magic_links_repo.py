from __future__ import annotations

import time
from typing import Any

from boto3.dynamodb.conditions import Key

from ..settings import settings
from ..db.dynamodb.table import get_table


def _table():
    if not settings.magic_link_table_name:
        raise RuntimeError("MAGIC_LINK_TABLE_NAME is not configured")
    return get_table(settings.magic_link_table_name)


def put_magic_session(
    *,
    magic_id: str,
    email: str,
    session: str,
    return_to: str | None,
    ttl_seconds: int = 600,
) -> dict[str, Any]:
    now = int(time.time())
    expires_at = now + int(ttl_seconds)
    item: dict[str, Any] = {
        "pk": f"MAGIC#{magic_id}",
        "sk": "SESSION",
        "magicId": magic_id,
        "email": email,
        "session": session,
        "returnTo": return_to or "/",
        # DynamoDB TTL attribute must be epoch seconds
        "expiresAt": expires_at,
        "createdAt": now,
        "updatedAt": now,
    }
    _table().put_item(item=item)
    return item


def put_magic_session_for_email(
    *,
    email: str,
    session: str,
    return_to: str | None,
    ttl_seconds: int = 600,
) -> dict[str, Any]:
    now = int(time.time())
    expires_at = now + int(ttl_seconds)
    item: dict[str, Any] = {
        "pk": f"EMAIL#{email.lower()}",
        "sk": f"SESSION#{now}",
        "email": email.lower(),
        "session": session,
        "returnTo": return_to or "/",
        "expiresAt": expires_at,
        "createdAt": now,
        "updatedAt": now,
    }
    _table().put_item(item=item)
    return item


def get_latest_magic_session_for_email(*, email: str) -> dict[str, Any] | None:
    pg = _table().query_page(
        key_condition_expression=Key("pk").eq(f"EMAIL#{email.lower()}")
        & Key("sk").begins_with("SESSION#"),
        scan_index_forward=False,
        limit=1,
        next_token=None,
    )
    items = pg.items or []
    if not items:
        return None
    item = items[0]
    try:
        if int(item.get("expiresAt") or 0) <= int(time.time()):
            return None
    except Exception:
        return None
    return item


def get_recent_magic_sessions_for_email(
    *, email: str, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Returns up to `limit` most-recent (non-expired) magic sessions for an email.
    Used to make email-only magic links robust if multiple sessions exist.
    """
    lim = max(1, min(int(limit or 5), 25))
    pg = _table().query_page(
        key_condition_expression=Key("pk").eq(f"EMAIL#{email.lower()}")
        & Key("sk").begins_with("SESSION#"),
        scan_index_forward=False,
        limit=lim,
        next_token=None,
    )
    items = list(pg.items or [])
    if not items:
        return []

    now = int(time.time())
    out: list[dict[str, Any]] = []
    for it in items:
        try:
            if int(it.get("expiresAt") or 0) <= now:
                continue
        except Exception:
            continue
        out.append(it)
    return out


def delete_magic_session_for_email(*, email: str, sk: str) -> None:
    _table().delete_item(key={"pk": f"EMAIL#{email.lower()}", "sk": sk})


def get_magic_session(*, magic_id: str) -> dict[str, Any] | None:
    item = _table().get_item(key={"pk": f"MAGIC#{magic_id}", "sk": "SESSION"})
    if not item:
        return None
    # TTL is enforced asynchronously; also enforce in app
    try:
        if int(item.get("expiresAt") or 0) <= int(time.time()):
            return None
    except Exception:
        return None
    return item


def delete_magic_session(*, magic_id: str) -> None:
    _table().delete_item(key={"pk": f"MAGIC#{magic_id}", "sk": "SESSION"})


