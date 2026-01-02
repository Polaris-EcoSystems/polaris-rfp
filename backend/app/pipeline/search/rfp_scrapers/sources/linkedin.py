from __future__ import annotations

from typing import Any

from app.infrastructure.token_crypto import decrypt_string
from app.repositories import finder_repo
from app.pipeline.search.rfp_scrapers.framework import ScraperContext
from app.pipeline.search.rfp_scrapers.linkedin_content_search_scraper import LinkedInContentSearchScraper

SOURCE: dict[str, Any] = {
    "id": "linkedin",
    "name": "LinkedIn",
    "description": "Search for RFPs within your network (requires authenticated workflow)",
    "baseUrl": "https://www.linkedin.com/search/results/content/",
    "kind": "browser",
    "authKind": "user_session",
    "requiresAuth": True,
    "implemented": True,
}


def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext) -> LinkedInContentSearchScraper:
    user_sub = str(getattr(ctx, "user_sub", "") or "").strip()
    if not user_sub:
        raise ValueError("linkedin scraper requires an authenticated user (missing user_sub)")

    item = finder_repo.get_user_linkedin_state(user_sub=user_sub)
    enc = (item or {}).get("encryptedStorageState") if isinstance(item, dict) else None
    if not enc:
        raise ValueError("linkedin storageState not configured for this user")

    raw = decrypt_string(enc)
    if not raw:
        raise ValueError("linkedin storageState could not be decrypted")
    storage_state = finder_repo.normalize_storage_state(raw)

    return LinkedInContentSearchScraper(storage_state=storage_state, search_params=search_params)


