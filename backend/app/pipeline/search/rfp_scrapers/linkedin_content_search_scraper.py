from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin, urlparse

from app.pipeline.search.rfp_scraper_base import BaseRfpScraper, RfpScrapedCandidate


class LinkedInContentSearchScraper(BaseRfpScraper):
    """
    LinkedIn content search scraper (Playwright via browser_worker).

    Auth:
    - Requires a Playwright `storageState` containing LinkedIn cookies.
    - The app already supports uploading this via /api/finder/linkedin/storage-state.

    Search params (recommended):
    - searchUrl: full LinkedIn search URL (most stable)
    - OR query: keywords string (we build a best-effort search URL)
    - maxCandidates: cap results (default 30)
    """

    def __init__(self, *, storage_state: dict[str, Any], search_params: dict[str, Any] | None = None):
        sp = search_params if isinstance(search_params, dict) else {}
        base_url = "https://www.linkedin.com/search/results/content/"
        super().__init__(source_name="linkedin", base_url=base_url, storage_state=storage_state)
        self._search_params = sp

    def get_search_url(self, search_params: dict[str, Any] | None = None) -> str:
        sp = search_params if isinstance(search_params, dict) else self._search_params

        search_url = str(sp.get("searchUrl") or "").strip()
        if search_url:
            return search_url

        q = str(sp.get("query") or "").strip()
        if not q:
            raise ValueError("linkedin scraper requires searchParams.searchUrl or searchParams.query")

        # Best-effort content search URL. LinkedIn may add/require extra params; we keep it minimal.
        return f"https://www.linkedin.com/search/results/content/?keywords={quote(q)}"

    def _wait_for_listing_content(self) -> None:
        # LinkedIn uses dynamic rendering; wait for main content area to show links.
        try:
            self.wait_for_selector("main", timeout_ms=30000)
        except Exception:
            pass
        try:
            self.wait_for_selector("a", timeout_ms=30000)
        except Exception:
            pass

    def scrape_listing_page(self, search_params: dict[str, Any] | None = None) -> list[RfpScrapedCandidate]:
        sp = search_params if isinstance(search_params, dict) else self._search_params
        max_candidates = int(sp.get("maxCandidates") or 30)
        max_candidates = max(1, min(200, max_candidates))

        # Collect links from the search results page.
        links = self.extract_links("a")
        if not links:
            return []

        search_url = self.get_search_url(sp)
        base_host = str(urlparse(search_url).hostname or "").lower()

        def normalize(url: str) -> str:
            u = str(url or "").strip()
            if not u:
                return ""
            return urljoin(search_url, u)

        def is_noise(url: str) -> bool:
            u = url.lower()
            # Drop obvious internal nav/profile links.
            if "linkedin.com/in/" in u or "linkedin.com/company/" in u:
                return True
            if "linkedin.com/jobs/" in u:
                return True
            if "linkedin.com/learning/" in u:
                return True
            if u.startswith("javascript:"):
                return True
            return False

        out: list[RfpScrapedCandidate] = []
        seen: set[str] = set()
        for lk in links:
            href = normalize(lk.get("href") or "")
            if not href:
                continue
            host = str(urlparse(href).hostname or "").lower()
            # Keep same host OR external links (often where the actual RFP lives).
            if host and base_host and host != base_host:
                # allow external if it looks like an RFP artifact
                if not any(x in href.lower() for x in ("rfp", "rfq", "solic", ".pdf")):
                    continue

            if is_noise(href):
                continue

            if href in seen:
                continue
            seen.add(href)

            title = str(lk.get("text") or "").strip()
            if not title or len(title) < 4:
                title = "LinkedIn result"

            out.append(
                self.create_candidate(
                    title=title,
                    detail_url=href,
                    source_url=search_url,
                    metadata={"searchUrl": search_url},
                )
            )
            if len(out) >= max_candidates:
                break

        return out


