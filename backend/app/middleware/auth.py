from __future__ import annotations

from fastapi import HTTPException, Request

from ..auth.cognito import verify_bearer_token


def is_public_path(path: str) -> bool:
    # "GET /" health is public.
    if path == "/":
        return True

    # Keep compatibility with legacy backend:
    # /api/auth/me is protected, but auth entrypoints are public.
    if path in (
        "/api/auth/login",
        "/api/auth/signup",
        "/api/auth/request-password-reset",
        "/api/auth/reset-password",
    ):
        return True

    return False


async def require_auth(request: Request):
    if is_public_path(request.url.path):
        return

    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        raise HTTPException(status_code=401, detail="Unauthorized")

    parts = str(auth).split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = parts[1].strip()
    try:
        user = verify_bearer_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

    request.state.user = user
