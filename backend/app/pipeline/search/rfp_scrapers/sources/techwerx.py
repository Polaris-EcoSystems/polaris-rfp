from __future__ import annotations

from typing import Any

from ..framework import ScraperContext, UnimplementedScraper

SOURCE: dict[str, Any] = {
    "id": "techwerx",
    "name": "TechWerx",
    "description": "Technology opportunities (alerts recommended; site workflow needed)",
    "baseUrl": "https://www.techwerx.org/opportunities",
    "kind": "browser",
    "authKind": "none",
    "requiresAuth": False,
    "implemented": False,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> UnimplementedScraper:
    _ = (search_params, ctx)
    return UnimplementedScraper(source_id="techwerx", reason="requires_site_specific_workflow")


