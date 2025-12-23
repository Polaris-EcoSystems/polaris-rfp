from __future__ import annotations

from typing import Any

from ..rfp_scraper_base import BaseRfpScraper
from .planning_org_scraper import PlanningOrgScraper

# Registry of available scrapers
_SCRAPERS: dict[str, type[BaseRfpScraper]] = {
    "planning.org": PlanningOrgScraper,
    # Add more scrapers here as they are implemented
}

# Metadata about each source
_SOURCE_METADATA: dict[str, dict[str, Any]] = {
    "planning.org": {
        "name": "American Planning Association",
        "description": "Daily RFP/RFQ listings for planning consultants",
        "baseUrl": "https://www.planning.org/consultants/rfp/search/",
        "requiresAuth": False,
    },
    "linkedin": {
        "name": "LinkedIn",
        "description": "Search for RFPs within your network",
        "baseUrl": "https://www.linkedin.com/search/results/content/",
        "requiresAuth": True,
        "available": False,  # Not yet implemented
    },
    "google": {
        "name": "Google Search",
        "description": "Search with 'last week' filter for recent RFPs",
        "baseUrl": "https://www.google.com/search",
        "requiresAuth": False,
        "available": False,  # Not yet implemented
    },
    "bidnetdirect": {
        "name": "Bidnet Direct",
        "description": "Supplier solicitations and RFP search",
        "baseUrl": "https://www.bidnetdirect.com/private/supplier/solicitations/search",
        "requiresAuth": True,
        "available": False,  # Not yet implemented
    },
    "f6s": {
        "name": "F6S",
        "description": "Programs and opportunities for startups",
        "baseUrl": "https://www.f6s.com/programs",
        "requiresAuth": False,
        "available": False,  # Not yet implemented
    },
    "opengov": {
        "name": "OpenGov Procurement",
        "description": "Government procurement opportunities",
        "baseUrl": "https://procurement.opengov.com/login",
        "requiresAuth": True,
        "available": False,  # Not yet implemented
    },
    "techwerx": {
        "name": "TechWerx",
        "description": "Technology opportunities (alerts recommended)",
        "baseUrl": "https://www.techwerx.org/opportunities",
        "requiresAuth": False,
        "available": False,  # Not yet implemented
    },
    "energywerx": {
        "name": "EnergyWerx",
        "description": "Energy sector opportunities (alerts recommended)",
        "baseUrl": "https://www.energywerx.org/opportunities",
        "requiresAuth": False,
        "available": False,  # Not yet implemented
    },
    "herox": {
        "name": "HeroX",
        "description": "Innovation challenges and opportunities",
        "baseUrl": "https://www.herox.com/",
        "requiresAuth": False,
        "available": False,  # Not yet implemented
    },
}


def get_available_sources() -> list[dict[str, Any]]:
    """Get list of available scraper sources with metadata."""
    sources: list[dict[str, Any]] = []
    for source_id, metadata in _SOURCE_METADATA.items():
        # Use 'available' from metadata if present, otherwise check if scraper exists
        available = metadata.get("available", source_id in _SCRAPERS)
        if "available" in metadata:
            # Remove the internal 'available' flag from metadata
            metadata_copy = {k: v for k, v in metadata.items() if k != "available"}
        else:
            metadata_copy = metadata.copy()
        sources.append(
            {
                "id": source_id,
                **metadata_copy,
                "available": available,
            }
        )
    return sources


def get_scraper(source: str) -> BaseRfpScraper | None:
    """Get a scraper instance for the given source."""
    scraper_class = _SCRAPERS.get(source)
    if not scraper_class:
        return None
    return scraper_class()


def is_source_available(source: str) -> bool:
    """Check if a scraper is available for the given source."""
    return source in _SCRAPERS

