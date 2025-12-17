from __future__ import annotations

from fastapi import HTTPException, Request


PUBLIC_PATH_PREFIXES = (
    "/",
    "/api/auth",
)


def is_public_path(path: str) -> bool:
    # "GET /" health is public.
    # All /api/auth/* endpoints are public.
    return path == "/" or path.startswith("/api/auth")


async def require_auth(request: Request):
    # Placeholder: will be replaced with Cognito JWT validation.
    # For now, enforce that protected endpoints have an Authorization header.
    if is_public_path(request.url.path):
        return

    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        raise HTTPException(status_code=401, detail="Unauthorized")
