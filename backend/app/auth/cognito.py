from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from cachetools import TTLCache
from jose import jwt
from jose.exceptions import JWTError

from app.settings import settings
from app.infrastructure import cognito_idp


@dataclass
class VerifiedUser:
    sub: str
    username: str
    email: str | None
    claims: dict[str, Any]


_JWKS_CACHE: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=4, ttl=60 * 60)
_USER_ATTR_CACHE: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=2048, ttl=5 * 60)


class CognitoAuthError(Exception):
    """
    Base class for auth-related errors with a suggested HTTP status code.
    """

    status_code: int = 401

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message)


class CognitoTokenError(CognitoAuthError):
    status_code = 401


class CognitoConfigError(CognitoAuthError):
    status_code = 500


class CognitoJWKSError(CognitoAuthError):
    status_code = 503


def _issuer() -> str:
    if not settings.cognito_user_pool_id:
        raise CognitoConfigError("COGNITO_USER_POOL_ID is not set")
    region = settings.cognito_region or settings.aws_region
    return f"https://cognito-idp.{region}.amazonaws.com/{settings.cognito_user_pool_id}"


def _jwks_url() -> str:
    return f"{_issuer()}/.well-known/jwks.json"


_HTTP: httpx.Client | None = None


def _http_client() -> httpx.Client:
    global _HTTP
    if _HTTP is None:
        _HTTP = httpx.Client(timeout=10.0, headers={"User-Agent": "polaris-rfp-backend"})
    return _HTTP


def _get_jwks() -> dict[str, Any]:
    url = _jwks_url()
    cached = _JWKS_CACHE.get(url)
    if cached:
        return cached

    try:
        resp = _http_client().get(url)
        resp.raise_for_status()
        jwks = resp.json()
        if not isinstance(jwks, dict) or "keys" not in jwks:
            raise CognitoJWKSError("Invalid JWKS response")
    except httpx.HTTPError as e:
        raise CognitoJWKSError(f"Failed to fetch JWKS: {e}") from e

    _JWKS_CACHE[url] = jwks
    return jwks


def verify_bearer_token(token: str) -> VerifiedUser:
    if not token:
        raise CognitoTokenError("missing token")
    if not settings.cognito_client_id:
        raise CognitoConfigError("COGNITO_CLIENT_ID is not set")

    jwks = _get_jwks()
    issuer = _issuer()

    # Validate signature + issuer. We do *not* rely on JWT library audience handling
    # because Cognito access tokens commonly use `client_id` (not `aud`).
    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False, "verify_iss": True},
        )
    except JWTError as e:
        raise CognitoTokenError("invalid token") from e

    # Basic expiry check (jwt.decode already verifies exp, but keep explicit for clarity)
    exp = claims.get("exp")
    if exp and int(exp) < int(time.time()):
        raise CognitoTokenError("token expired")

    token_use = claims.get("token_use")
    if token_use and token_use not in ("id", "access"):
        raise CognitoTokenError("invalid token_use")

    # Enforce this token was minted for our app client.
    client_id = str(settings.cognito_client_id or "").strip()
    if token_use == "id":
        aud = str(claims.get("aud") or "").strip()
        if not aud or aud != client_id:
            raise CognitoTokenError("invalid audience")
    elif token_use == "access":
        cid = str(claims.get("client_id") or "").strip()
        # Some Cognito configurations may also include aud; accept either as long as it matches.
        aud = str(claims.get("aud") or "").strip()
        if not ((cid and cid == client_id) or (aud and aud == client_id)):
            raise CognitoTokenError("invalid client_id")

    sub = str(claims.get("sub") or "")
    if not sub:
        raise CognitoTokenError("missing sub")

    email = claims.get("email")
    if email is not None:
        email = str(email)

    # Access tokens often omit email/name fields; enrich from Cognito AdminGetUser (cached).
    if token_use == "access":
        pool_id = str(settings.cognito_user_pool_id or "").strip()
        # Determine Cognito username for lookup (prefer explicit claim).
        cognito_username = (
            str(claims.get("cognito:username") or "").strip()
            or str(claims.get("username") or "").strip()
            or str(claims.get("preferred_username") or "").strip()
            or (str(email).strip() if email else "")
        )
        if cognito_username and pool_id:
            cached = _USER_ATTR_CACHE.get(cognito_username)
            if cached is None:
                try:
                    resp = cognito_idp.admin_get_user(
                        user_pool_id=pool_id,
                        username=cognito_username,
                    )
                    attrs_list = resp.get("UserAttributes") or []
                    attrs: dict[str, str] = {}
                    for a in attrs_list:
                        n = str(a.get("Name") or "").strip()
                        if not n:
                            continue
                        v = a.get("Value")
                        attrs[n] = "" if v is None else str(v)
                    cached = attrs
                    _USER_ATTR_CACHE[cognito_username] = attrs
                except Exception:
                    cached = {}
            # Fill missing fields.
            if not email and cached.get("email"):
                email = str(cached.get("email"))
            for k in ("given_name", "family_name", "name", "preferred_username", "cognito:username"):
                if k not in claims and cached.get(k):
                    claims[k] = cached.get(k)

    username = (
        str(claims.get("preferred_username") or "").strip()
        or str(claims.get("cognito:username") or "").strip()
        or (email or "")
    )

    return VerifiedUser(sub=sub, username=username, email=email, claims=claims)
