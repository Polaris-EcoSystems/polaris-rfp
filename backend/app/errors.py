from __future__ import annotations

from fastapi import Request
from fastapi.responses import ORJSONResponse


def http_404_handler(_: Request, __):
    # Match legacy Express behavior
    return ORJSONResponse(status_code=404, content={"error": "Route not found"})


def http_500_handler(request: Request, exc: Exception):
    # Match legacy Express behavior:
    # - Always return { error, message }
    # - Hide internal error details in production
    from .settings import settings

    msg = str(exc) if settings.environment == "development" else "Internal server error"
    return ORJSONResponse(
        status_code=500,
        content={"error": "Something went wrong!", "message": msg},
    )
