"""
External context aggregation and reporting service.

Aggregates and summarizes external context from all sources over a time window,
reports on source availability and record counts.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta, timezone
from typing import Any

from ..memory.core.agent_memory_db import MemoryType
from ..memory.retrieval.agent_memory_retrieval import retrieve_relevant_memories
from .external_context_fetcher import (
    fetch_arxiv_research,
    fetch_business_news,
    fetch_geopolitical_events,
    fetch_weather,
)
from ..observability.logging import get_logger

log = get_logger("external_context_aggregator")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _test_source_availability() -> dict[str, dict[str, Any]]:
    """
    Test availability of all external context sources in parallel.
    
    Returns:
        Dict mapping source names to availability status and metadata
    """
    results: dict[str, dict[str, Any]] = {}
    
    def test_news():
        try:
            result = fetch_business_news(query="test", limit=1)
            return {
                "available": result.get("ok", False),
                "error": result.get("error"),
                "articles_count": len(result.get("articles", [])) if result.get("ok") else 0,
            }
        except Exception as e:
            return {"available": False, "error": str(e), "articles_count": 0}
    
    def test_weather():
        try:
            # Test with a common zip code
            result = fetch_weather(zip_code="10001", country_code="US")
            return {
                "available": result.get("ok", False),
                "error": result.get("error"),
                "has_data": bool(result.get("temperature_f")),
            }
        except Exception as e:
            return {"available": False, "error": str(e), "has_data": False}
    
    def test_arxiv():
        try:
            result = fetch_arxiv_research(query="test", max_results=1)
            return {
                "available": result.get("ok", False),
                "error": result.get("error"),
                "papers_count": len(result.get("papers", [])) if result.get("ok") else 0,
            }
        except Exception as e:
            return {"available": False, "error": str(e), "papers_count": 0}
    
    def test_geopolitical():
        try:
            result = fetch_geopolitical_events(limit=1)
            return {
                "available": result.get("ok", False),
                "error": result.get("error"),
                "events_count": len(result.get("events", [])) if result.get("ok") else 0,
            }
        except Exception as e:
            return {"available": False, "error": str(e), "events_count": 0}
    
    # Run all tests in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_news = executor.submit(test_news)
        future_weather = executor.submit(test_weather)
        future_arxiv = executor.submit(test_arxiv)
        future_geo = executor.submit(test_geopolitical)
        
        results["news"] = future_news.result(timeout=30)
        results["weather"] = future_weather.result(timeout=30)
        results["arxiv"] = future_arxiv.result(timeout=30)
        results["geopolitical"] = future_geo.result(timeout=30)
    
    return results


def _count_stored_context_by_source(
    *,
    hours: int = 4,
) -> dict[str, int]:
    """
    Count stored external context records by source type over the last N hours.
    
    Args:
        hours: Number of hours to look back
    
    Returns:
        Dict mapping context types to record counts
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    start_iso = start.isoformat().replace("+00:00", "Z")
    
    # Retrieve all external context memories from GLOBAL scope
    # We'll use a broad query to get all recent external context
    memories = retrieve_relevant_memories(
        scope_id="GLOBAL",
        memory_types=[MemoryType.EXTERNAL_CONTEXT],
        query_text="external context",
        limit=1000,  # Get a large batch to count
    )
    
    counts: dict[str, int] = {
        "news": 0,
        "weather": 0,
        "research": 0,
        "geopolitical": 0,
        "total": 0,
    }
    
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        
        # Check if memory is within time window
        created_at = mem.get("createdAt", "")
        if created_at and created_at < start_iso:
            continue
        
        metadata = mem.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        
        context_type = str(metadata.get("contextType", "")).strip().lower()
        counts["total"] += 1
        
        if context_type == "news":
            counts["news"] += 1
        elif context_type == "weather":
            counts["weather"] += 1
        elif context_type == "research":
            counts["research"] += 1
        elif context_type == "geopolitical":
            counts["geopolitical"] += 1
    
    return counts


def aggregate_external_context_report(
    *,
    hours: int = 4,
) -> dict[str, Any]:
    """
    Generate comprehensive report on external context sources.
    
    Aggregates:
    - Source availability status
    - Record counts by source over time window
    - Summary of recent context
    
    Args:
        hours: Time window for aggregation (default: 4 hours)
    
    Returns:
        Dict with report data
    """
    report_start = _now_iso()
    
    log.info("external_context_aggregation_started", hours=hours)
    
    # Test source availability in parallel
    availability = _test_source_availability()
    
    # Count stored records
    record_counts = _count_stored_context_by_source(hours=hours)
    
    # Build summary
    available_sources = [name for name, status in availability.items() if status.get("available")]
    unavailable_sources = [name for name, status in availability.items() if not status.get("available")]
    
    report = {
        "ok": True,
        "window": {
            "hours": hours,
            "start": report_start,
        },
        "source_availability": availability,
        "record_counts": record_counts,
        "summary": {
            "total_sources": len(availability),
            "available_sources": len(available_sources),
            "unavailable_sources": len(unavailable_sources),
            "available_source_names": available_sources,
            "unavailable_source_names": unavailable_sources,
            "total_records_stored": record_counts.get("total", 0),
        },
        "generated_at": _now_iso(),
    }
    
    log.info(
        "external_context_aggregation_completed",
        available=len(available_sources),
        unavailable=len(unavailable_sources),
        total_records=record_counts.get("total", 0),
    )
    
    return report


def format_aggregation_report_for_slack(report: dict[str, Any]) -> str:
    """
    Format aggregation report for Slack message.
    
    Args:
        report: Report dict from aggregate_external_context_report
    
    Returns:
        Formatted Slack message text
    """
    if not report.get("ok"):
        return "*External Context Report*\nError generating report."
    
    summary = report.get("summary", {})
    availability = report.get("source_availability", {})
    counts = report.get("record_counts", {})
    window = report.get("window", {})
    
    lines: list[str] = []
    lines.append("*External Context Aggregation Report*")
    lines.append("")
    
    # Window info
    hours = window.get("hours", 4)
    lines.append(f"*Time Window:* Last {hours} hours")
    lines.append("")
    
    # Source availability
    lines.append("*Source Availability:*")
    for source_name, status in availability.items():
        available = status.get("available", False)
        status_icon = "✅" if available else "❌"
        error = status.get("error")
        
        source_display = source_name.replace("_", " ").title()
        status_text = f"{status_icon} {source_display}"
        
        if available:
            # Add additional info if available
            if source_name == "news" and "articles_count" in status:
                status_text += f" ({status['articles_count']} test article)"
            elif source_name == "arxiv" and "papers_count" in status:
                status_text += f" ({status['papers_count']} test paper)"
            elif source_name == "geopolitical" and "events_count" in status:
                status_text += f" ({status['events_count']} test event)"
        else:
            if error:
                status_text += f" - {error}"
        
        lines.append(status_text)
    lines.append("")
    
    # Record counts
    lines.append("*Records Stored (Last 4 Hours):*")
    lines.append(f"- News: {counts.get('news', 0)}")
    lines.append(f"- Weather: {counts.get('weather', 0)}")
    lines.append(f"- Research: {counts.get('research', 0)}")
    lines.append(f"- Geopolitical: {counts.get('geopolitical', 0)}")
    lines.append(f"- *Total: {counts.get('total', 0)}*")
    lines.append("")
    
    # Summary
    available_count = summary.get("available_sources", 0)
    total_count = summary.get("total_sources", 0)
    lines.append(f"*Summary:* {available_count}/{total_count} sources available, {counts.get('total', 0)} total records stored")
    
    return "\n".join(lines)
