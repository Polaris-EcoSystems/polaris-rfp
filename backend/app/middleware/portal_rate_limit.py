from __future__ import annotations

import time
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..settings import settings


@dataclass
class _Bucket:
    window_start: float
    count: int


class PortalRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Lightweight, best-effort rate limit for public client portal endpoints.
    This is in-memory per process (good enough to discourage abuse).
    """

    _buckets: dict[str, _Bucket] = {}

    def _client_key(self, request: Request) -> str:
        # Prefer X-Forwarded-For (ALB/CloudFront), fallback to client.host.
        xff = (request.headers.get("x-forwarded-for") or "").strip()
        ip = xff.split(",")[0].strip() if xff else ""
        if not ip:
            try:
                ip = request.client.host if request.client else ""
            except Exception:
                ip = ""
        ip = ip or "unknown"

        # Include token prefix to dampen brute-force against one token.
        path = str(getattr(request.url, "path", "") or "")
        tok = ""
        if path.startswith("/api/client/portal/"):
            rest = path[len("/api/client/portal/") :]
            tok = rest.split("/")[0].strip()
        tok_prefix = tok[:8] if tok else "none"
        return f"{ip}:{tok_prefix}"

    async def dispatch(self, request: Request, call_next) -> Response:
        path = str(getattr(request.url, "path", "") or "")
        if not path.startswith("/api/client/portal/"):
            return await call_next(request)

        rpm = int(getattr(settings, "portal_rate_limit_rpm", 120) or 120)
        rpm = max(1, min(6000, rpm))
        window_s = 60.0
        key = self._client_key(request)
        now = time.time()

        b = self._buckets.get(key)
        if not b or (now - b.window_start) >= window_s:
            b = _Bucket(window_start=now, count=0)
            self._buckets[key] = b

        b.count += 1
        if b.count > rpm:
            retry_after = int(max(1.0, window_s - (now - b.window_start)))
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

