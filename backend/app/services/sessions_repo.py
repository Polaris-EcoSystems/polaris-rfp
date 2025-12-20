from __future__ import annotations

import hashlib
import ipaddress
import time
from typing import Any

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table
from ..services.token_crypto import decrypt_string, encrypt_string


def session_key(*, sid: str) -> dict[str, str]:
    s = str(sid or "").strip()
    if not s:
        raise ValueError("sid is required")
    return {"pk": f"SESSION#{s}", "sk": "v1"}


def put_session(
    *,
    sid: str,
    refresh_token_enc: str,
    expires_at: int,
    session_kind: str,
    sub: str | None = None,
    email: str | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    """
    Stores a refreshable session server-side.

    `expires_at` must be epoch seconds and is used as DynamoDB TTL (`expiresAt`).
    """
    now = int(time.time())
    ua = str(user_agent or "").strip()
    ua_hash = (
        hashlib.sha256(ua.encode("utf-8")).hexdigest() if ua else None
    )

    ip_prefix: str | None = None
    try:
        if ip:
            addr = ipaddress.ip_address(str(ip))
            if addr.version == 4:
                net = ipaddress.ip_network(f"{addr}/24", strict=False)
                ip_prefix = str(net.network_address) + "/24"
            else:
                net = ipaddress.ip_network(f"{addr}/64", strict=False)
                ip_prefix = str(net.network_address) + "/64"
    except Exception:
        ip_prefix = None

    item: dict[str, Any] = {
        **session_key(sid=sid),
        "sid": str(sid),
        "sessionKind": str(session_kind or "normal"),
        "refreshTokenEnc": str(refresh_token_enc),
        "expiresAt": int(expires_at),
        "createdAt": now,
        "updatedAt": now,
        "lastSeenAt": now,
    }
    if sub:
        item["sub"] = str(sub)
        item["gsi1pk"] = f"USER#{str(sub)}"
        item["gsi1sk"] = f"SESSION#{now}#{str(sid)}"
    if email:
        item["email"] = str(email).strip().lower()
    if ua:
        item["userAgent"] = ua[:512]
    if ua_hash:
        item["userAgentHash"] = ua_hash
    if ip_prefix:
        item["ipPrefix"] = ip_prefix

    get_main_table().put_item(item=item)
    return item


def get_session(*, sid: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key=session_key(sid=sid))


def touch_session(
    *,
    sid: str,
    refresh_token_enc: str | None = None,
    last_seen_at: int | None = None,
) -> dict[str, Any] | None:
    """
    Best-effort: update updatedAt and optionally replace refreshTokenEnc (if rotated).
    """
    now = int(time.time())
    expr = ["updatedAt = :u"]
    vals: dict[str, Any] = {":u": now}
    if last_seen_at:
        expr.append("lastSeenAt = :ls")
        vals[":ls"] = int(last_seen_at)
    if refresh_token_enc:
        expr.append("refreshTokenEnc = :rt")
        vals[":rt"] = str(refresh_token_enc)

    return get_main_table().update_item(
        key=session_key(sid=sid),
        update_expression="SET " + ", ".join(expr),
        expression_attribute_names=None,
        expression_attribute_values=vals,
        return_values="ALL_NEW",
    )


def delete_session(*, sid: str) -> None:
    get_main_table().delete_item(key=session_key(sid=sid))


def list_sessions_for_user(*, sub: str, limit: int = 25) -> list[dict[str, Any]]:
    """
    Returns newest-first sessions for a user.
    """
    s = str(sub or "").strip()
    if not s:
        return []
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(f"USER#{s}")
        & Key("gsi1sk").begins_with("SESSION#"),
        scan_index_forward=False,
        limit=max(1, min(100, int(limit or 25))),
        next_token=None,
    )
    return list(pg.items or [])


def try_get_recent_cached_access_token(
    *,
    sid: str,
    max_age_seconds: int = 90,
) -> str | None:
    """
    Best-effort: return a recently-minted access token cached on the session record.
    Used to avoid refresh stampedes when many requests hit 401 concurrently.
    """
    it = get_session(sid=sid)
    if not it:
        return None
    try:
        issued_at = int(it.get("lastAccessTokenIssuedAt") or 0)
        if issued_at <= 0:
            return None
        if int(time.time()) - issued_at > int(max_age_seconds):
            return None
    except Exception:
        return None
    tok_enc = str(it.get("lastAccessTokenEnc") or "")
    tok = decrypt_string(tok_enc)
    return str(tok) if tok else None


def try_acquire_refresh_lock(*, sid: str, lock_seconds: int = 10) -> bool:
    """
    Acquire a short-lived lock on a session record to ensure only one refresh call
    hits Cognito at a time.
    """
    now = int(time.time())
    until = now + max(2, min(30, int(lock_seconds)))
    try:
        get_main_table().update_item(
            key=session_key(sid=sid),
            update_expression="SET refreshLockUntil = :u, updatedAt = :now",
            expression_attribute_names=None,
            expression_attribute_values={":u": until, ":now": now},
            condition_expression="attribute_not_exists(refreshLockUntil) OR refreshLockUntil < :now",
            return_values="NONE",
        )
        return True
    except Exception:
        return False


def release_refresh_lock(*, sid: str) -> None:
    now = int(time.time())
    # There's no REMOVE support in our helper (we could add it), so set it to now.
    try:
        get_main_table().update_item(
            key=session_key(sid=sid),
            update_expression="SET refreshLockUntil = :now, updatedAt = :now",
            expression_attribute_names=None,
            expression_attribute_values={":now": now},
            return_values="NONE",
        )
    except Exception:
        pass


def cache_access_token(*, sid: str, access_token: str) -> None:
    now = int(time.time())
    enc = encrypt_string(str(access_token))
    if not enc:
        return
    try:
        get_main_table().update_item(
            key=session_key(sid=sid),
            update_expression=(
                "SET lastAccessTokenEnc = :t, lastAccessTokenIssuedAt = :i, "
                "updatedAt = :u, lastSeenAt = :u"
            ),
            expression_attribute_names=None,
            expression_attribute_values={":t": str(enc), ":i": now, ":u": now},
            return_values="NONE",
        )
    except Exception:
        pass


