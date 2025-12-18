from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import ORJSONResponse

from .settings import get_settings

PROBLEM_JSON = "application/problem+json"


def _default_title(status_code: int) -> str:
    if status_code == 400:
        return "Bad Request"
    if status_code == 401:
        return "Unauthorized"
    if status_code == 403:
        return "Forbidden"
    if status_code == 404:
        return "Not Found"
    if status_code == 405:
        return "Method Not Allowed"
    if status_code == 409:
        return "Conflict"
    if status_code == 422:
        return "Unprocessable Entity"
    if status_code >= 500:
        return "Internal Server Error"
    return "Error"


def _request_id(request: Request) -> str | None:
    rid = getattr(getattr(request, "state", None), "request_id", None)
    if rid:
        return str(rid)
    hdr = request.headers.get("x-request-id") or request.headers.get("X-Request-Id")
    return str(hdr) if hdr else None


def problem_payload(
    *,
    request: Request,
    status_code: int,
    title: str | None = None,
    detail: str | None = None,
    type: str = "about:blank",
    instance: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": type or "about:blank",
        "title": title or _default_title(int(status_code)),
        "status": int(status_code),
    }

    if detail:
        payload["detail"] = str(detail)

    inst = instance or str(getattr(request.url, "path", "") or "")
    if inst:
        payload["instance"] = inst

    rid = _request_id(request)
    if rid:
        payload["requestId"] = rid

    if errors:
        payload["errors"] = errors

    if extensions:
        # RFC7807 allows extension members; keep them in a single namespace to
        # avoid collisions with reserved keys.
        payload["extensions"] = extensions

    return payload


def problem_response(
    *,
    request: Request,
    status_code: int,
    title: str | None = None,
    detail: str | None = None,
    type: str = "about:blank",
    instance: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    extensions: dict[str, Any] | None = None,
) -> ORJSONResponse:
    settings = get_settings()

    # Never leak internal details in production for server errors.
    safe_detail = detail
    if int(status_code) >= 500 and settings.is_production:
        safe_detail = None

    return ORJSONResponse(
        status_code=int(status_code),
        content=problem_payload(
            request=request,
            status_code=int(status_code),
            title=title,
            detail=safe_detail,
            type=type,
            instance=instance,
            errors=errors,
            extensions=extensions,
        ),
        media_type=PROBLEM_JSON,
    )

