from __future__ import annotations

import os

from fastapi import FastAPI

from app.settings import Settings
from app.observability.logging import get_logger


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def configure_otel(settings: Settings) -> None:
    """
    Optional OpenTelemetry setup.

    This is intentionally defensive:
    - If OTEL is disabled, do nothing.
    - If OTEL deps are missing, log once and do nothing (keeps local dev smooth).
    - If exporter config is missing, fall back to console exporter (useful in dev).
    """

    enabled = bool(getattr(settings, "otel_enabled", False)) or _truthy(
        os.environ.get("OTEL_ENABLED")
    )
    if not enabled:
        return

    log = get_logger("otel")

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except Exception:
        log.warning("otel_disabled_missing_deps")
        return

    service_name = str(
        getattr(settings, "otel_service_name", None)
        or os.environ.get("OTEL_SERVICE_NAME")
        or "polaris-rfp-backend"
    ).strip()

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    endpoint = str(
        getattr(settings, "otel_exporter_otlp_endpoint", None)
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or ""
    ).strip()

    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        log.info("otel_configured", exporter="otlp_http", endpoint=endpoint)
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        log.info("otel_configured", exporter="console")

    trace.set_tracer_provider(provider)


def instrument_app(app: FastAPI) -> None:
    """
    Wire instrumentation for inbound HTTP and common outbound HTTP clients.
    Safe to call even when OTEL isn't configured; instrumentors will no-op.
    """

    log = get_logger("otel")

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        log.info("otel_instrumented", target="fastapi")
    except Exception:
        # Keep the app running even if instrumentation fails.
        log.warning("otel_instrument_failed", target="fastapi")

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        log.info("otel_instrumented", target="httpx")
    except Exception:
        log.warning("otel_instrument_failed", target="httpx")

