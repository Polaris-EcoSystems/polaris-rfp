from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from .middleware.access_log import AccessLogMiddleware
from .middleware.auth import AuthMiddleware
from .middleware.cors import build_allowed_origin_regex, build_allowed_origins
from .middleware.portal_rate_limit import PortalRateLimitMiddleware
from .middleware.request_context import RequestContextMiddleware
from .observability.logging import configure_logging, get_logger
from .observability.otel import configure_otel, instrument_app
from .problem_details import problem_response
from .db.dynamodb.errors import (
    DdbConflict,
    DdbError,
    DdbNotFound,
    DdbThrottled,
    DdbUnavailable,
    DdbValidation,
 )
from .routers.health import router as health_router
from .routers.auth import router as auth_router
from .routers.content import router as content_router
from .routers.rfp import router as rfp_router
from .routers.attachments import router as attachments_router
from .routers.proposals import router as proposals_router
from .routers.templates import router as templates_router
from .routers.ai import router as ai_router
from .routers.ai_jobs import router as ai_jobs_router
from .routers.integrations_canva import router as canva_router
from .routers.integrations_slack import router as slack_router
from .routers.northstar_audit import router as northstar_audit_router
from .routers.profile import router as profile_router
from .routers.finder import router as finder_router
from .routers.tasks import router as tasks_router
from .routers.user_profile import router as user_profile_router
from .routers.contracting import router as contracting_router
from .routers.contract_templates import router as contract_templates_router
from .routers.client_portal import router as client_portal_router
from .settings import settings


def create_app() -> FastAPI:
    # Logging must be configured before the app starts handling requests.
    configure_logging(level="INFO")
    log = get_logger("startup")

    # Optional tracing (no-op unless OTEL_ENABLED=true)
    configure_otel(settings)

    app = FastAPI(
        title="Polaris RFP Backend",
        version="1.0.0",
        default_response_class=ORJSONResponse,
        # Avoid 307/308 redirects between /path and /path/ which can create
        # redirect loops when requests are proxied (e.g. via Next.js BFF).
        redirect_slashes=False,
    )

    allowed_origins = build_allowed_origins(
        frontend_base_url=settings.frontend_base_url,
        frontend_url=settings.frontend_url,
        frontend_urls=settings.frontend_urls,
    )

    log.info("app_starting", settings=settings.to_log_safe_dict())

    # Middlewares (order matters; last added is outermost)
    # Auth runs inside CORS so auth failures still get CORS headers.
    app.add_middleware(AuthMiddleware)
    # Best-effort throttling for public portal endpoints.
    app.add_middleware(PortalRateLimitMiddleware)
    # Access logs (structured JSON)
    app.add_middleware(AccessLogMiddleware, exclude_paths={"/"})
    # Use CORSMiddleware with both explicit allowlist AND wildcard regex support.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=build_allowed_origin_regex(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        expose_headers=["ETag"],
        max_age=3000,
    )
    # Outermost: request context (request-id) wraps everything.
    app.add_middleware(RequestContextMiddleware)

    # Error handlers
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DdbError, _ddb_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    # Routes
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(rfp_router, prefix="/api/rfp")
    app.include_router(attachments_router, prefix="/api/rfp")
    app.include_router(proposals_router, prefix="/api/proposals")
    app.include_router(templates_router, prefix="/api/templates")
    app.include_router(content_router, prefix="/api/content")
    app.include_router(ai_router, prefix="/api/ai")
    app.include_router(ai_jobs_router, prefix="/api/ai")
    app.include_router(canva_router, prefix="/api/integrations/canva")
    app.include_router(slack_router, prefix="/api/integrations")
    app.include_router(northstar_audit_router, prefix="/api")
    app.include_router(profile_router, prefix="/api/profile")
    app.include_router(user_profile_router, prefix="/api")
    app.include_router(finder_router, prefix="/api/finder")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(contracting_router, prefix="/api")
    app.include_router(contract_templates_router, prefix="/api")
    app.include_router(client_portal_router, prefix="/api")

    # Instrument after routers/middleware are attached.
    instrument_app(app)

    return app


def _ddb_error_handler(request: Request, exc: DdbError) -> Response:
    # Map storage-layer errors to stable HTTP semantics.
    status_code = 500
    title = "Storage Error"

    if isinstance(exc, DdbValidation):
        status_code = 400
        title = "Bad Request"
    elif isinstance(exc, DdbNotFound):
        status_code = 404
        title = "Not Found"
    elif isinstance(exc, DdbConflict):
        status_code = 409
        title = "Conflict"
    elif isinstance(exc, (DdbThrottled, DdbUnavailable)):
        status_code = 503
        title = "Service Unavailable"

    extensions: dict[str, object] | None = None
    try:
        extensions = {
            "operation": exc.operation,
            "table": exc.table_name,
            "key": exc.key,
            "awsRequestId": exc.aws_request_id,
            "retryable": bool(getattr(exc, "retryable", False)),
        }
        extensions = {k: v for k, v in extensions.items() if v is not None}
    except Exception:
        extensions = None

    # In production, problem_response already suppresses 5xx detail.
    return problem_response(
        request=request,
        status_code=status_code,
        title=title,
        detail=str(exc) if isinstance(getattr(exc, "message", None), str) else None,
        extensions=extensions,
    )


def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    status_code = int(getattr(exc, "status_code", 500) or 500)
    detail = getattr(exc, "detail", None)

    # Standardize to RFC7807 while preserving useful structured details
    # some routes currently raise HTTPException(detail={...}).
    title: str | None = None
    extensions: dict | None = None
    safe_detail: str | None = None

    if isinstance(detail, dict):
        extensions = detail
        if "error" in detail and isinstance(detail.get("error"), str):
            title = detail.get("error")
        msg = detail.get("message")
        if isinstance(msg, str) and msg.strip():
            safe_detail = msg.strip()
    elif detail is not None:
        safe_detail = str(detail)

    if status_code == 404:
        title = title or "Not Found"
        safe_detail = safe_detail or "Route not found"

    return problem_response(
        request=request,
        status_code=status_code,
        title=title,
        detail=safe_detail,
        extensions=extensions,
    )


def _validation_error_handler(request: Request, exc: RequestValidationError) -> Response:
    errors: list[dict[str, object]] = []
    for e in exc.errors():
        loc = e.get("loc") or ()
        loc_path = ".".join([str(x) for x in loc if x != "body"])
        errors.append(
            {
                "location": list(loc) if isinstance(loc, (list, tuple)) else [],
                "path": loc_path,
                "message": e.get("msg", "Invalid value"),
                "type": e.get("type"),
            }
        )
    return problem_response(
        request=request,
        status_code=422,
        title="Validation Failed",
        detail="Request validation failed",
        errors=errors,
    )


def _unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    # Log the full traceback to CloudWatch. We keep the HTTP response generic
    # in production (see problem_response), but operators need stack traces.
    try:
        log = get_logger("unhandled")
        rid = getattr(getattr(request, "state", None), "request_id", None)
        user = getattr(getattr(request, "state", None), "user", None)
        user_sub = getattr(user, "sub", None) if user else None
        log.exception(
            "unhandled_exception",
            request_id=str(rid) if rid else None,
            http_method=str(getattr(request, "method", "") or "").upper() or None,
            path=str(getattr(getattr(request, "url", None), "path", "") or ""),
            user_sub=str(user_sub) if user_sub else None,
        )
    except Exception:
        # Never let logging crash the exception handler.
        pass

    return problem_response(
        request=request,
        status_code=500,
        title="Internal Server Error",
        detail=str(exc) if exc else None,
    )


app = create_app()
