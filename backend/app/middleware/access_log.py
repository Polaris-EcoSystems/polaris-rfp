from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.logging import get_logger


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    Structured access logs (JSON) for every request.
    """

    def __init__(self, app, *, exclude_paths: set[str] | None = None):
        super().__init__(app)
        self._exclude = exclude_paths or set()
        self._log = get_logger("access")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self._exclude:
            return await call_next(request)

        start = time.perf_counter()
        method = request.method.upper()
        client = getattr(request, "client", None)
        client_host = getattr(client, "host", None) if client else None

        try:
            response = await call_next(request)
            user = getattr(getattr(request, "state", None), "user", None)
            user_sub = getattr(user, "sub", None) if user else None
            dur_ms = (time.perf_counter() - start) * 1000.0
            self._log.info(
                "request",
                http_method=method,
                path=path,
                status_code=int(getattr(response, "status_code", 0) or 0),
                duration_ms=round(dur_ms, 2),
                client_ip=client_host,
                user_sub=str(user_sub) if user_sub else None,
            )
            return response
        except Exception:
            user = getattr(getattr(request, "state", None), "user", None)
            user_sub = getattr(user, "sub", None) if user else None
            dur_ms = (time.perf_counter() - start) * 1000.0
            self._log.exception(
                "request_error",
                http_method=method,
                path=path,
                duration_ms=round(dur_ms, 2),
                client_ip=client_host,
                user_sub=str(user_sub) if user_sub else None,
            )
            raise





