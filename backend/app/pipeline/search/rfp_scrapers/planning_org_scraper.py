from __future__ import annotations

from typing import Any

from app.pipeline.search.rfp_scraper_base import BaseRfpScraper, RfpScrapedCandidate


class PlanningOrgScraper(BaseRfpScraper):
    """Scraper for American Planning Association RFP listings."""

    def __init__(self, search_params: dict[str, Any] | None = None):
        super().__init__(
            source_name="planning.org",
            base_url="https://www.planning.org/consultants/rfp/search/",
        )
        self._search_params = search_params if isinstance(search_params, dict) else {}

    def get_search_url(self, search_params: dict[str, Any] | None = None) -> str:
        """Get the search URL."""
        # Default to the main search page
        return self.base_url

    def _wait_for_listing_content(self) -> None:
        """Wait for RFP listings to load."""
        # Wait for the listings container (adjust selector based on actual page structure)
        try:
            self.wait_for_selector("table.rfp-results, .rfp-listing, article.rfp", timeout_ms=30000)
        except Exception:
            # If selector doesn't exist, continue anyway
            pass

    def scrape_listing_page(self, search_params: dict[str, Any] | None = None) -> list[RfpScrapedCandidate]:
        """Scrape the planning.org RFP listing page."""
        sp = search_params if isinstance(search_params, dict) else self._search_params
        max_candidates = int(sp.get("maxCandidates") or 50)
        max_candidates = max(1, min(200, max_candidates))

        # We don’t rely on fragile table selectors; instead, extract links and heuristically filter.
        links = self.extract_links("a")
        if not links:
            return []

        from urllib.parse import urljoin, urlparse

        base = self.base_url
        host = str(urlparse(base).hostname or "").lower()

        def looks_like_rfp(url: str) -> bool:
            u = url.lower()
            return ("rfp" in u) or ("rfq" in u) or ("/consultants/" in u and "/rfp" in u)

        out: list[RfpScrapedCandidate] = []
        seen: set[str] = set()
        for lk in links:
            href = str(lk.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(base, href)
            uhost = str(urlparse(abs_url).hostname or "").lower()
            if host and uhost and uhost != host:
                continue
            if not looks_like_rfp(abs_url):
                continue
            if abs_url in seen:
                continue
            seen.add(abs_url)

            title = str(lk.get("text") or "").strip()
            if not title or len(title) < 4:
                title = "Planning.org RFP"

            out.append(
                self.create_candidate(
                    title=title,
                    detail_url=abs_url,
                    source_url=self.base_url,
                    metadata={"listingUrl": self.base_url},
                )
            )
            if len(out) >= max_candidates:
                break

        return out

