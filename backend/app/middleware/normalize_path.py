from __future__ import annotations

from typing import Callable, Awaitable, Any


class NormalizePathMiddleware:
    """
    Normalize incoming request paths to avoid hard 404s when clients/proxies append
    trailing slashes.

    Why:
    - The app runs with FastAPI `redirect_slashes=False` to avoid 307/308 redirect
      loops through proxies (and issues with large uploads).
    - Some clients still normalize URLs by adding a trailing slash.
    - Instead of redirecting, we rewrite the ASGI scope path in-place (no extra RTT).
    """

    def __init__(self, app: Callable[..., Awaitable[Any]]):
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable):
        if scope.get("type") == "http":
            path = str(scope.get("path") or "")
            if path and path != "/" and path.endswith("/"):
                # Only normalize API-ish paths; avoid surprising behavior for non-API routes.
                if path.startswith("/api/") or path.startswith("/googledrive/"):
                    new_path = path.rstrip("/")
                    scope["path"] = new_path
                    # Starlette/FastAPI route matching uses `scope["path"]`.
                    # Keep raw_path consistent when present.
                    raw_path = scope.get("raw_path")
                    if isinstance(raw_path, (bytes, bytearray)):
                        try:
                            scope["raw_path"] = new_path.encode("utf-8")
                        except Exception:
                            pass
        return await self.app(scope, receive, send)


