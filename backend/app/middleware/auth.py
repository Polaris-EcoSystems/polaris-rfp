from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..auth.cognito import verify_bearer_token


def is_public_path(path: str) -> bool:
    # "GET /" health is public.
    if path == "/":
        return True

    # Keep compatibility with legacy backend:
    # /api/auth/me is protected, but auth entrypoints are public.
    if path.startswith("/api/auth/") and path not in ("/api/auth/me",):
        return True

    return False


async def require_auth(request: Request):
    path = request.url.path

    # Let CORS preflight through without auth.
    # CORSMiddleware will handle preflight and add headers.
    if request.method.upper() == "OPTIONS":
        return

    # Only enforce auth for API routes. Non-API paths should return legacy 404s.
    if not path.startswith("/api/"):
        return

    if is_public_path(path):
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


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Auth enforcement as ASGI middleware.

    Important: this should be added *before* CORSMiddleware so CORS wraps all
    responses (including auth failures) and preflight works.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            await require_auth(request)
        except Exception as exc:
            status_code = getattr(exc, "status_code", 500)
            detail = getattr(exc, "detail", "Unauthorized")
            return ORJSONResponse(
                status_code=int(status_code),
                content={"error": detail if isinstance(detail, str) else "Unauthorized"},
            )
        return await call_next(request)
