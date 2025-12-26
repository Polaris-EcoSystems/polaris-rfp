from __future__ import annotations

from typing import Any

from ..custom_links_scraper import CustomLinksScraper
from ..framework import ScraperContext

SOURCE: dict[str, Any] = {
    "id": "custom",
    "name": "Custom Website (Links)",
    "description": "Scrape a listing page and collect links matching a pattern",
    "baseUrl": "",
    "kind": "browser",
    "authKind": "none",
    "requiresAuth": False,
    "implemented": True,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> CustomLinksScraper:
    _ = ctx
    return CustomLinksScraper(search_params=search_params)


