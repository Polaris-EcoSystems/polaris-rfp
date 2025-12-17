from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .errors import http_404_handler, http_500_handler
from .middleware.auth import require_auth
from .middleware.cors import build_allowed_origins
from .routers.health import router as health_router
from .routers.auth import router as auth_router
from .routers.content import router as content_router
from .routers.rfp import router as rfp_router
from .routers.proposals import router as proposals_router
from .routers.templates import router as templates_router
from .routers.ai import router as ai_router
from .routers.integrations_canva import router as canva_router
from .settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Polaris RFP Backend",
        version="1.0.0",
        default_response_class=ORJSONResponse,
    )

    allowed_origins = build_allowed_origins(
        frontend_base_url=settings.frontend_base_url,
        frontend_url=settings.frontend_url,
        frontend_urls=settings.frontend_urls,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        expose_headers=["ETag"],
        max_age=3000,
    )

    # Auth dependency (placeholder; Cognito will replace)
    @app.middleware("http")
    async def _auth_middleware(request, call_next):
        try:
            await require_auth(request)
        except StarletteHTTPException as exc:
            return ORJSONResponse(
                status_code=exc.status_code, content={"error": exc.detail}
            )
        return await call_next(request)

    # Error handlers
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, http_500_handler)

    # Routes
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(rfp_router, prefix="/api/rfp")
    app.include_router(proposals_router, prefix="/api/proposals")
    app.include_router(templates_router, prefix="/api/templates")
    app.include_router(content_router, prefix="/api/content")
    app.include_router(ai_router, prefix="/api/ai")
    app.include_router(canva_router, prefix="/api/integrations/canva")

    return app


def _http_exception_handler(request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return http_404_handler(request, exc)
    # Match legacy shape for other HTTP errors where possible
    return ORJSONResponse(status_code=exc.status_code, content={"error": exc.detail})


def _validation_error_handler(_request, exc: RequestValidationError):
    # Keep close to Express-validator style: { errors: [...] }
    errors = []
    for e in exc.errors():
        errors.append(
            {
                "msg": e.get("msg", "Invalid value"),
                "path": ".".join([str(x) for x in e.get("loc", []) if x != "body"]),
                "type": e.get("type"),
            }
        )
    return ORJSONResponse(status_code=400, content={"errors": errors})


app = create_app()
