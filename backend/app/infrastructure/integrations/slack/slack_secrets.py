from __future__ import annotations

import json
import time
from typing import Any

import boto3

from app.observability.logging import get_logger
from app.settings import settings


log = get_logger("slack_secrets")

# Simple in-process cache so we don't hit Secrets Manager on every Slack call.
_CACHE_TTL_SECONDS = 60
_cache_value: dict[str, Any] | None = None
_cache_at: float = 0.0


def get_slack_secret(*, force_refresh: bool = False) -> dict[str, Any] | None:
    arn = str(settings.slack_secret_arn or "").strip()
    if not arn:
        return None

    global _cache_value, _cache_at
    now = time.time()
    if (not force_refresh) and _cache_value is not None and (now - _cache_at) < _CACHE_TTL_SECONDS:
        return _cache_value

    try:
        sm = boto3.client("secretsmanager", region_name=settings.aws_region)
        resp = sm.get_secret_value(SecretId=arn)
        raw = resp.get("SecretString")
        if not isinstance(raw, str) or not raw.strip():
            _cache_value = None
            _cache_at = now
            return None
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            _cache_value = None
            _cache_at = now
            return None
        _cache_value = obj
        _cache_at = now
        return obj
    except Exception as e:
        log.warning("slack_secret_fetch_failed", error=str(e) or "unknown_error")
        return None


def get_secret_str(key: str) -> str | None:
    sec = get_slack_secret()
    if not sec:
        return None
    v = sec.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None

