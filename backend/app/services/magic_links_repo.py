from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

import boto3

from ..settings import settings


@lru_cache(maxsize=1)
def table():
    if not settings.magic_link_table_name:
        raise RuntimeError("MAGIC_LINK_TABLE_NAME is not configured")
    return boto3.resource("dynamodb", region_name=settings.aws_region).Table(
        settings.magic_link_table_name
    )


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
    table().put_item(Item=item)
    return item


def get_magic_session(*, magic_id: str) -> dict[str, Any] | None:
    resp = table().get_item(Key={"pk": f"MAGIC#{magic_id}", "sk": "SESSION"})
    item = resp.get("Item")
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
    table().delete_item(Key={"pk": f"MAGIC#{magic_id}", "sk": "SESSION"})

