from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from ...settings import settings
from ...tools.registry.allowlist import parse_csv, uniq


def _base_url() -> str:
    u = str(getattr(settings, "browser_worker_url", "") or "").strip()
    if not u:
        raise RuntimeError("BROWSER_WORKER_URL is not configured")
    return u.rstrip("/")


def _allowed_domains() -> list[str]:
    explicit = uniq(parse_csv(getattr(settings, "agent_allowed_browser_domains", None)))
    # Empty list means "deny by default" for safety.
    return [d.lower() for d in explicit if d]


def _require_allowed_url(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        raise ValueError("missing_url")
    parsed = urlparse(u)
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("invalid_url")
    allowed = _allowed_domains()
    if allowed and host not in allowed:
        raise ValueError("domain_not_allowed")
    if not allowed:
        raise ValueError("browser_domains_not_configured")
    return u


def _post(path: str, payload: dict[str, Any], timeout_s: float = 30.0) -> dict[str, Any]:
    url = _base_url() + path
    with httpx.Client(timeout=timeout_s, follow_redirects=True) as c:
        r = c.post(url, json=payload or {})
        data = r.json() if r.content else {}
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid_response"}
        if r.status_code >= 400 and "ok" not in data:
            return {"ok": False, "error": "http_error", "status": r.status_code, "details": data}
        return data


def new_context(*, user_agent: str | None = None, viewport_width: int | None = None, viewport_height: int | None = None) -> dict[str, Any]:
    return _post(
        "/v1/context",
        {"userAgent": user_agent, "viewportWidth": viewport_width, "viewportHeight": viewport_height},
        timeout_s=30.0,
    )


def new_page(*, context_id: str) -> dict[str, Any]:
    cid = str(context_id or "").strip()
    if not cid:
        return {"ok": False, "error": "missing_contextId"}
    return _post("/v1/page", {"contextId": cid}, timeout_s=30.0)


def goto(*, page_id: str, url: str, wait_until: str | None = None, timeout_ms: int | None = None) -> dict[str, Any]:
    pid = str(page_id or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_pageId"}
    u = _require_allowed_url(url)
    return _post(
        "/v1/goto",
        {"pageId": pid, "url": u, "waitUntil": wait_until, "timeoutMs": timeout_ms},
        timeout_s=60.0,
    )


def click(*, page_id: str, selector: str, timeout_ms: int | None = None) -> dict[str, Any]:
    pid = str(page_id or "").strip()
    sel = str(selector or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_pageId"}
    if not sel:
        return {"ok": False, "error": "missing_selector"}
    return _post("/v1/click", {"pageId": pid, "selector": sel, "timeoutMs": timeout_ms}, timeout_s=60.0)


def type_text(*, page_id: str, selector: str, text: str, clear_first: bool = True, timeout_ms: int | None = None) -> dict[str, Any]:
    pid = str(page_id or "").strip()
    sel = str(selector or "").strip()
    t = str(text or "")
    if not pid:
        return {"ok": False, "error": "missing_pageId"}
    if not sel:
        return {"ok": False, "error": "missing_selector"}
    if not t.strip():
        return {"ok": False, "error": "missing_text"}
    return _post(
        "/v1/type",
        {"pageId": pid, "selector": sel, "text": t, "clearFirst": bool(clear_first), "timeoutMs": timeout_ms},
        timeout_s=60.0,
    )


def wait_for(*, page_id: str, selector: str | None = None, text: str | None = None, timeout_ms: int | None = None) -> dict[str, Any]:
    pid = str(page_id or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_pageId"}
    return _post(
        "/v1/wait_for",
        {"pageId": pid, "selector": selector, "text": text, "timeoutMs": timeout_ms},
        timeout_s=60.0,
    )


def extract(*, page_id: str, selector: str, mode: str | None = None, attribute: str | None = None) -> dict[str, Any]:
    pid = str(page_id or "").strip()
    sel = str(selector or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_pageId"}
    if not sel:
        return {"ok": False, "error": "missing_selector"}
    return _post("/v1/extract", {"pageId": pid, "selector": sel, "mode": mode, "attribute": attribute}, timeout_s=60.0)


def screenshot(*, page_id: str, full_page: bool = True, name: str | None = None) -> dict[str, Any]:
    pid = str(page_id or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_pageId"}
    return _post("/v1/screenshot", {"pageId": pid, "fullPage": bool(full_page), "name": name}, timeout_s=60.0)


def trace_start(*, context_id: str, screenshots: bool = True, snapshots: bool = True, sources: bool = False) -> dict[str, Any]:
    cid = str(context_id or "").strip()
    if not cid:
        return {"ok": False, "error": "missing_contextId"}
    return _post(
        "/v1/trace_start",
        {"contextId": cid, "screenshots": bool(screenshots), "snapshots": bool(snapshots), "sources": bool(sources)},
        timeout_s=30.0,
    )


def trace_stop(*, context_id: str, name: str | None = None) -> dict[str, Any]:
    cid = str(context_id or "").strip()
    if not cid:
        return {"ok": False, "error": "missing_contextId"}
    return _post("/v1/trace_stop", {"contextId": cid, "name": name}, timeout_s=60.0)


def close(*, context_id: str | None = None, page_id: str | None = None) -> dict[str, Any]:
    return _post("/v1/close", {"contextId": context_id, "pageId": page_id}, timeout_s=30.0)

