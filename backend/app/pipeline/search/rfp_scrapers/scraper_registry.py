from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from .framework import ScraperContext
from .framework import RfpScraper
from ....settings import settings

_CACHE: dict[str, dict[str, Any]] | None = None


def _settings_ready(meta: dict[str, Any]) -> bool:
    req = meta.get("requiredSettings")
    if not isinstance(req, list) or not req:
        return True
    for k in req:
        name = str(k or "").strip()
        if not name:
            continue
        val = getattr(settings, name, None)
        if val is None:
            return False
        if isinstance(val, str) and not val.strip():
            return False
    return True


def get_available_sources() -> list[dict[str, Any]]:
    """Get list of scraper sources with metadata (discovered from source modules)."""
    reg = _discover_sources()
    out: list[dict[str, Any]] = []
    for sid, spec in reg.items():
        meta = dict(spec.get("SOURCE") or {})
        implemented = bool(meta.get("implemented"))
        available = bool(implemented and _settings_ready(meta))
        out.append(
            {
                "id": sid,
                "name": meta.get("name") or sid,
                "description": meta.get("description") or "",
                "baseUrl": meta.get("baseUrl") or "",
                "requiresAuth": bool(meta.get("requiresAuth")),
                "available": available,
                "kind": meta.get("kind") or "browser",
                "authKind": meta.get("authKind") or ("user_session" if meta.get("requiresAuth") else "none"),
            }
        )
    # Stable ordering for UI
    out.sort(key=lambda x: str(x.get("name") or ""))
    return out


def get_scraper(
    source: str,
    search_params: dict[str, Any] | None = None,
    *,
    user_sub: str | None = None,
) -> RfpScraper | None:
    """Get a scraper instance for the given source via its source module factory."""
    sid = str(source or "").strip()
    if not sid:
        return None
    reg = _discover_sources()
    spec = reg.get(sid)
    if not spec:
        return None
    create = spec.get("create")
    if not callable(create):
        return None
    ctx = ScraperContext(user_sub=str(user_sub).strip() if user_sub else None)
    sp = search_params if isinstance(search_params, dict) else None
    try:
        return create(search_params=sp, ctx=ctx)
    except Exception:
        return None


def is_source_available(source: str) -> bool:
    """Check if a scraper is implemented and runnable for the given source."""
    sid = str(source or "").strip()
    if not sid:
        return False
    reg = _discover_sources()
    spec = reg.get(sid) or {}
    meta = spec.get("SOURCE") or {}
    return bool(meta.get("implemented") and _settings_ready(meta))


def _discover_sources() -> dict[str, dict[str, Any]]:
    global _CACHE
    if isinstance(_CACHE, dict):
        return _CACHE

    reg: dict[str, dict[str, Any]] = {}
    pkg = importlib.import_module("app.pipeline.search.rfp_scrapers.sources")
    for m in pkgutil.iter_modules(pkg.__path__):  # type: ignore[attr-defined]
        if not m.name or m.ispkg:
            continue
        mod = importlib.import_module(f"app.pipeline.search.rfp_scrapers.sources.{m.name}")
        meta = getattr(mod, "SOURCE", None)
        create = getattr(mod, "create", None)
        if not isinstance(meta, dict):
            continue
        sid = str(meta.get("id") or "").strip()
        if not sid:
            continue
        reg[sid] = {"SOURCE": meta, "create": create}

    _CACHE = reg
    return reg

