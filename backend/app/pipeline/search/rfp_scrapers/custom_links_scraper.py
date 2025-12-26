from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from ..rfp_scraper_base import BaseRfpScraper, RfpScrapedCandidate


class CustomLinksScraper(BaseRfpScraper):
    """
    Generic scraper that:
    - navigates to a listing page (searchParams.listingUrl)
    - extracts links (searchParams.linkSelector, default "a")
    - filters by linkPattern (substring or regex)
    """

    def __init__(self, search_params: dict[str, Any] | None = None):
        sp = search_params if isinstance(search_params, dict) else {}
        listing_url = str(sp.get("listingUrl") or "").strip() or "about:blank"
        super().__init__(source_name="custom", base_url=listing_url)
        self._search_params = sp

    def get_search_url(self, search_params: dict[str, Any] | None = None) -> str:
        sp = search_params if isinstance(search_params, dict) else self._search_params
        listing_url = str(sp.get("listingUrl") or "").strip()
        if not listing_url:
            raise ValueError("custom scraper requires searchParams.listingUrl")
        return listing_url

    def _wait_for_listing_content(self) -> None:
        # Best-effort: wait for *any* link; this avoids hanging on empty pages.
        try:
            self.wait_for_selector("a", timeout_ms=20000)
        except Exception:
            pass

    def scrape_listing_page(self, search_params: dict[str, Any] | None = None) -> list[RfpScrapedCandidate]:
        sp = search_params if isinstance(search_params, dict) else self._search_params
        link_selector = str(sp.get("linkSelector") or "a").strip() or "a"

        pattern_raw = str(sp.get("linkPattern") or "").strip()
        pattern_is_regex = bool(sp.get("linkPatternIsRegex"))

        max_candidates = int(sp.get("maxCandidates") or 50)
        max_candidates = max(1, min(200, max_candidates))

        # Extract links from the page (text + href).
        links = self.extract_links(link_selector)

        base = self.get_search_url(sp)
        base_host = str(urlparse(base).hostname or "").lower()

        rx: re.Pattern[str] | None = None
        if pattern_raw and pattern_is_regex:
            try:
                rx = re.compile(pattern_raw, re.IGNORECASE)
            except Exception:
                rx = None

        out: list[RfpScrapedCandidate] = []
        seen: set[str] = set()
        for lk in links:
            href = str(lk.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(base, href)
            uhost = str(urlparse(abs_url).hostname or "").lower()
            if base_host and uhost and uhost != base_host:
                # Keep within the same host by default.
                continue

            if pattern_raw:
                if rx:
                    if not rx.search(abs_url):
                        continue
                else:
                    if pattern_raw.lower() not in abs_url.lower():
                        continue

            if abs_url in seen:
                continue
            seen.add(abs_url)

            title = str(lk.get("text") or "").strip()
            if not title or len(title) < 4:
                title = abs_url

            out.append(
                self.create_candidate(
                    title=title,
                    detail_url=abs_url,
                    source_url=base,
                    metadata={"listingUrl": base},
                )
            )
            if len(out) >= max_candidates:
                break

        return out


