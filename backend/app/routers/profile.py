from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..infrastructure import cognito_idp
from ..settings import settings

router = APIRouter(tags=["profile"])


def _require_cognito_configured():
    if not settings.cognito_user_pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")


def _current_cognito_username(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Prefer explicit Cognito username from token (works even if email is mutable).
    claims = getattr(user, "claims", {}) or {}
    cognito_username = str(claims.get("cognito:username") or "").strip()
    if cognito_username:
        return cognito_username

    # Fallbacks (common in our pool where UsernameAttributes = [email])
    if getattr(user, "email", None):
        return str(user.email).strip()
    return str(user.username).strip()


def _get_profile_payload(request: Request) -> dict[str, Any]:
    _require_cognito_configured()
    pool_id = str(settings.cognito_user_pool_id or "").strip()
    if not pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")

    verified_user = getattr(request.state, "user", None)
    if not verified_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    username = _current_cognito_username(request)

    try:
        user_resp = cognito_idp.admin_get_user(user_pool_id=pool_id, username=username)
    except Exception:
        # Don't leak AWS internals; treat as not found / misconfigured
        raise HTTPException(status_code=404, detail="User not found")

    attrs_list = user_resp.get("UserAttributes") or []
    attrs: dict[str, str] = {}
    for a in attrs_list:
        name = str(a.get("Name") or "").strip()
        if not name:
            continue
        value = a.get("Value")
        attrs[name] = "" if value is None else str(value)

    # Pool schema is the best available source of mutable/required flags for custom attributes.
    schema: list[dict[str, Any]] = []
    schema_map: dict[str, dict[str, Any]] = {}
    try:
        pool = cognito_idp.describe_user_pool(user_pool_id=pool_id)
        for s in (pool.get("UserPool") or {}).get("SchemaAttributes") or []:
            name = str(s.get("Name") or "").strip()
            if not name:
                continue
            meta = {
                "name": name,
                "required": bool(s.get("Required") or False),
                "mutable": bool(s.get("Mutable") or False),
            }
            schema.append(meta)
            schema_map[name] = meta
    except Exception:
        # Schema is optional; the API can still function without it.
        schema = []
        schema_map = {}

    # Build an "attributes" list that includes current values and editability metadata.
    attributes: list[dict[str, Any]] = []
    for name, value in sorted(attrs.items(), key=lambda kv: kv[0]):
        meta = schema_map.get(name) or {"name": name, "required": False, "mutable": False}
        attributes.append(
            {
                "name": name,
                "value": value,
                "required": bool(meta.get("required")),
                "mutable": bool(meta.get("mutable")),
            }
        )

    # Also include any schema-defined attributes that aren't present yet.
    for s in schema:
        n = s["name"]
        if n not in attrs:
            attributes.append(
                {
                    "name": n,
                    "value": "",
                    "required": bool(s.get("required")),
                    "mutable": bool(s.get("mutable")),
                }
            )

    # Sort: mutable first, then required, then name.
    attributes.sort(key=lambda a: (0 if a.get("mutable") else 1, 0 if a.get("required") else 1, a["name"]))

    claims = getattr(verified_user, "claims", {}) or {}
    return {
        "user": {
            "sub": verified_user.sub,
            "username": verified_user.username,
            "email": verified_user.email,
            "cognito_username": username,
        },
        "claims": claims,
        "attributes": attributes,
        "schema": schema,
    }


@router.get("")
@router.get("/")
def get_profile(request: Request):
    return _get_profile_payload(request)


class AttributeUpdate(BaseModel):
    name: str = Field(..., min_length=1)
    value: str | None = None


class UpdateAttributesRequest(BaseModel):
    attributes: list[AttributeUpdate] = Field(default_factory=list)


@router.put("/attributes")
def update_attributes(body: UpdateAttributesRequest, request: Request):
    _require_cognito_configured()
    pool_id = str(settings.cognito_user_pool_id or "").strip()
    if not pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")
    username = _current_cognito_username(request)

    to_update: dict[str, str] = {}
    to_delete: list[str] = []

    for a in body.attributes or []:
        name = str(a.name).strip()
        if not name:
            continue
        if a.value is None:
            to_delete.append(name)
        else:
            to_update[name] = str(a.value)

    try:
        if to_update:
            cognito_idp.admin_update_user_attributes(
                user_pool_id=pool_id,
                username=username,
                attributes=to_update,
            )
        if to_delete:
            cognito_idp.admin_delete_user_attributes(
                user_pool_id=pool_id,
                username=username,
                attribute_names=to_delete,
            )
    except Exception as _e:
        raise HTTPException(status_code=400, detail="Failed to update attributes")

    # Return refreshed state
    return _get_profile_payload(request)


@router.delete("/attributes/{name}")
def delete_attribute(name: str, request: Request):
    _require_cognito_configured()
    pool_id = str(settings.cognito_user_pool_id or "").strip()
    if not pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")
    username = _current_cognito_username(request)

    attr = str(name or "").strip()
    if not attr:
        raise HTTPException(status_code=400, detail="Attribute name is required")

    try:
        cognito_idp.admin_delete_user_attributes(
            user_pool_id=pool_id,
            username=username,
            attribute_names=[attr],
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to delete attribute")

    return _get_profile_payload(request)




