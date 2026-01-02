from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.observability.logging import get_logger
from app.infrastructure.browser.browser_worker_client import (
    close,
    extract,
    goto,
    new_context,
    new_page,
    wait_for,
)

log = get_logger("rfp_scraper")


class RfpScrapedCandidate:
    """Represents a single RFP candidate found during scraping."""

    def __init__(
        self,
        *,
        source: str,
        source_url: str,
        title: str,
        detail_url: str,
        scraped_at: str,
        metadata: dict[str, Any] | None = None,
    ):
        self.source = source
        self.source_url = source_url
        self.title = title
        self.detail_url = detail_url
        self.scraped_at = scraped_at
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "source": self.source,
            "sourceUrl": self.source_url,
            "title": self.title,
            "detailUrl": self.detail_url,
            "scrapedAt": self.scraped_at,
            "metadata": self.metadata,
        }


class BaseRfpScraper(ABC):
    """Base class for RFP scrapers using Playwright."""

    def __init__(self, source_name: str, base_url: str, *, storage_state: dict[str, Any] | None = None):
        self.source_name = source_name
        self.base_url = base_url
        self.storage_state = storage_state if isinstance(storage_state, dict) else None
        self.context_id: str | None = None
        self.page_id: str | None = None

    def __enter__(self):
        """Context manager entry - creates browser context and page."""
        ctx_result = new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport_width=1280,
            viewport_height=800,
            storage_state=self.storage_state,
        )
        if not ctx_result.get("ok"):
            raise RuntimeError(f"Failed to create browser context: {ctx_result.get('error')}")
        self.context_id = ctx_result.get("contextId")
        if not self.context_id:
            raise RuntimeError("No contextId returned")

        page_result = new_page(context_id=self.context_id)
        if not page_result.get("ok"):
            raise RuntimeError(f"Failed to create page: {page_result.get('error')}")
        self.page_id = page_result.get("pageId")
        if not self.page_id:
            raise RuntimeError("No pageId returned")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes browser context and page."""
        if self.page_id or self.context_id:
            close(context_id=self.context_id, page_id=self.page_id)
            self.page_id = None
            self.context_id = None

    def navigate(self, url: str, wait_until: str = "load", timeout_ms: int = 30000) -> dict[str, Any]:
        """Navigate to a URL."""
        if not self.page_id:
            raise RuntimeError("No page available (call within context manager)")
        return goto(page_id=self.page_id, url=url, wait_until=wait_until, timeout_ms=timeout_ms)

    def wait_for_selector(self, selector: str, timeout_ms: int = 20000) -> dict[str, Any]:
        """Wait for a selector to appear."""
        if not self.page_id:
            raise RuntimeError("No page available (call within context manager)")
        return wait_for(page_id=self.page_id, selector=selector, timeout_ms=timeout_ms)

    def extract_text(self, selector: str) -> str:
        """Extract text content from a selector."""
        if not self.page_id:
            raise RuntimeError("No page available (call within context manager)")
        result = extract(page_id=self.page_id, selector=selector, mode="text")
        if not result.get("ok"):
            return ""
        return str(result.get("text") or "").strip()

    def extract_html(self, selector: str) -> str:
        """Extract HTML content from a selector."""
        if not self.page_id:
            raise RuntimeError("No page available (call within context manager)")
        result = extract(page_id=self.page_id, selector=selector, mode="html")
        if not result.get("ok"):
            return ""
        return str(result.get("html") or "").strip()

    def extract_attribute(self, selector: str, attribute: str) -> str:
        """Extract an attribute value from a selector."""
        if not self.page_id:
            raise RuntimeError("No page available (call within context manager)")
        result = extract(page_id=self.page_id, selector=selector, mode="attr", attribute=attribute)
        if not result.get("ok"):
            return ""
        return str(result.get("value") or "").strip()

    def extract_links(self, selector: str = "a") -> list[dict[str, str]]:
        """
        Extract (href, text) pairs from all elements matching selector.
        Requires browser_worker support for mode="links_all".
        """
        if not self.page_id:
            raise RuntimeError("No page available (call within context manager)")
        res = extract(page_id=self.page_id, selector=selector, mode="links_all")
        if not res.get("ok"):
            return []
        links = res.get("links")
        if not isinstance(links, list):
            return []
        out: list[dict[str, str]] = []
        for it in links[:1000]:
            if not isinstance(it, dict):
                continue
            href = str(it.get("href") or "").strip()
            text = str(it.get("text") or "").strip()
            if href or text:
                out.append({"href": href, "text": text})
        return out

    @abstractmethod
    def scrape_listing_page(self, search_params: dict[str, Any] | None = None) -> list[RfpScrapedCandidate]:
        """
        Scrape a listing page and return candidates.
        
        Args:
            search_params: Optional search parameters (source-specific)
            
        Returns:
            List of RFP candidates found on the page
        """
        pass

    @abstractmethod
    def get_search_url(self, search_params: dict[str, Any] | None = None) -> str:
        """Get the URL to scrape based on search parameters."""
        pass

    def scrape(self, search_params: dict[str, Any] | None = None) -> list[RfpScrapedCandidate]:
        """
        Main scrape method - navigates and extracts RFP candidates.
        
        Args:
            search_params: Optional search parameters (source-specific)
            
        Returns:
            List of RFP candidates
        """
        url = self.get_search_url(search_params)
        log.info("rfp_scraper_starting", source=self.source_name, url=url)

        try:
            # Navigate to the search/listing page
            nav_result = self.navigate(url, wait_until="networkidle", timeout_ms=60000)
            if not nav_result.get("ok"):
                raise RuntimeError(f"Failed to navigate: {nav_result.get('error')}")

            # Wait for content to load (implementer should override if needed)
            self._wait_for_listing_content()

            # Extract candidates
            candidates = self.scrape_listing_page(search_params)
            log.info(
                "rfp_scraper_completed",
                source=self.source_name,
                candidates_found=len(candidates),
            )
            return candidates

        except Exception as e:
            log.exception("rfp_scraper_failed", source=self.source_name, error=str(e))
            raise

    def _wait_for_listing_content(self) -> None:
        """
        Override this method to wait for specific content to load.
        Default implementation does nothing.
        """
        pass

    @staticmethod
    def now_iso() -> str:
        """Get current ISO timestamp."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def create_candidate(
        self,
        *,
        title: str,
        detail_url: str,
        source_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RfpScrapedCandidate:
        """Helper method to create a candidate with proper defaults."""
        return RfpScrapedCandidate(
            source=self.source_name,
            source_url=source_url or self.base_url,
            title=title,
            detail_url=detail_url,
            scraped_at=self.now_iso(),
            metadata=metadata,
        )

