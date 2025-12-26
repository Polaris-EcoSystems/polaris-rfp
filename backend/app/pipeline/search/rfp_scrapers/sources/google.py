from __future__ import annotations

from typing import Any

from ....settings import settings
from ..framework import ScraperContext
from ..google_cse_scraper import GoogleCseRfpScraper

SOURCE: dict[str, Any] = {
    "id": "google",
    "name": "Google Search",
    "description": "Google Custom Search (CSE) API scraper",
    "baseUrl": "https://developers.google.com/custom-search/v1/overview",
    "kind": "api",
    "authKind": "api_key",
    "requiresAuth": False,
    "implemented": True,
    "requiredSettings": ["google_cse_api_key", "google_cse_cx"],
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> GoogleCseRfpScraper:
    _ = (search_params, ctx)
    api_key = str(getattr(settings, "google_cse_api_key", "") or "").strip()
    cx = str(getattr(settings, "google_cse_cx", "") or "").strip()
    return GoogleCseRfpScraper(api_key=api_key, cx=cx)


