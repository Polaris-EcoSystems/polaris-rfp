"""
Agent tools for querying external context sources.

These tools allow the agent to fetch real-world context on demand.
"""

from __future__ import annotations

from typing import Any

from ...observability.logging import get_logger
from ..external_context_fetcher import (
    fetch_arxiv_research,
    fetch_business_news,
    fetch_financial_research,
    fetch_geopolitical_events,
    fetch_weather,
)
from ..external_context_service import format_external_context_for_prompt, get_external_context_for_query

log = get_logger("external_context_tools")


def _external_news_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch business and finance news.
    
    Args:
        query: Search query (e.g., "federal contracting", "government procurement")
        limit: Maximum number of articles (default: 10, max: 20)
    
    Returns:
        Dict with articles and metadata
    """
    query = str(args.get("query") or "").strip()
    limit = max(1, min(20, int(args.get("limit") or 10)))
    
    try:
        result = fetch_business_news(query=query if query else None, limit=limit)
        return result
    except Exception as e:
        log.warning("external_news_tool_failed", error=str(e))
        return {"ok": False, "error": str(e), "articles": []}


def _external_weather_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch weather data for a zip code.
    
    Args:
        zipCode: US zip code (e.g., "90210")
        countryCode: Country code (default: "US")
    
    Returns:
        Dict with weather data
    """
    zip_code = str(args.get("zipCode") or args.get("zip_code") or "").strip()
    if not zip_code:
        return {"ok": False, "error": "zipCode is required"}
    
    country_code = str(args.get("countryCode") or args.get("country_code") or "US").strip()
    
    try:
        result = fetch_weather(zip_code=zip_code, country_code=country_code)
        return result
    except Exception as e:
        log.warning("external_weather_tool_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def _external_research_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch research papers from arXiv.
    
    Args:
        query: Search query (e.g., "government procurement", "federal contracting")
        maxResults: Maximum number of results (default: 10, max: 100)
        sortBy: Sort order ("relevance", "lastUpdatedDate", "submittedDate")
    
    Returns:
        Dict with research papers
    """
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query is required"}
    
    max_results = max(1, min(100, int(args.get("maxResults") or args.get("max_results") or 10)))
    sort_by = str(args.get("sortBy") or args.get("sort_by") or "relevance").strip()
    
    try:
        result = fetch_arxiv_research(query=query, max_results=max_results, sort_by=sort_by)
        return result
    except Exception as e:
        log.warning("external_research_tool_failed", error=str(e))
        return {"ok": False, "error": str(e), "papers": []}


def _external_financial_research_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch financial/business research papers.
    
    Args:
        query: Search query (e.g., "corporate finance", "government contracting")
        limit: Maximum number of results (default: 10)
    
    Returns:
        Dict with research papers
    """
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query is required"}
    
    limit = max(1, min(50, int(args.get("limit") or 10)))
    
    try:
        result = fetch_financial_research(query=query, limit=limit)
        return result
    except Exception as e:
        log.warning("external_financial_research_tool_failed", error=str(e))
        return {"ok": False, "error": str(e), "papers": []}


def _external_geopolitical_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch recent geopolitical events/news.
    
    Args:
        region: Optional region filter (e.g., "United States", "Europe", "Asia")
        limit: Maximum number of events (default: 10, max: 20)
    
    Returns:
        Dict with events
    """
    region = str(args.get("region") or "").strip() or None
    limit = max(1, min(20, int(args.get("limit") or 10)))
    
    try:
        result = fetch_geopolitical_events(region=region, limit=limit)
        return result
    except Exception as e:
        log.warning("external_geopolitical_tool_failed", error=str(e))
        return {"ok": False, "error": str(e), "events": []}


def _external_context_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get relevant external context for a query (auto-detects context types).
    
    This is a convenience tool that fetches multiple types of external context
    based on query keywords.
    
    Args:
        query: User's query/question
        contextTypes: Optional list of specific context types to fetch
          (["news", "weather", "research", "geopolitical", "financial_research"])
        limitPerType: Maximum items per context type (default: 5)
    
    Returns:
        Dict with external context organized by type
    """
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query is required"}
    
    context_types_raw = args.get("contextTypes") or args.get("context_types")
    context_types = context_types_raw if isinstance(context_types_raw, list) else None
    limit_per_type = max(1, min(10, int(args.get("limitPerType") or args.get("limit_per_type") or 5)))
    
    try:
        result = get_external_context_for_query(
            query=query,
            context_types=context_types,
            limit_per_type=limit_per_type,
        )
        # Format for display
        formatted = format_external_context_for_prompt(
            external_context=result,
            max_chars=5000,
        )
        result["formatted"] = formatted
        return result
    except Exception as e:
        log.warning("external_context_tool_failed", error=str(e))
        return {"ok": False, "error": str(e), "contexts": {}}


EXTERNAL_CONTEXT_TOOLS: dict[str, tuple[dict[str, Any], Any]] = {
    "external_news": (
        {
            "type": "function",
            "function": {
                "name": "external_news",
                "description": "Fetch business and finance news. Useful for understanding current business events, market trends, economic conditions, and industry news relevant to RFPs and proposals.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'federal contracting', 'government procurement', 'business news')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of articles (default: 10, max: 20)",
                            "default": 10,
                        },
                    },
                },
                "strict": False,
            },
        },
        _external_news_tool,
    ),
    "external_weather": (
        {
            "type": "function",
            "function": {
                "name": "external_weather",
                "description": "Fetch weather data for a zip code. Useful when users ask about weather conditions in specific locations, which may be relevant for project timelines, logistics, or RFP requirements.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zipCode": {
                            "type": "string",
                            "description": "US zip code (e.g., '90210')",
                        },
                        "countryCode": {
                            "type": "string",
                            "description": "Country code (default: 'US')",
                            "default": "US",
                        },
                    },
                    "required": ["zipCode"],
                },
                "strict": False,
            },
        },
        _external_weather_tool,
    ),
    "external_research": (
        {
            "type": "function",
            "function": {
                "name": "external_research",
                "description": "Fetch research papers from arXiv. Useful for finding academic research, technical papers, and scholarly articles relevant to topics like government procurement, contracting, or domain-specific subjects.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'government procurement', 'federal contracting', 'public sector innovation')",
                        },
                        "maxResults": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10, max: 100)",
                            "default": 10,
                        },
                        "sortBy": {
                            "type": "string",
                            "description": "Sort order: 'relevance', 'lastUpdatedDate', or 'submittedDate'",
                            "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                            "default": "relevance",
                        },
                    },
                    "required": ["query"],
                },
                "strict": False,
            },
        },
        _external_research_tool,
    ),
    "external_financial_research": (
        {
            "type": "function",
            "function": {
                "name": "external_financial_research",
                "description": "Fetch financial and business research papers. Useful for finding research on corporate finance, economics, business strategy, government contracting finance, and related topics.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'corporate finance', 'government contracting', 'public procurement')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10, max: 50)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
                "strict": False,
            },
        },
        _external_financial_research_tool,
    ),
    "external_geopolitical": (
        {
            "type": "function",
            "function": {
                "name": "external_geopolitical",
                "description": "Fetch recent geopolitical events and news. Useful for understanding political developments, policy changes, international relations, and government actions that may affect RFPs, contracts, or business operations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "region": {
                            "type": "string",
                            "description": "Optional region filter (e.g., 'United States', 'Europe', 'Asia')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of events (default: 10, max: 20)",
                            "default": 10,
                        },
                    },
                },
                "strict": False,
            },
        },
        _external_geopolitical_tool,
    ),
    "external_context": (
        {
            "type": "function",
            "function": {
                "name": "external_context",
                "description": "Get relevant external context for a query (auto-detects and fetches multiple context types). This is a convenience tool that intelligently determines which external data sources are relevant based on the query and fetches them.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "User's query/question to fetch relevant external context for",
                        },
                        "contextTypes": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["news", "weather", "research", "geopolitical", "financial_research"],
                            },
                            "description": "Optional: Specific context types to fetch. If not provided, types are auto-detected from query keywords.",
                        },
                        "limitPerType": {
                            "type": "integer",
                            "description": "Maximum items per context type (default: 5, max: 10)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
                "strict": False,
            },
        },
        _external_context_tool,
    ),
}
