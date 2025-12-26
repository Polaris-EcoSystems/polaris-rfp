from __future__ import annotations

from typing import Any

from ..framework import ScraperContext, UnimplementedScraper

SOURCE: dict[str, Any] = {
    "id": "energywerx",
    "name": "EnergyWerx",
    "description": "Energy sector opportunities (alerts recommended; site workflow needed)",
    "baseUrl": "https://www.energywerx.org/opportunities",
    "kind": "browser",
    "authKind": "none",
    "requiresAuth": False,
    "implemented": False,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> UnimplementedScraper:
    _ = (search_params, ctx)
    return UnimplementedScraper(source_id="energywerx", reason="requires_site_specific_workflow")


