from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .observability.logging import configure_logging, get_logger
from .infrastructure.storage import s3_assets
from .settings import settings


log = get_logger("browser_worker")


class NewContextRequest(BaseModel):
    userAgent: str | None = Field(default=None, max_length=300)
    viewportWidth: int | None = Field(default=1280, ge=320, le=3840)
    viewportHeight: int | None = Field(default=800, ge=240, le=2160)


class NewContextResponse(BaseModel):
    ok: bool = True
    contextId: str


class NewPageRequest(BaseModel):
    contextId: str = Field(min_length=1, max_length=120)


class NewPageResponse(BaseModel):
    ok: bool = True
    pageId: str


class GotoRequest(BaseModel):
    pageId: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    waitUntil: str | None = Field(default="load", max_length=40)
    timeoutMs: int | None = Field(default=30000, ge=1000, le=120000)


class ClickRequest(BaseModel):
    pageId: str = Field(min_length=1, max_length=120)
    selector: str = Field(min_length=1, max_length=600)
    timeoutMs: int | None = Field(default=15000, ge=1000, le=120000)


class TypeRequest(BaseModel):
    pageId: str = Field(min_length=1, max_length=120)
    selector: str = Field(min_length=1, max_length=600)
    text: str = Field(min_length=1, max_length=5000)
    timeoutMs: int | None = Field(default=15000, ge=1000, le=120000)
    clearFirst: bool | None = True


class WaitForRequest(BaseModel):
    pageId: str = Field(min_length=1, max_length=120)
    selector: str | None = Field(default=None, max_length=600)
    text: str | None = Field(default=None, max_length=400)
    timeoutMs: int | None = Field(default=20000, ge=1000, le=120000)


class ExtractRequest(BaseModel):
    pageId: str = Field(min_length=1, max_length=120)
    selector: str = Field(min_length=1, max_length=600)
    mode: str | None = Field(default="text", max_length=20)  # text|html|attr
    attribute: str | None = Field(default=None, max_length=80)


class ScreenshotRequest(BaseModel):
    pageId: str = Field(min_length=1, max_length=120)
    fullPage: bool | None = True
    name: str | None = Field(default=None, max_length=120)


class CloseRequest(BaseModel):
    contextId: str | None = Field(default=None, max_length=120)
    pageId: str | None = Field(default=None, max_length=120)


class TraceStartRequest(BaseModel):
    contextId: str = Field(min_length=1, max_length=120)
    screenshots: bool | None = True
    snapshots: bool | None = True
    sources: bool | None = False


class TraceStopRequest(BaseModel):
    contextId: str = Field(min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=120)


@dataclass
class _State:
    browser: Browser | None = None
    contexts: dict[str, BrowserContext] = None  # type: ignore[assignment]
    pages: dict[str, Page] = None  # type: ignore[assignment]
    last_used: dict[str, float] = None  # type: ignore[assignment]


STATE = _State(contexts={}, pages={}, last_used={})


def _touch(*ids: str) -> None:
    now = time.time()
    for i in ids:
        if i:
            STATE.last_used[i] = now


def _artifact_key(*, kind: str, name: str | None = None) -> str:
    safe = str(name or "").strip()[:80]
    suffix = safe.replace(" ", "_") if safe else uuid.uuid4().hex[:10]
    return f"agent/browser_artifacts/{kind}/{int(time.time())}_{suffix}.png"


async def _require_browser() -> Browser:
    if STATE.browser is not None:
        return STATE.browser
    pw = await async_playwright().start()
    # Headless chromium is installed in the container via `playwright install chromium`.
    browser = await pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
    STATE.browser = browser
    return browser


def _require_context(context_id: str) -> BrowserContext:
    cid = str(context_id or "").strip()
    ctx = STATE.contexts.get(cid)
    if not ctx:
        raise HTTPException(status_code=404, detail="context_not_found")
    _touch(cid)
    return ctx


def _require_page(page_id: str) -> Page:
    pid = str(page_id or "").strip()
    pg = STATE.pages.get(pid)
    if not pg:
        raise HTTPException(status_code=404, detail="page_not_found")
    _touch(pid)
    return pg


app = FastAPI(title="Polaris Browser Worker", version="1.0.0")


@app.on_event("startup")
async def _startup() -> None:
    configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
    await _require_browser()
    log.info("browser_worker_started", aws_region=settings.aws_region, assets_bucket=bool(settings.assets_bucket_name))


@app.get("/")
async def root() -> dict[str, Any]:
    return {"ok": True, "service": "browser_worker"}


@app.post("/v1/context", response_model=NewContextResponse)
async def new_context(req: NewContextRequest) -> NewContextResponse:
    browser = await _require_browser()
    cid = "ctx_" + uuid.uuid4().hex[:18]
    ctx = await browser.new_context(
        user_agent=req.userAgent or None,
        viewport={"width": req.viewportWidth or 1280, "height": req.viewportHeight or 800},
    )
    STATE.contexts[cid] = ctx
    _touch(cid)
    return NewContextResponse(contextId=cid)


@app.post("/v1/page", response_model=NewPageResponse)
async def new_page(req: NewPageRequest) -> NewPageResponse:
    ctx = _require_context(req.contextId)
    pid = "pg_" + uuid.uuid4().hex[:18]
    pg = await ctx.new_page()
    STATE.pages[pid] = pg
    _touch(req.contextId, pid)
    return NewPageResponse(pageId=pid)


