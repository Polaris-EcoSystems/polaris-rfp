from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from .framework import ScraperContext
from .framework import RfpScraper
from ....settings import settings
from ....observability.logging import get_logger

log = get_logger("rfp_scraper_registry")

# Cache discovered source modules in long-running processes (prod).
# In development we disable caching so newly added sources show up without a restart.
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


def get_available_sources(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Get list of scraper sources with metadata (discovered from source modules)."""
    reg = _discover_sources(force_refresh=force_refresh)
    out: list[dict[str, Any]] = []
    for sid, spec in reg.items():
        meta = dict(spec.get("SOURCE") or {})
        implemented = bool(meta.get("implemented"))
        available = bool(implemented and _settings_ready(meta))
        unavailable_reason = ""
        if not implemented:
            # surface import/discovery issues if present
            unavailable_reason = str(meta.get("importError") or "").strip() or "not_implemented"
        elif not available:
            unavailable_reason = "missing_required_settings"
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
                # Optional fields (frontend ignores unknown keys, but they're helpful for debugging)
                "unavailableReason": unavailable_reason,
                "importError": meta.get("importError") or "",
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


def clear_source_cache() -> None:
    """Clear the in-process source discovery cache (mostly useful for tests/debug)."""
    global _CACHE
    _CACHE = None


def _discover_sources(*, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    global _CACHE
    if settings.is_development:
        # Avoid confusion during local development: new/renamed sources should show up immediately.
        force_refresh = True

    if (not force_refresh) and isinstance(_CACHE, dict):
        return _CACHE

    reg: dict[str, dict[str, Any]] = {}
    pkg = importlib.import_module("app.pipeline.search.rfp_scrapers.sources")
    # pkg.__path__ exists for packages; mypy can infer it here.
    for m in pkgutil.iter_modules(pkg.__path__):
        if not m.name or m.ispkg:
            continue
        module_path = f"app.pipeline.search.rfp_scrapers.sources.{m.name}"
        try:
            mod = importlib.import_module(module_path)
        except Exception as e:
            # Be resilient: a missing optional dependency (e.g. googleapiclient) shouldn't hide *all* sources.
            # We still surface the source in the registry (unavailable) so the UI can show it + the reason.
            msg = str(e) or e.__class__.__name__
            log.warning("scraper_source_import_failed", module=module_path, error=msg)
            reg[m.name] = {
                "SOURCE": {
                    "id": m.name,
                    "name": m.name,
                    "description": f"Failed to import source module ({module_path}): {msg}",
                    "baseUrl": "",
                    "requiresAuth": False,
                    "implemented": False,
                    "importError": msg,
                },
                "create": None,
            }
            continue

        meta = getattr(mod, "SOURCE", None)
        create = getattr(mod, "create", None)
        if not isinstance(meta, dict):
            reg[m.name] = {
                "SOURCE": {
                    "id": m.name,
                    "name": m.name,
                    "description": f"Source module missing SOURCE manifest: {module_path}",
                    "baseUrl": "",
                    "requiresAuth": False,
                    "implemented": False,
                    "importError": "missing_SOURCE_manifest",
                },
                "create": None,
            }
            continue

        sid = str(meta.get("id") or "").strip()
        if not sid:
            reg[m.name] = {
                "SOURCE": {
                    "id": m.name,
                    "name": m.name,
                    "description": f"Source manifest missing id: {module_path}",
                    "baseUrl": "",
                    "requiresAuth": bool(meta.get("requiresAuth")),
                    "implemented": False,
                    "importError": "missing_SOURCE_id",
                },
                "create": None,
            }
            continue

        reg[sid] = {"SOURCE": meta, "create": create}

    _CACHE = reg
    return reg

