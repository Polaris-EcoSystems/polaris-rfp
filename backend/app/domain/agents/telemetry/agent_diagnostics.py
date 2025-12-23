from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...observability.logging import get_logger
from .agent_events_repo import list_recent_events_global
from .agent_jobs_repo import list_recent_jobs
from ...memory.core.agent_memory import add_diagnostics_memory
from .agent_telemetry import get_agent_metrics
from .daily_report_builder import build_northstar_daily_report

log = get_logger("agent_diagnostics")

# Cache for diagnostics to avoid repeated expensive queries
_diagnostics_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes cache


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_get_data_source(name: str, func, *args, **kwargs) -> dict[str, Any] | None:
    """
    Safely execute a data source function with error handling.
    Returns None on failure to allow graceful degradation.
    """
    try:
        result = func(*args, **kwargs)
        return result if isinstance(result, dict) else None
    except Exception as e:
        log.warning(
            "diagnostics_data_source_failed",
            source=name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _build_activities_with_context(
    *,
    events: list[dict[str, Any]],
    limit: int = 50,
    user_sub: str | None = None,
    rfp_id: str | None = None,
    channel_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Build enriched activity list with contextual information.
    
    Includes correlation IDs, user context, Slack context, and relationships.
    """
    activities: list[dict[str, Any]] = []
    
    for event in events[:limit]:
        if not isinstance(event, dict):
            continue
        
        event_type = str(event.get("type") or "").strip()
        tool = str(event.get("tool") or "").strip()
        rfp_id_event = str(event.get("rfpId") or "").strip()
        created_at = str(event.get("createdAt") or "").strip()
        correlation_id = str(event.get("correlationId") or "").strip()
        created_by = str(event.get("createdBy") or "").strip()
        
        # Filter by context if provided
        if user_sub and created_by and user_sub not in created_by:
            continue
        if rfp_id and rfp_id_event and rfp_id != rfp_id_event:
            continue
        
        activity: dict[str, Any] = {
            "type": event_type,
            "createdAt": created_at,
            "relevanceScore": 1.0,  # Can be enhanced with scoring
        }
        
        if tool:
            activity["tool"] = tool
        if rfp_id_event:
            activity["rfpId"] = rfp_id_event
        if correlation_id:
            activity["correlationId"] = correlation_id
        if created_by:
            activity["createdBy"] = created_by
        
        # Extract contextual information from payload
        payload = event.get("payload")
        if isinstance(payload, dict):
            # Slack context
            if "channelId" in payload:
                activity["slackChannelId"] = str(payload["channelId"])
            if "threadTs" in payload:
                activity["slackThreadTs"] = str(payload["threadTs"])
            if "slackUserId" in payload:
                activity["slackUserId"] = str(payload["slackUserId"])
            
            # Agent operation details
            if event_type == "agent_completion":
                activity["summary"] = payload.get("purpose", "")[:200]
                activity["success"] = payload.get("success", True)
                activity["steps"] = payload.get("steps")
                activity["durationMs"] = payload.get("durationMs")
                activity["operationType"] = payload.get("operationType")
            
            # Error context
            if "error" in payload:
                activity["error"] = str(payload["error"])[:200]
            
            # Policy checks
            policy_checks = event.get("policyChecks")
            if isinstance(policy_checks, list) and policy_checks:
                failed_checks = [pc for pc in policy_checks if isinstance(pc, dict) and str(pc.get("status") or "").lower() == "fail"]
                if failed_checks:
                    activity["policyFailures"] = len(failed_checks)
        
        activities.append(activity)
    
    # Sort by relevance and recency
    activities.sort(
        key=lambda a: (
            a.get("createdAt", ""),
            -a.get("relevanceScore", 0.0),
        ),
        reverse=True,
    )
    
    return activities


def build_agent_diagnostics(
    *,
    hours: int = 24,
    user_sub: str | None = None,
    rfp_id: str | None = None,
    channel_id: str | None = None,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Build comprehensive agent diagnostics including metrics and recent activities.
    
    Enhanced with:
    - Error handling and graceful degradation
    - Contextual filtering (user, RFP, channel)
    - Caching to avoid expensive repeated queries
    - Rich activity context with correlation IDs
    
    Args:
        hours: Number of hours to look back for diagnostics
        user_sub: Optional user filter for activities
        rfp_id: Optional RFP filter for activities
        channel_id: Optional Slack channel filter
        use_cache: Whether to use cached results if available
        force_refresh: Force refresh even if cache is valid
    
    Returns:
        Dict with metrics, activities summary, and formatted text summary
    """
    h = max(1, min(168, int(hours or 24)))  # Max 1 week
    end = _now()
    start = end - timedelta(hours=h)
    start_iso = _iso(start)
    
    # Check cache (if using cache and not forcing refresh)
    cache_key = f"{hours}_{user_sub or 'all'}_{rfp_id or 'all'}_{channel_id or 'all'}"
    if use_cache and not force_refresh and cache_key in _diagnostics_cache:
        cached_time, cached_data = _diagnostics_cache[cache_key]
        age = (end - cached_time).total_seconds()
        if age < CACHE_TTL_SECONDS:
            log.debug("diagnostics_cache_hit", cache_key=cache_key, age_seconds=age)
            return cached_data
    
    # Build diagnostics with graceful degradation for each data source
    diagnostics: dict[str, Any] = {
        "ok": True,
        "window": {
            "start": start_iso,
            "end": _iso(end),
            "hours": h,
        },
        "filters": {
            "userSub": user_sub,
            "rfpId": rfp_id,
            "channelId": channel_id,
        },
        "dataSourceStatus": {},
    }
    
    # Get daily report (graceful degradation)
    daily_report = _safe_get_data_source("daily_report", build_northstar_daily_report, hours=h)
    if daily_report:
        diagnostics["dailyReport"] = daily_report
        diagnostics["dataSourceStatus"]["dailyReport"] = "ok"
    else:
        diagnostics["dailyReport"] = {}
        diagnostics["dataSourceStatus"]["dailyReport"] = "failed"
    
    # Get agent metrics (graceful degradation)
    metrics = _safe_get_data_source("metrics", get_agent_metrics, since_iso=start_iso)
    if metrics:
        diagnostics["metrics"] = metrics
        diagnostics["dataSourceStatus"]["metrics"] = "ok"
    else:
        diagnostics["metrics"] = {
            "count": 0,
            "avg_duration_ms": 0,
            "avg_steps": 0,
            "success_rate": 0.0,
        }
        diagnostics["dataSourceStatus"]["metrics"] = "failed"
    
    # Get recent jobs (graceful degradation)
    try:
        recent_jobs = list_recent_jobs(limit=20)
        diagnostics["recentJobs"] = recent_jobs[:20]
        diagnostics["dataSourceStatus"]["jobs"] = "ok"
    except Exception as e:
        log.warning("diagnostics_jobs_failed", error=str(e))
        diagnostics["recentJobs"] = []
        diagnostics["dataSourceStatus"]["jobs"] = "failed"
    
    # Get recent events for detailed activity (graceful degradation)
    try:
        events = list_recent_events_global(since_iso=start_iso, limit=200)  # Get more for filtering
        diagnostics["dataSourceStatus"]["events"] = "ok"
    except Exception as e:
        log.warning("diagnostics_events_failed", error=str(e))
        events = []
        diagnostics["dataSourceStatus"]["events"] = "failed"
    
    # Build enriched activity summary with context
    activities = _build_activities_with_context(
        events=events,
        limit=100,  # More for better context
        user_sub=user_sub,
        rfp_id=rfp_id,
        channel_id=channel_id,
    )
    diagnostics["recentActivities"] = activities[:50]
    
    # Build formatted text summary with contextual information
    summary_lines: list[str] = []
    summary_lines.append(f"Agent Diagnostics Report (last {h} hours)")
    
    # Add context filters to summary
    if user_sub or rfp_id or channel_id:
        summary_lines.append("")
        summary_lines.append("Filters:")
        if user_sub:
            summary_lines.append(f"- User: {user_sub[:20]}...")
        if rfp_id:
            summary_lines.append(f"- RFP: {rfp_id}")
        if channel_id:
            summary_lines.append(f"- Channel: {channel_id}")
    
    summary_lines.append("")
    
    # Metrics section
    summary_lines.append("Metrics:")
    metrics_data = diagnostics["metrics"]
    summary_lines.append(f"- Total operations: {metrics_data.get('count', 0)}")
    if metrics_data.get("count", 0) > 0:
        summary_lines.append(f"- Average duration: {metrics_data.get('avg_duration_ms', 0)}ms")
        summary_lines.append(f"- Average steps: {metrics_data.get('avg_steps', 0)}")
        summary_lines.append(f"- Success rate: {metrics_data.get('success_rate', 0.0):.1%}")
        if metrics_data.get("p95_duration_ms"):
            summary_lines.append(f"- P95 duration: {metrics_data.get('p95_duration_ms')}ms")
        if metrics_data.get("p99_duration_ms"):
            summary_lines.append(f"- P99 duration: {metrics_data.get('p99_duration_ms')}ms")
    summary_lines.append("")
    
    # Activity summary from daily report
    events_data = diagnostics.get("dailyReport", {}).get("events", {})
    if events_data:
        summary_lines.append("Activity Summary:")
        summary_lines.append(f"- Events logged: {events_data.get('count', 0)}")
        
        by_type = events_data.get("byType", {})
        if by_type:
            summary_lines.append("- Events by type:")
            for event_type, count in sorted(by_type.items(), key=lambda kv: -kv[1])[:10]:
                summary_lines.append(f"  - {event_type}: {count}")
        
        by_tool = events_data.get("byTool", {})
        if by_tool:
            summary_lines.append("- Tools used:")
            for tool, count in sorted(by_tool.items(), key=lambda kv: -kv[1])[:10]:
                summary_lines.append(f"  - {tool}: {count}")
        summary_lines.append("")
    
    # Opportunities touched
    opps_touched = diagnostics.get("dailyReport", {}).get("opportunitiesTouched", [])
    if opps_touched:
        summary_lines.append(f"- Opportunities touched: {len(opps_touched)}")
        if rfp_id is None:  # Only show list if not filtered to one RFP
            summary_lines.append(f"  (Sample: {', '.join(opps_touched[:5])})")
        summary_lines.append("")
    
    # Recent jobs
    recent_jobs = diagnostics.get("recentJobs", [])
    if recent_jobs:
        running_jobs = [j for j in recent_jobs if str(j.get("status") or "").strip().lower() == "running"]
        completed_jobs = [j for j in recent_jobs if str(j.get("status") or "").strip().lower() == "completed"]
        failed_jobs = [j for j in recent_jobs if str(j.get("status") or "").strip().lower() == "failed"]
        
        summary_lines.append("Recent Jobs:")
        summary_lines.append(f"- Running: {len(running_jobs)}")
        summary_lines.append(f"- Completed: {len(completed_jobs)}")
        summary_lines.append(f"- Failed: {len(failed_jobs)}")
        
        if running_jobs:
            summary_lines.append("- Currently running:")
            for job in running_jobs[:5]:
                job_type = str(job.get("jobType") or "").strip()
                job_id = str(job.get("jobId") or "").strip()
                job_rfp = job.get("scope", {}).get("rfpId") if isinstance(job.get("scope"), dict) else None
                line = f"  - {job_type} ({job_id})"
                if job_rfp:
                    line += f" [RFP: {job_rfp}]"
                summary_lines.append(line)
        summary_lines.append("")
    
    # Change proposals
    cps_data = diagnostics.get("dailyReport", {}).get("changeProposals", {})
    if cps_data:
        summary_lines.append("Self-Improvement:")
        summary_lines.append(f"- Change proposals created: {cps_data.get('recentCount', 0)}")
        summary_lines.append(f"- PRs opened: {cps_data.get('prsOpened', 0)}")
        summary_lines.append(f"- Merged: {cps_data.get('merged', 0)}")
        if cps_data.get("failed", 0) > 0:
            summary_lines.append(f"- Failed: {cps_data.get('failed', 0)}")
        summary_lines.append("")
    
    # Recent activities with context
    if activities:
        summary_lines.append("Recent Activities:")
        for activity in activities[:15]:  # Show top 15
            activity_type = activity.get("type", "unknown")
            tool = activity.get("tool", "")
            summary = activity.get("summary", "")
            timestamp = activity.get("createdAt", "")[:19] if activity.get("createdAt") else ""
            rfp_id_act = activity.get("rfpId", "")
            correlation_id = activity.get("correlationId", "")
            success = activity.get("success")
            
            line = f"- {timestamp}: {activity_type}"
            if tool:
                line += f" ({tool})"
            if rfp_id_act and not rfp_id:  # Only show if not already filtered
                line += f" [RFP: {rfp_id_act[:15]}...]"
            if correlation_id:
                line += f" [Corr: {correlation_id[:12]}...]"
            if success is False:
                line += " [FAILED]"
            if summary:
                line += f": {summary[:100]}"
            summary_lines.append(line)
    
    # Data source status
    failed_sources = [
        name for name, status in diagnostics["dataSourceStatus"].items()
        if status == "failed"
    ]
    if failed_sources:
        summary_lines.append("")
        summary_lines.append(f"⚠️  Note: Some data sources failed: {', '.join(failed_sources)}")
        summary_lines.append("Results may be incomplete.")
    
    diagnostics["summaryText"] = "\n".join(summary_lines).strip()
    
    # Store diagnostics in memory (best-effort, don't fail if it errors)
    try:
        add_diagnostics_memory(
            scope_id="GLOBAL",
            diagnostics_data=diagnostics,
            hours=h,
            source="diagnostics_service",
        )
    except Exception as e:
        log.warning("diagnostics_memory_store_failed", error=str(e))
        # Non-critical, don't fail
    
    # Update cache
    if use_cache:
        _diagnostics_cache[cache_key] = (end, diagnostics)
        # Clean old cache entries (keep only last 10)
        if len(_diagnostics_cache) > 10:
            oldest_key = min(_diagnostics_cache.keys(), key=lambda k: _diagnostics_cache[k][0])
            _diagnostics_cache.pop(oldest_key, None)
    
    return diagnostics
