from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build

from ..rfp_scraper_base import RfpScrapedCandidate
from .framework import NoopScraper


class GoogleCseRfpScraper(NoopScraper):
    """
    Google Custom Search (CSE) scraper.

    search_params:
      - query (required): search query
      - apiKey (optional): override API key
      - cx (optional): override search engine id
      - dateRestrict (optional): e.g. "d7" (last 7 days), "m1" (last month)
      - siteSearch (optional): restrict to a domain (e.g. "gov")
      - maxCandidates (optional): cap results (default 20, max 100)
    """

    def __init__(self, *, api_key: str, cx: str):
        self.api_key = str(api_key or "").strip()
        self.cx = str(cx or "").strip()
        if not self.api_key:
            raise ValueError("missing_google_cse_api_key")
        if not self.cx:
            raise ValueError("missing_google_cse_cx")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def scrape(self, search_params: dict[str, Any] | None = None) -> list[RfpScrapedCandidate]:
        sp = search_params if isinstance(search_params, dict) else {}
        q = str(sp.get("query") or "").strip()
        if not q:
            raise ValueError("google scraper requires searchParams.query")

        api_key = str(sp.get("apiKey") or self.api_key).strip()
        cx = str(sp.get("cx") or self.cx).strip()

        date_restrict = str(sp.get("dateRestrict") or "").strip() or None
        site_search = str(sp.get("siteSearch") or "").strip() or None

        max_candidates = int(sp.get("maxCandidates") or 20)
        max_candidates = max(1, min(100, max_candidates))

        # Avoid discovery caching to disk (works better in containers).
        service = build("customsearch", "v1", developerKey=api_key, cache_discovery=False)

        out: list[RfpScrapedCandidate] = []
        start = 1
        while len(out) < max_candidates:
            num = min(10, max_candidates - len(out))
            req = service.cse().list(
                q=q,
                cx=cx,
                num=num,
                start=start,
                dateRestrict=date_restrict,
                siteSearch=site_search,
            )
            res = req.execute() or {}
            items = res.get("items") or []
            if not isinstance(items, list) or not items:
                break

            for it in items:
                if not isinstance(it, dict):
                    continue
                title = str(it.get("title") or "").strip() or "Google result"
                link = str(it.get("link") or "").strip()
                if not link:
                    continue
                snippet = str(it.get("snippet") or "").strip()
                display_link = str(it.get("displayLink") or "").strip()

                out.append(
                    RfpScrapedCandidate(
                        source="google",
                        source_url=f"google:cse:{q}",
                        title=title,
                        detail_url=link,
                        scraped_at=self._now_iso(),
                        metadata={
                            "query": q,
                            "snippet": snippet,
                            "displayLink": display_link,
                            "cacheId": it.get("cacheId"),
                        },
                    )
                )
                if len(out) >= max_candidates:
                    break

            start += 10

        return out


