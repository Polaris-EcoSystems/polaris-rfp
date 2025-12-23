from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .agent_diagnostics import build_agent_diagnostics
from .agent_events_repo import append_event
from .agent_jobs_repo import create_job
from ...observability.logging import get_logger
from ...settings import settings

log = get_logger("agent_diagnostics_scheduler")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def next_diagnostics_update_due_iso(*, minutes: int = 60) -> str:
    """
    Compute the next scheduled diagnostics update time.
    
    Args:
        minutes: Interval in minutes (default 60 = hourly)
    
    Returns:
        ISO timestamp string for next due time
    """
    now = datetime.now(timezone.utc)
    next_due = now + timedelta(minutes=minutes)
    return next_due.isoformat().replace("+00:00", "Z")


def run_diagnostics_update_and_reschedule(*, hours: int = 24, reschedule_minutes: int = 60) -> dict[str, Any]:
    """
    Run diagnostics update (builds and stores diagnostics in memory),
    then schedule the next update.
    
    This function is idempotent - it can be called multiple times safely.
    
    Args:
        hours: Number of hours to look back for diagnostics
        reschedule_minutes: Minutes until next update (default 60 = hourly)
    
    Returns:
        Dict with update results and next scheduled time
    """
    started_at = _now_iso()
    
    try:
        # Build diagnostics (this stores them in memory automatically)
        diagnostics = build_agent_diagnostics(
            hours=hours,
            use_cache=False,  # Always refresh for scheduled updates
            force_refresh=True,
        )
        
        # Log the update
        try:
            append_event(
                rfp_id="rfp_diagnostics_update",
                type="agent_diagnostics_updated",
                tool="agent_diagnostics_scheduler",
                payload={
                    "window": diagnostics.get("window", {}),
                    "metricsCount": diagnostics.get("metrics", {}).get("count", 0),
                    "dataSourceStatus": diagnostics.get("dataSourceStatus", {}),
                },
                created_by="system",
                correlation_id=None,
            )
        except Exception as e:
            log.warning("diagnostics_event_log_failed", error=str(e))
        
        # Schedule next update
        next_due = next_diagnostics_update_due_iso(minutes=reschedule_minutes)
        try:
            create_job(
                job_type="agent_diagnostics_update",
                scope={"env": settings.normalized_environment},
                payload={
                    "hours": hours,
                    "rescheduleMinutes": reschedule_minutes,
                },
                due_at=next_due,
            )
            log.info("diagnostics_next_update_scheduled", next_due=next_due, reschedule_minutes=reschedule_minutes)
        except Exception as e:
            log.warning("diagnostics_reschedule_failed", error=str(e))
        
        finished_at = _now_iso()
        return {
            "ok": True,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "nextDueIso": next_due,
            "diagnostics": {
                "metricsCount": diagnostics.get("metrics", {}).get("count", 0),
                "activitiesCount": len(diagnostics.get("recentActivities", [])),
            },
        }
    
    except Exception as e:
        log.exception("diagnostics_update_failed", error=str(e))
        finished_at = _now_iso()
        
        # Still try to reschedule even on failure
        next_due = next_diagnostics_update_due_iso(minutes=reschedule_minutes)
        try:
            create_job(
                job_type="agent_diagnostics_update",
                scope={"env": settings.normalized_environment},
                payload={
                    "hours": hours,
                    "rescheduleMinutes": reschedule_minutes,
                },
                due_at=next_due,
            )
        except Exception:
            pass
        
        return {
            "ok": False,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "nextDueIso": next_due,
            "error": str(e),
        }