@app.post("/v1/goto")
async def goto(req: GotoRequest) -> dict[str, Any]:
    pg = _require_page(req.pageId)
    from typing import Literal, cast

    WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]
    raw = str(req.waitUntil or "").strip().lower()
    wait_until: WaitUntil = "load"
    if raw in ("commit", "domcontentloaded", "load", "networkidle"):
        wait_until = cast(WaitUntil, raw)
    await pg.goto(req.url, wait_until=wait_until, timeout=req.timeoutMs or 30000)
    return {"ok": True, "pageId": req.pageId, "url": req.url}


@app.post("/v1/click")
async def click(req: ClickRequest) -> dict[str, Any]:
    pg = _require_page(req.pageId)
    await pg.click(req.selector, timeout=req.timeoutMs or 15000)
    return {"ok": True, "pageId": req.pageId, "selector": req.selector}


@app.post("/v1/type")
async def type_text(req: TypeRequest) -> dict[str, Any]:
    pg = _require_page(req.pageId)
    loc = pg.locator(req.selector)
    await loc.wait_for(timeout=req.timeoutMs or 15000)
    if req.clearFirst is True:
        await loc.fill("")
    await loc.type(req.text)
    return {"ok": True, "pageId": req.pageId, "selector": req.selector, "typedChars": len(req.text)}


@app.post("/v1/wait_for")
async def wait_for(req: WaitForRequest) -> dict[str, Any]:
    pg = _require_page(req.pageId)
    timeout = req.timeoutMs or 20000
    if req.selector:
        await pg.locator(req.selector).wait_for(timeout=timeout)
        return {"ok": True, "pageId": req.pageId, "selector": req.selector}
    if req.text:
        await pg.get_by_text(req.text).first.wait_for(timeout=timeout)
        return {"ok": True, "pageId": req.pageId, "text": req.text}
    raise HTTPException(status_code=400, detail="missing_selector_or_text")


@app.post("/v1/extract")
async def extract(req: ExtractRequest) -> dict[str, Any]:
    pg = _require_page(req.pageId)
    loc = pg.locator(req.selector).first
    mode = (req.mode or "text").strip().lower()
    if mode == "html":
        html = await loc.inner_html()
        return {"ok": True, "pageId": req.pageId, "selector": req.selector, "html": (html[:20000] + "…") if len(html) > 20000 else html}
    if mode == "attr":
        attr = str(req.attribute or "").strip()
        if not attr:
            raise HTTPException(status_code=400, detail="missing_attribute")
        v = await loc.get_attribute(attr)
        return {"ok": True, "pageId": req.pageId, "selector": req.selector, "attribute": attr, "value": v}
    # text
    txt = await loc.inner_text()
    return {"ok": True, "pageId": req.pageId, "selector": req.selector, "text": (txt[:20000] + "…") if len(txt) > 20000 else txt}


@app.post("/v1/screenshot")
async def screenshot(req: ScreenshotRequest) -> dict[str, Any]:
    pg = _require_page(req.pageId)
    data = await pg.screenshot(full_page=bool(req.fullPage is True), type="png")
    key = _artifact_key(kind="screenshot", name=req.name)
    s3_assets.put_object_bytes(key=key, data=data, content_type="image/png")
    return {"ok": True, "pageId": req.pageId, "s3Key": key}


@app.post("/v1/trace_start")
async def trace_start(req: TraceStartRequest) -> dict[str, Any]:
    ctx = _require_context(req.contextId)
    try:
        await ctx.tracing.start(
            screenshots=bool(req.screenshots is True),
            snapshots=bool(req.snapshots is True),
            sources=bool(req.sources is True),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"trace_start_failed:{e}")
    return {"ok": True, "contextId": req.contextId}


@app.post("/v1/trace_stop")
async def trace_stop(req: TraceStopRequest) -> dict[str, Any]:
    ctx = _require_context(req.contextId)
    # Playwright writes traces to a file. We'll write to /tmp then upload to S3.
    suffix = (str(req.name or "").strip().replace(" ", "_")[:80]) or uuid.uuid4().hex[:10]
    path = f"/tmp/trace_{int(time.time())}_{suffix}.zip"
    try:
        await ctx.tracing.stop(path=path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"trace_stop_failed:{e}")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        raise HTTPException(status_code=500, detail="trace_read_failed")
    key = f"agent/browser_artifacts/trace/{int(time.time())}_{suffix}.zip"
    s3_assets.put_object_bytes(key=key, data=data, content_type="application/zip")
    return {"ok": True, "contextId": req.contextId, "s3Key": key}


@app.post("/v1/close")
async def close(req: CloseRequest) -> dict[str, Any]:
    closed: list[str] = []
    if req.pageId:
        pid = str(req.pageId).strip()
        pg = STATE.pages.pop(pid, None)
        if pg:
            try:
                await pg.close()
            except Exception:
                pass
            closed.append(pid)
    if req.contextId:
        cid = str(req.contextId).strip()
        ctx = STATE.contexts.pop(cid, None)
        if ctx:
            try:
                await ctx.close()
            except Exception:
                pass
            closed.append(cid)
    return {"ok": True, "closed": closed}

