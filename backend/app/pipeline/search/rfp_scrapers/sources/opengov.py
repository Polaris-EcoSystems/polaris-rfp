from __future__ import annotations

from typing import Any

from app.pipeline.search.rfp_scrapers.framework import ScraperContext, UnimplementedScraper

SOURCE: dict[str, Any] = {
    "id": "opengov",
    "name": "OpenGov Procurement",
    "description": "Government procurement opportunities (auth + per-tenant workflow)",
    "baseUrl": "https://procurement.opengov.com/login",
    "kind": "browser",
    "authKind": "user_session",
    "requiresAuth": True,
    "implemented": False,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> UnimplementedScraper:
    _ = (search_params, ctx)
    return UnimplementedScraper(source_id="opengov", reason="requires_auth_and_tenant_specific_workflow")


