from __future__ import annotations

import json
import logging
import sys
from typing import Any

from .context import get_request_id

structlog: Any
try:
    import structlog as _structlog
    structlog = _structlog
except Exception:  # pragma: no cover
    structlog = None


def _add_request_id(_: logging.Logger, __: str, event_dict: dict) -> dict:
    rid = get_request_id()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


_CONFIGURED = False


def configure_logging(*, level: str | int = "INFO") -> None:
    """
    Configure stdlib logging + structlog to output structured JSON to stdout.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Minimal fallback when optional deps aren't installed (e.g. unit tests).
    if structlog is None:  # pragma: no cover
        root = logging.getLogger()
        root.handlers = [logging.StreamHandler(sys.stdout)]
        root.setLevel(level)
        _CONFIGURED = True
        return

    pre_chain = [
        _add_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=pre_chain,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Make uvicorn loggers flow through root so formatting is consistent.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(name)
        log.handlers = []
        log.propagate = True

    structlog.configure(
        processors=[
            _add_request_id,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


class _ShimLogger:
    """
    structlog-like logger shim for environments without structlog installed.
    Accepts `log.info("event", key=value)` and emits a single JSON line.
    """

    def __init__(self, name: str | None):
        self._logger = logging.getLogger(name or __name__)

    def _emit(self, level: int, event: str, **kwargs):
        payload = {"event": str(event or "")}
        try:
            rid = get_request_id()
            if rid:
                payload["request_id"] = rid
        except Exception:
            pass
        for k, v in (kwargs or {}).items():
            if v is None:
                continue
            payload[str(k)] = v
        self._logger.log(level, json.dumps(payload, default=str))

    def info(self, event: str, **kwargs):
        self._emit(logging.INFO, event, **kwargs)

    def warning(self, event: str, **kwargs):
        self._emit(logging.WARNING, event, **kwargs)

    def error(self, event: str, **kwargs):
        self._emit(logging.ERROR, event, **kwargs)

    def exception(self, event: str, **kwargs):
        # Emit once and include traceback.
        payload = {"event": str(event or ""), **{str(k): v for k, v in (kwargs or {}).items() if v is not None}}
        try:
            rid = get_request_id()
            if rid:
                payload["request_id"] = rid
        except Exception:
            pass
        self._logger.exception(json.dumps(payload, default=str))


def get_logger(name: str | None = None):
    if structlog is None:  # pragma: no cover
        return _ShimLogger(name)
    return structlog.get_logger(name)




