"""
External context fetcher for real-world data integration.

This module fetches and stores external context from various sources:
- Business and finance news
- Weather data (by zip code)
- Geopolitical events
- Research papers (arXiv, financial/business research)

All external context is stored in agent memory for retrieval and reuse.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ...observability.logging import get_logger
from ...settings import settings
from ...memory.core.agent_memory_db import MemoryType, create_memory

log = get_logger("external_context_fetcher")

# Cache for external context queries
_external_context_cache: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour cache for external data


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_api_call(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float = 10.0) -> dict[str, Any] | None:
    """Safely call external API with error handling."""
    try:
        resp = httpx.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
        if resp.status_code == 200:
            return resp.json() if resp.content else None
        else:
            log.warning("external_api_error", url=url, status_code=resp.status_code)
            return None
    except Exception as e:
        log.warning("external_api_exception", url=url, error=str(e))
        return None


def fetch_business_news(*, query: str | None = None, limit: int = 10) -> dict[str, Any]:
    """
    Fetch business and finance news.
    
    Uses NewsAPI (free tier) or similar service.
    Requires NEWS_API_KEY in settings.
    
    Args:
        query: Search query (e.g., "federal contracting", "government procurement")
        limit: Maximum number of articles to return
    
    Returns:
        Dict with articles and metadata
    """
    # Check cache
    cache_key = f"news_{query or 'general'}_{limit}"
    now = time.time()
    if cache_key in _external_context_cache:
        cached_time, cached_data = _external_context_cache[cache_key]
        if (now - cached_time) < CACHE_TTL_SECONDS:
            return cached_data
    
    api_key = getattr(settings, "news_api_key", None)
    if not api_key:
        log.debug("news_api_key_not_configured")
        return {"ok": False, "error": "news_api_key_not_configured", "articles": []}
    
    # Use NewsAPI v2 (free tier allows 100 requests/day)
    base_url = "https://newsapi.org/v2/top-headlines"
    params: dict[str, Any] = {
        "apiKey": api_key,
        "category": "business",
        "language": "en",
        "pageSize": min(limit, 20),  # NewsAPI free tier limit
    }
    
    if query:
        # Use everything endpoint for search
        base_url = "https://newsapi.org/v2/everything"
        params["q"] = query
        params["sortBy"] = "publishedAt"
        params.pop("category", None)  # Remove category for search
    
    data = _safe_api_call(base_url, params=params)
    
    if not data or not isinstance(data, dict):
        return {"ok": False, "error": "api_failed", "articles": []}
    
    articles = data.get("articles", [])
    if not isinstance(articles, list):
        articles = []
    
    # Format articles for context
    formatted_articles = []
    for article in articles[:limit]:
        if not isinstance(article, dict):
            continue
        formatted_articles.append({
            "title": str(article.get("title", "")).strip(),
            "description": str(article.get("description", "")).strip()[:500],
            "url": str(article.get("url", "")).strip(),
            "publishedAt": str(article.get("publishedAt", "")).strip(),
            "source": str(article.get("source", {}).get("name", "") if isinstance(article.get("source"), dict) else "").strip(),
        })
    
    result = {
        "ok": True,
        "source": "newsapi",
        "query": query,
        "articles": formatted_articles,
        "fetchedAt": _now_iso(),
    }
    
    # Update cache
    _external_context_cache[cache_key] = (now, result)
    
    return result


def fetch_weather(*, zip_code: str, country_code: str = "US") -> dict[str, Any]:
    """
    Fetch weather data for a zip code.
    
    Uses OpenWeatherMap API (free tier).
    Requires OPENWEATHER_API_KEY in settings.
    
    Args:
        zip_code: US zip code or postal code
        country_code: Country code (default: US)
    
    Returns:
        Dict with weather data
    """
    cache_key = f"weather_{zip_code}_{country_code}"
    now = time.time()
    if cache_key in _external_context_cache:
        cached_time, cached_data = _external_context_cache[cache_key]
        # Weather cache shorter (15 minutes)
        if (now - cached_time) < 900:  # 15 minutes
            return cached_data
    
    api_key = getattr(settings, "openweather_api_key", None)
    if not api_key:
        log.debug("openweather_api_key_not_configured")
        return {"ok": False, "error": "openweather_api_key_not_configured"}
    
    # OpenWeatherMap API
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "zip": f"{zip_code},{country_code}",
        "appid": api_key,
        "units": "imperial",  # Fahrenheit
    }
    
    data = _safe_api_call(url, params=params)
    
    if not data or not isinstance(data, dict):
        return {"ok": False, "error": "api_failed"}
    
    weather = data.get("weather", [{}])[0] if isinstance(data.get("weather"), list) and data.get("weather") else {}
    main_data = data.get("main", {})
    wind = data.get("wind", {})
    
    result = {
        "ok": True,
        "source": "openweathermap",
        "zip_code": zip_code,
        "location": data.get("name"),
        "description": str(weather.get("description", "")).strip(),
        "temperature_f": main_data.get("temp"),
        "feels_like_f": main_data.get("feels_like"),
        "humidity": main_data.get("humidity"),
        "wind_speed_mph": wind.get("speed"),
        "fetchedAt": _now_iso(),
    }
    
    # Update cache
    _external_context_cache[cache_key] = (now, result)
    
    return result


def fetch_arxiv_research(*, query: str, max_results: int = 10, sort_by: str = "relevance") -> dict[str, Any]:
    """
    Fetch research papers from arXiv.
    
    Uses arXiv API (free, no auth required).
    
    Args:
        query: Search query (e.g., "government procurement", "federal contracting")
        max_results: Maximum number of results
        sort_by: Sort order ("relevance", "lastUpdatedDate", "submittedDate")
    
    Returns:
        Dict with research papers
    """
    cache_key = f"arxiv_{query}_{max_results}_{sort_by}"
    now = time.time()
    # arXiv cache longer (6 hours) since papers don't change frequently
    if cache_key in _external_context_cache:
        cached_time, cached_data = _external_context_cache[cache_key]
        if (now - cached_time) < 21600:  # 6 hours
            return cached_data
    
    # arXiv API (no auth required)
    url = "http://export.arxiv.org/api/query"
    params: dict[str, str | int] = {
        "search_query": query,
        "start": 0,
        "max_results": min(max_results, 100),
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    
    try:
        resp = httpx.get(url, params=params, timeout=15.0)
        if resp.status_code != 200:
            return {"ok": False, "error": "api_failed", "papers": []}
        
        # Parse Atom XML response
        content = resp.text
        papers = []
        
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            # Namespace handling for Atom feeds
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            
            entries = root.findall(".//atom:entry", ns)
            for entry in entries[:max_results]:
                paper: dict[str, Any] = {}
                
                # Title
                title_elem = entry.find("atom:title", ns)
                if title_elem is not None and title_elem.text:
                    # Clean title (remove newlines and extra spaces)
                    paper["title"] = " ".join(title_elem.text.strip().split())
                
                # Summary/abstract
                summary_elem = entry.find("atom:summary", ns)
                if summary_elem is not None and summary_elem.text:
                    summary_text = summary_elem.text.strip()
                    # Clean and truncate summary
                    paper["summary"] = " ".join(summary_text.split())[:500]
                
                # Authors
                authors = []
                for author in entry.findall("atom:author", ns):
                    name_elem = author.find("atom:name", ns)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())
                paper["authors"] = authors[:5]  # Limit authors
                
                # Published date
                published_elem = entry.find("atom:published", ns)
                if published_elem is not None and published_elem.text:
                    pub_str = published_elem.text.strip()
                    # Extract date part (YYYY-MM-DD)
                    if "T" in pub_str:
                        paper["published"] = pub_str.split("T")[0]
                    else:
                        paper["published"] = pub_str[:10]
                
                # Links (find PDF and HTML links)
                pdf_link = None
                html_link = None
                for link in entry.findall("atom:link", ns):
                    rel = link.get("rel", "")
                    href = link.get("href", "")
                    if rel == "alternate" and href:
                        html_link = href
                    elif "pdf" in href.lower() or rel == "related":
                        pdf_link = href if href else None
                paper["pdf_url"] = pdf_link
                paper["html_url"] = html_link
                
                # ID (extract arXiv ID)
                id_elem = entry.find("atom:id", ns)
                if id_elem is not None and id_elem.text:
                    arxiv_url = id_elem.text.strip()
                    # Extract ID from URL like http://arxiv.org/abs/1234.5678v1
                    if "/abs/" in arxiv_url:
                        paper["arxiv_id"] = arxiv_url.split("/abs/")[-1].split("v")[0]
                    elif "/" in arxiv_url:
                        paper["arxiv_id"] = arxiv_url.split("/")[-1].split("v")[0]
                
                if paper.get("title"):
                    papers.append(paper)
        
        except Exception as parse_error:
            log.warning("arxiv_xml_parse_failed", error=str(parse_error))
            papers = []  # Return empty list on parse failure
        
        result = {
            "ok": len(papers) > 0,
            "source": "arxiv",
            "query": query,
            "papers": papers,
            "fetchedAt": _now_iso(),
        }
    except Exception as e:
        log.warning("arxiv_fetch_failed", error=str(e))
        return {"ok": False, "error": str(e), "papers": []}
    
    # Update cache
    _external_context_cache[cache_key] = (now, result)
    
    return result


def fetch_geopolitical_events(*, region: str | None = None, limit: int = 10) -> dict[str, Any]:
    """
    Fetch recent geopolitical events.
    
    Uses NewsAPI with specific queries for geopolitical news.
    Requires NEWS_API_KEY in settings.
    
    Args:
        region: Region filter (e.g., "United States", "Europe", "Asia")
        limit: Maximum number of events
    
    Returns:
        Dict with events
    """
    cache_key = f"geo_{region or 'global'}_{limit}"
    now = time.time()
    if cache_key in _external_context_cache:
        cached_time, cached_data = _external_context_cache[cache_key]
        if (now - cached_time) < CACHE_TTL_SECONDS:
            return cached_data
    
    api_key = getattr(settings, "news_api_key", None)
    if not api_key:
        return {"ok": False, "error": "news_api_key_not_configured", "events": []}
    
    # Use NewsAPI with geopolitical keywords
    query = "politics OR government OR international relations OR diplomacy"
    if region:
        query = f"({query}) AND ({region})"
    
    base_url = "https://newsapi.org/v2/everything"
    params = {
        "apiKey": api_key,
        "q": query,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": min(limit, 20),
    }
    
    data = _safe_api_call(base_url, params=params)
    
    if not data or not isinstance(data, dict):
        return {"ok": False, "error": "api_failed", "events": []}
    
    articles = data.get("articles", [])
    if not isinstance(articles, list):
        articles = []
    
    formatted_events = []
    for article in articles[:limit]:
        if not isinstance(article, dict):
            continue
        formatted_events.append({
            "title": str(article.get("title", "")).strip(),
            "description": str(article.get("description", "")).strip()[:500],
            "url": str(article.get("url", "")).strip(),
            "publishedAt": str(article.get("publishedAt", "")).strip(),
            "source": str(article.get("source", {}).get("name", "") if isinstance(article.get("source"), dict) else "").strip(),
        })
    
    result = {
        "ok": True,
        "source": "newsapi",
        "region": region,
        "events": formatted_events,
        "fetchedAt": _now_iso(),
    }
    
    # Update cache
    _external_context_cache[cache_key] = (now, result)
    
    return result


def fetch_financial_research(*, query: str, limit: int = 10) -> dict[str, Any]:
    """
    Fetch financial/business research.
    
    Uses SSRN (Social Science Research Network) API or similar.
    Falls back to arXiv with financial keywords if SSRN not available.
    
    Args:
        query: Search query (e.g., "corporate finance", "government contracting")
        limit: Maximum number of results
    
    Returns:
        Dict with research papers
    """
    # For now, use arXiv with finance/business keywords
    # TODO: Integrate SSRN or other financial research APIs when available
    enhanced_query = f"{query} AND (finance OR economics OR business OR accounting)"
    return fetch_arxiv_research(query=enhanced_query, max_results=limit)


def store_external_context(
    *,
    context_type: str,
    context_data: dict[str, Any],
    query: str | None = None,
    scope_id: str = "GLOBAL",
    ttl_hours: int = 24,
) -> dict[str, Any]:
    """
    Store external context in agent memory for later retrieval.
    
    Args:
        context_type: Type of context ("news", "weather", "research", "geopolitical")
        context_data: The fetched context data
        query: Original query that generated this context
        scope_id: Scope for memory (default: GLOBAL)
        ttl_hours: Hours until context expires (default: 24)
    
    Returns:
        Created memory dict
    """
    # Build content from context data
    content_parts: list[str] = []
    
    if context_type == "news" and context_data.get("ok"):
        content_parts.append(f"Business/Finance News (query: {query or 'general'})")
        articles = context_data.get("articles", [])
        for article in articles[:5]:  # Store top 5
            title = article.get("title", "")
            desc = article.get("description", "")[:200]
            pub_date = article.get("publishedAt", "")[:10] if article.get("publishedAt") else ""
            content_parts.append(f"- {title} ({pub_date}): {desc}")
    
    elif context_type == "weather" and context_data.get("ok"):
        location = context_data.get("location", "")
        temp = context_data.get("temperature_f")
        desc = context_data.get("description", "")
        content_parts.append(f"Weather for {location}: {desc}, {temp}°F")
        if context_data.get("humidity"):
            content_parts.append(f"Humidity: {context_data.get('humidity')}%")
    
    elif context_type == "research" and context_data.get("ok"):
        content_parts.append(f"Research Papers (query: {query})")
        papers = context_data.get("papers", [])
        for paper in papers[:5]:  # Store top 5
            title = paper.get("title", "")
            authors = paper.get("authors", [])
            published = paper.get("published", "")
            if title:
                paper_line = f"- {title}"
                if authors:
                    authors_str = ", ".join(authors[:3])
                    paper_line += f" by {authors_str}"
                if published:
                    paper_line += f" ({published})"
                content_parts.append(paper_line)
    
    elif context_type == "geopolitical" and context_data.get("ok"):
        content_parts.append(f"Geopolitical Events (region: {context_data.get('region', 'global')})")
        events = context_data.get("events", [])
        for event in events[:5]:  # Store top 5
            title = event.get("title", "")
            pub_date = event.get("publishedAt", "")[:10] if event.get("publishedAt") else ""
            content_parts.append(f"- {title} ({pub_date})")
    
    content = "\n".join(content_parts)
    if not content:
        content = json.dumps(context_data, default=str)[:5000]  # Fallback
    
    # Calculate expiry
    expires_at = int(time.time()) + (ttl_hours * 3600)
    
    # Create tags and keywords
    tags = ["external_context", context_type]
    keywords = [context_type]
    if query:
        # Extract keywords from query
        from ...memory.core.agent_memory_keywords import extract_keywords
        keywords.extend(extract_keywords(query, max_keywords=10))
    
    # Store in memory
    memory = create_memory(
        memory_type=MemoryType.EXTERNAL_CONTEXT,
        scope_id=scope_id,
        content=content,
        tags=tags,
        keywords=keywords,
        metadata={
            "contextType": context_type,
            "query": query,
            "contextData": context_data,
            "source": context_data.get("source"),
            "fetchedAt": context_data.get("fetchedAt"),
        },
        summary=f"{context_type.replace('_', ' ').title()}: {query or 'general context'}"[:500],
        expires_at=expires_at,
        source="external_context_fetcher",
    )
    
    log.info("external_context_stored", context_type=context_type, query=query, memory_id=memory.get("memoryId"))
    
    return memory
