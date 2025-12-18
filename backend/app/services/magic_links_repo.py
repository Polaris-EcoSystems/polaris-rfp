from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

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
    table().put_item(Item=item)
    return item


def get_latest_magic_session_for_email(*, email: str) -> dict[str, Any] | None:
    resp = table().query(
        KeyConditionExpression=Key("pk").eq(f"EMAIL#{email.lower()}")
        & Key("sk").begins_with("SESSION#"),
        ScanIndexForward=False,
        Limit=1,
    )
    items = resp.get("Items") or []
    if not items:
        return None
    item = items[0]
    try:
        if int(item.get("expiresAt") or 0) <= int(time.time()):
            return None
    except Exception:
        return None
    return item


def delete_magic_session_for_email(*, email: str, sk: str) -> None:
    table().delete_item(Key={"pk": f"EMAIL#{email.lower()}", "sk": sk})


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


