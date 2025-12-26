from __future__ import annotations

from typing import Any

from ..framework import ScraperContext
from ..planning_org_scraper import PlanningOrgScraper

SOURCE: dict[str, Any] = {
    "id": "planning.org",
    "name": "American Planning Association",
    "description": "Daily RFP/RFQ listings for planning consultants",
    "baseUrl": "https://www.planning.org/consultants/rfp/search/",
    "kind": "browser",  # type: ScraperKind
    "authKind": "none",  # type: AuthKind
    "requiresAuth": False,
    "implemented": True,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> PlanningOrgScraper:
    # Planning.org is public; no user session required (for now).
    _ = ctx
    return PlanningOrgScraper(search_params=search_params)


