from __future__ import annotations

from typing import Any

from ..framework import ScraperContext, UnimplementedScraper

SOURCE: dict[str, Any] = {
    "id": "herox",
    "name": "HeroX",
    "description": "Innovation challenges and opportunities (site workflow needed)",
    "baseUrl": "https://www.herox.com/",
    "kind": "browser",
    "authKind": "none",
    "requiresAuth": False,
    "implemented": False,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> UnimplementedScraper:
    _ = (search_params, ctx)
    return UnimplementedScraper(source_id="herox", reason="requires_site_specific_workflow")


