"""
Service for managing external context integration.

Provides unified interface for fetching and retrieving external context
that can be included in agent prompts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .agent_memory_db import MemoryType
from .agent_memory_retrieval import retrieve_relevant_memories
from .external_context_fetcher import (
    fetch_arxiv_research,
    fetch_business_news,
    fetch_financial_research,
    fetch_geopolitical_events,
    fetch_weather,
    store_external_context,
)
from ..observability.logging import get_logger

log = get_logger("external_context_service")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_external_context_for_query(
    *,
    query: str,
    context_types: list[str] | None = None,
    limit_per_type: int = 5,
    use_cache: bool = True,
) -> dict[str, Any]:
    """
    Get relevant external context for a user query.
    
    Determines which external context types are relevant based on query keywords
    and fetches/stores them.
    
    Args:
        query: User's query/question
        context_types: Specific context types to fetch (None = auto-detect)
        limit_per_type: Maximum items per context type
        use_cache: Whether to check cached/stored context first
    
    Returns:
        Dict with external context organized by type
    """
    query_lower = query.lower()
    result: dict[str, Any] = {
        "query": query,
        "contexts": {},
    }
    
    # Auto-detect context types if not specified
    if not context_types:
        context_types = []
        
        # Check for business/finance keywords
        business_keywords = ["business", "finance", "economic", "market", "stock", "trading", "procurement", "contract", "rfp"]
        if any(kw in query_lower for kw in business_keywords):
            context_types.append("news")
            context_types.append("financial_research")
        
        # Check for weather keywords
        weather_keywords = ["weather", "temperature", "forecast", "climate", "zip code", "zipcode"]
        if any(kw in query_lower for kw in weather_keywords):
            context_types.append("weather")
        
        # Check for geopolitical keywords
        geo_keywords = ["political", "government", "policy", "international", "diplomacy", "geopolitical", "election"]
        if any(kw in query_lower for kw in geo_keywords):
            context_types.append("geopolitical")
        
        # Check for research keywords
        research_keywords = ["research", "study", "paper", "academic", "journal", "arxiv"]
        if any(kw in query_lower for kw in research_keywords):
            context_types.append("research")
            context_types.append("financial_research")
    
    # Fetch each context type
    for ctx_type in set(context_types):  # Deduplicate
        try:
            if ctx_type == "news":
                news_data = fetch_business_news(query=query, limit=limit_per_type)
                if news_data.get("ok"):
                    result["contexts"]["news"] = news_data
                    # Store in memory
                    store_external_context(
                        context_type="news",
                        context_data=news_data,
                        query=query,
                        ttl_hours=24,
                    )
            
            elif ctx_type == "weather":
                # Extract zip code from query if possible
                import re
                zip_match = re.search(r'\b\d{5}(?:-\d{4})?\b', query)
                if zip_match:
                    zip_code = zip_match.group(0).split("-")[0]
                    weather_data = fetch_weather(zip_code=zip_code)
                    if weather_data.get("ok"):
                        result["contexts"]["weather"] = weather_data
                        store_external_context(
                            context_type="weather",
                            context_data=weather_data,
                            query=query,
                            ttl_hours=1,  # Weather expires faster
                        )
            
            elif ctx_type == "geopolitical":
                geo_data = fetch_geopolitical_events(limit=limit_per_type)
                if geo_data.get("ok"):
                    result["contexts"]["geopolitical"] = geo_data
                    store_external_context(
                        context_type="geopolitical",
                        context_data=geo_data,
                        query=query,
                        ttl_hours=24,
                    )
            
            elif ctx_type == "research":
                research_data = fetch_arxiv_research(query=query, max_results=limit_per_type)
                if research_data.get("ok"):
                    result["contexts"]["research"] = research_data
                    store_external_context(
                        context_type="research",
                        context_data=research_data,
                        query=query,
                        ttl_hours=168,  # Research stays relevant longer (1 week)
                    )
            
            elif ctx_type == "financial_research":
                fin_research = fetch_financial_research(query=query, limit=limit_per_type)
                if fin_research.get("ok"):
                    result["contexts"]["financial_research"] = fin_research
                    store_external_context(
                        context_type="research",
                        context_data=fin_research,
                        query=f"financial: {query}",
                        ttl_hours=168,
                    )
        
        except Exception as e:
            log.warning("external_context_fetch_failed", context_type=ctx_type, error=str(e))
            result["contexts"][ctx_type] = {"ok": False, "error": str(e)}
    
    result["ok"] = len(result["contexts"]) > 0
    return result


def get_stored_external_context(
    *,
    query: str | None = None,
    context_types: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Retrieve stored external context from memory.
    
    Args:
        query: Optional query for semantic search
        context_types: Optional filter by context types
        limit: Maximum number of contexts to return
    
    Returns:
        List of stored external context memories
    """
    # Retrieve from memory with EXTERNAL_CONTEXT type
    memories = retrieve_relevant_memories(
        scope_id="GLOBAL",
        memory_types=[MemoryType.EXTERNAL_CONTEXT],
        query_text=query,
        limit=limit,
    )
    
    # Filter by context type if specified
    if context_types:
        filtered = []
        for mem in memories:
            metadata = mem.get("metadata", {})
            if isinstance(metadata, dict):
                mem_context_type = metadata.get("contextType")
                if mem_context_type in context_types:
                    filtered.append(mem)
        return filtered
    
    return memories


