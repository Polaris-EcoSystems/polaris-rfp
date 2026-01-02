from __future__ import annotations

from typing import Any

from app.pipeline.search.rfp_scrapers.framework import ScraperContext, UnimplementedScraper

SOURCE: dict[str, Any] = {
    "id": "bidnetdirect",
    "name": "Bidnet Direct",
    "description": "Supplier solicitations and RFP search (auth + complex workflow)",
    "baseUrl": "https://www.bidnetdirect.com/private/supplier/solicitations/search",
    "kind": "browser",
    "authKind": "user_session",
    "requiresAuth": True,
    "implemented": False,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> UnimplementedScraper:
    _ = (search_params, ctx)
    return UnimplementedScraper(source_id="bidnetdirect", reason="requires_auth_and_search_workflow")


