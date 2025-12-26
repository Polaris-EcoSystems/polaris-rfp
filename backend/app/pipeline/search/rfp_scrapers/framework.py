from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

ScraperKind = Literal["browser", "api", "hybrid"]
AuthKind = Literal["none", "user_session", "service_account", "api_key", "cookie_jar"]


@dataclass(frozen=True, slots=True)
class ScraperContext:
    """
    Runtime context for a scrape execution.

    We keep this intentionally small for now; as we implement complex sources
    (LinkedIn/Google/BidNet/OpenGov/etc.) we can extend it with auth/session providers.
    """

    user_sub: str | None = None


@runtime_checkable
class RfpScraper(Protocol):
    """
    Unified scraper interface (browser-based, API-based, or hybrid).

    Implementations may optionally use context-manager semantics to allocate
    browser resources. API-only scrapers can implement no-op __enter__/__exit__.
    """

    def __enter__(self) -> "RfpScraper": ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

    def scrape(self, search_params: dict[str, Any] | None = None) -> list[Any]: ...


class NoopScraper:
    """Convenience base for API-only scrapers that don't need browser resources."""

    def __enter__(self) -> "NoopScraper":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class UnimplementedScraper(NoopScraper):
    """
    Placeholder for sources that require complex workflows (auth, pagination, etc.).
    """

    def __init__(self, *, source_id: str, reason: str | None = None):
        self.source_id = str(source_id or "").strip()
        self.reason = str(reason or "").strip() or "not_implemented"

    def scrape(self, search_params: dict[str, Any] | None = None) -> list[Any]:
        raise NotImplementedError(f"scraper_not_implemented:{self.source_id}:{self.reason}")


