from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from cachetools import TTLCache
from jose import jwt

from ..settings import settings


@dataclass
class VerifiedUser:
    sub: str
    username: str
    email: str | None
    claims: dict[str, Any]


_JWKS_CACHE: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=4, ttl=60 * 60)


def _issuer() -> str:
    if not settings.cognito_user_pool_id:
        raise RuntimeError("COGNITO_USER_POOL_ID is not set")
    region = settings.cognito_region or settings.aws_region
    return f"https://cognito-idp.{region}.amazonaws.com/{settings.cognito_user_pool_id}"


def _jwks_url() -> str:
    return f"{_issuer()}/.well-known/jwks.json"


def _get_jwks() -> dict[str, Any]:
    url = _jwks_url()
    cached = _JWKS_CACHE.get(url)
    if cached:
        return cached

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        jwks = resp.json()

    _JWKS_CACHE[url] = jwks
    return jwks


def verify_bearer_token(token: str) -> VerifiedUser:
    if not token:
        raise ValueError("missing token")
    if not settings.cognito_client_id:
        raise RuntimeError("COGNITO_CLIENT_ID is not set")

    jwks = _get_jwks()
    issuer = _issuer()

    # Cognito ID token is what the frontend stores as `access_token` for now.
    # Validate standard claims.
    claims = jwt.decode(
        token,
        jwks,
        algorithms=["RS256"],
        audience=settings.cognito_client_id,
        issuer=issuer,
        options={"verify_aud": True, "verify_iss": True},
    )

    # Basic expiry check (jwt.decode already verifies exp, but keep explicit for clarity)
    exp = claims.get("exp")
    if exp and int(exp) < int(time.time()):
        raise ValueError("token expired")

    token_use = claims.get("token_use")
    # Accept id tokens primarily; can loosen later.
    if token_use and token_use not in ("id", "access"):
        raise ValueError("invalid token_use")

    sub = str(claims.get("sub") or "")
    if not sub:
        raise ValueError("missing sub")

    email = claims.get("email")
    if email is not None:
        email = str(email)

    username = (
        str(claims.get("preferred_username") or "").strip()
        or str(claims.get("cognito:username") or "").strip()
        or (email or "")
    )

    return VerifiedUser(sub=sub, username=username, email=email, claims=claims)
