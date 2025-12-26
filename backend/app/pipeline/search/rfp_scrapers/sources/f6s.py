from __future__ import annotations

from typing import Any

from ..framework import ScraperContext, UnimplementedScraper

SOURCE: dict[str, Any] = {
    "id": "f6s",
    "name": "F6S",
    "description": "Programs and opportunities (pagination + filtering; may require JS workflow)",
    "baseUrl": "https://www.f6s.com/programs",
    "kind": "browser",
    "authKind": "none",
    "requiresAuth": False,
    "implemented": False,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> UnimplementedScraper:
    _ = (search_params, ctx)
    return UnimplementedScraper(source_id="f6s", reason="requires_site_specific_workflow")


