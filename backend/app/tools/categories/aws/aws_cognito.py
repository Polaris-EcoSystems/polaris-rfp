from __future__ import annotations

from typing import Any

from ....settings import settings
from ....infrastructure.allowlist import parse_csv, uniq
from ....infrastructure.aws_clients import cognito_idp_client


def _allowed_user_pools() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_cognito_user_pool_ids))
    if explicit:
        return explicit
    return uniq([str(settings.cognito_user_pool_id or "").strip()])


def _resolve_pool(user_pool_id: str | None) -> str:
    up = str(user_pool_id or "").strip() or str(settings.cognito_user_pool_id or "").strip()
    if not up:
        raise ValueError("missing_userPoolId")
    allowed = [x for x in _allowed_user_pools() if x]
    if allowed and up not in allowed:
        raise ValueError("user_pool_not_allowed")
    return up


def describe_user_pool(*, user_pool_id: str | None = None) -> dict[str, Any]:
    up = _resolve_pool(user_pool_id)
    resp = cognito_idp_client().describe_user_pool(UserPoolId=up)
    pool = resp.get("UserPool") if isinstance(resp, dict) else None
    if not isinstance(pool, dict):
        return {"ok": False, "error": "not_found"}
    # Bound fields.
    keys = [
        "Id",
        "Name",
        "Status",
        "CreationDate",
        "LastModifiedDate",
        "UsernameAttributes",
        "AutoVerifiedAttributes",
        "MfaConfiguration",
        "LambdaConfig",
    ]
    out: dict[str, Any] = {}
    for k in keys:
        if k in pool:
            out[k] = pool.get(k)
    return {"ok": True, "userPoolId": up, "userPool": out}


def admin_get_user(*, username: str, user_pool_id: str | None = None) -> dict[str, Any]:
    up = _resolve_pool(user_pool_id)
    un = str(username or "").strip()
    if not un:
        return {"ok": False, "error": "missing_username"}
    resp = cognito_idp_client().admin_get_user(UserPoolId=up, Username=un)
    attrs = resp.get("UserAttributes") if isinstance(resp, dict) else None
    a = attrs if isinstance(attrs, list) else []
    # Convert attribute list to dict (bounded)
    attr_map: dict[str, str] = {}
    for it in a[:50]:
        if not isinstance(it, dict):
            continue
        n = str(it.get("Name") or "").strip()
        v = str(it.get("Value") or "").strip()
        if n and n not in attr_map:
            attr_map[n] = v[:500]
    return {
        "ok": True,
        "userPoolId": up,
        "username": resp.get("Username"),
        "userStatus": resp.get("UserStatus"),
        "enabled": resp.get("Enabled"),
        "userCreateDate": str(resp.get("UserCreateDate") or "") or None,
        "userLastModifiedDate": str(resp.get("UserLastModifiedDate") or "") or None,
        "attributes": attr_map,
    }


def list_users(*, user_pool_id: str | None = None, limit: int = 20, pagination_token: str | None = None, filter: str | None = None) -> dict[str, Any]:
    up = _resolve_pool(user_pool_id)
    lim = max(1, min(50, int(limit or 20)))
    token = str(pagination_token or "").strip() or None
    flt = str(filter or "").strip() or None
    kwargs: dict[str, Any] = {"UserPoolId": up, "Limit": lim}
    if token:
        kwargs["PaginationToken"] = token
    if flt:
        kwargs["Filter"] = flt[:250]
    resp = cognito_idp_client().list_users(**kwargs)
    users = resp.get("Users") if isinstance(resp, dict) else None
    rows = users if isinstance(users, list) else []
    out: list[dict[str, Any]] = []
    for u in rows[:lim]:
        if not isinstance(u, dict):
            continue
        out.append(
            {
                "username": u.get("Username"),
                "enabled": u.get("Enabled"),
                "userStatus": u.get("UserStatus"),
                "userCreateDate": str(u.get("UserCreateDate") or "") or None,
                "userLastModifiedDate": str(u.get("UserLastModifiedDate") or "") or None,
            }
        )
    nxt = str(resp.get("PaginationToken") or "").strip() or None
    return {"ok": True, "userPoolId": up, "users": out, "nextToken": nxt}


def admin_disable_user(*, username: str, user_pool_id: str | None = None) -> dict[str, Any]:
    up = _resolve_pool(user_pool_id)
    un = str(username or "").strip()
    if not un:
        return {"ok": False, "error": "missing_username"}
    cognito_idp_client().admin_disable_user(UserPoolId=up, Username=un)
    return {"ok": True, "userPoolId": up, "username": un, "disabled": True}


def admin_enable_user(*, username: str, user_pool_id: str | None = None) -> dict[str, Any]:
    up = _resolve_pool(user_pool_id)
    un = str(username or "").strip()
    if not un:
        return {"ok": False, "error": "missing_username"}
    cognito_idp_client().admin_enable_user(UserPoolId=up, Username=un)
    return {"ok": True, "userPoolId": up, "username": un, "enabled": True}

