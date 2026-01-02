from __future__ import annotations

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from ..observability.context import request_id_var


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    - Accepts inbound X-Request-Id (if present) or generates a UUIDv4.
    - Stores it in request.state.request_id.
    - Exposes it via a contextvar so downstream logging can include it.
    - Always echoes X-Request-Id on the response.
    """

    header_name = "X-Request-Id"

    async def dispatch(self, request: Request, call_next):
        inbound = request.headers.get("x-request-id") or request.headers.get("X-Request-Id")
        request_id = (str(inbound).strip() if inbound else "") or str(uuid.uuid4())

        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers[self.header_name] = request_id
            return response
        finally:
            request_id_var.reset(token)