def format_external_context_for_prompt(
    *,
    external_context: dict[str, Any],
    max_chars: int = 2000,
) -> str:
    """
    Format external context data for inclusion in agent prompts.
    
    Args:
        external_context: External context dict from get_external_context_for_query
        max_chars: Maximum characters for formatted output
    
    Returns:
        Formatted string for prompt inclusion
    """
    if not external_context.get("ok"):
        return ""
    
    lines: list[str] = []
    lines.append("=== EXTERNAL_CONTEXT (Real-World Information) ===")
    lines.append("")
    
    contexts = external_context.get("contexts", {})
    
    # Format news
    if "news" in contexts and contexts["news"].get("ok"):
        news = contexts["news"]
        lines.append("Business/Finance News:")
        articles = news.get("articles", [])
        for article in articles[:3]:  # Top 3
            title = article.get("title", "")
            desc = article.get("description", "")[:150]
            pub_date = article.get("publishedAt", "")[:10] if article.get("publishedAt") else ""
            url = article.get("url", "")
            lines.append(f"- {title} ({pub_date})")
            if desc:
                lines.append(f"  {desc}")
            if url:
                lines.append(f"  Source: {url}")
        lines.append("")
    
    # Format weather
    if "weather" in contexts and contexts["weather"].get("ok"):
        weather = contexts["weather"]
        location = weather.get("location", "")
        temp = weather.get("temperature_f")
        desc = weather.get("description", "")
        lines.append(f"Weather for {location}: {desc}, {temp}°F")
        if weather.get("humidity"):
            lines.append(f"Humidity: {weather.get('humidity')}%")
        lines.append("")
    
    # Format geopolitical events
    if "geopolitical" in contexts and contexts["geopolitical"].get("ok"):
        geo = contexts["geopolitical"]
        lines.append("Recent Geopolitical Events:")
        events = geo.get("events", [])
        for event in events[:3]:  # Top 3
            title = event.get("title", "")
            pub_date = event.get("publishedAt", "")[:10] if event.get("publishedAt") else ""
            lines.append(f"- {title} ({pub_date})")
        lines.append("")
    
    # Format research
    if "research" in contexts and contexts["research"].get("ok"):
        research = contexts["research"]
        lines.append("Research Papers (arXiv):")
        papers = research.get("papers", [])
        for paper in papers[:3]:  # Top 3
            title = paper.get("title", "")
            authors = paper.get("authors", [])
            published = paper.get("published", "")
            arxiv_id = paper.get("arxiv_id", "")
            lines.append(f"- {title}")
            if authors:
                authors_str = ", ".join(authors[:3])
                lines.append(f"  Authors: {authors_str}")
            if published:
                lines.append(f"  Published: {published}")
            if arxiv_id:
                lines.append(f"  arXiv ID: {arxiv_id}")
        lines.append("")
    
    if "financial_research" in contexts and contexts["financial_research"].get("ok"):
        fin_research = contexts["financial_research"]
        lines.append("Financial/Business Research:")
        papers = fin_research.get("papers", [])
        for paper in papers[:3]:  # Top 3
            title = paper.get("title", "")
            published = paper.get("published", "")
            lines.append(f"- {title}")
            if published:
                lines.append(f"  Published: {published}")
        lines.append("")
    
    formatted = "\n".join(lines).strip()
    
    # Truncate if needed
    if len(formatted) > max_chars:
        formatted = formatted[:max_chars - 100] + "\n\n[External context truncated...]"
    
    return formatted
