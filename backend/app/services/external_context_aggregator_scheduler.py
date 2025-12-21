"""
Scheduler for external context aggregation jobs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .agent_events_repo import append_event
from .agent_jobs_repo import create_job
from .external_context_aggregator import aggregate_external_context_report, format_aggregation_report_for_slack
from .slack_web import chat_post_message_result
from ..observability.logging import get_logger
from ..settings import settings

log = get_logger("external_context_aggregator_scheduler")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def next_aggregation_due_iso(*, hours: int = 4) -> str:
    """
    Calculate next scheduled run time for external context aggregation.
    
    Args:
        hours: Hours until next run (default: 4)
    
    Returns:
        ISO timestamp string
    """
    next_run = datetime.now(timezone.utc) + timedelta(hours=hours)
    return next_run.isoformat().replace("+00:00", "Z")


def run_external_context_aggregation_and_reschedule(
    *,
    hours: int = 4,
    reschedule_hours: int = 4,
    report_to_slack: bool = True,
) -> dict[str, Any]:
    """
    Run external context aggregation, generate report, and reschedule next run.
    
    Args:
        hours: Time window for aggregation (default: 4 hours)
        reschedule_hours: Hours until next run (default: 4)
        report_to_slack: Whether to post report to Slack (default: True)
    
    Returns:
        Dict with execution results
    """
    started_at = _now_iso()
    
    try:
        # Generate aggregation report
        report = aggregate_external_context_report(hours=hours)
        
        # Post to Slack if enabled
        if report_to_slack:
            try:
                channel = (
                    str(settings.northstar_daily_report_channel or "").strip()
                    or str(settings.slack_rfp_machine_channel or "").strip()
                    or None
                )
                
                if channel and bool(settings.slack_enabled):
                    formatted_report = format_aggregation_report_for_slack(report)
                    result = chat_post_message_result(
                        text=formatted_report,
                        channel=channel,
                        unfurl_links=False,
                    )
                    if result.get("ok"):
                        log.info("external_context_report_sent_to_slack", channel=channel)
                    else:
                        log.warning("external_context_report_slack_failed", error=result.get("error"))
                else:
                    log.debug("external_context_report_skip_slack", reason="no_channel_or_disabled")
            except Exception as e:
                log.warning("external_context_report_slack_exception", error=str(e))
        
        # Log event (using a global scope since this is not RFP-specific)
        try:
            append_event(
                rfp_id="GLOBAL",
                type="external_context_aggregated",
                tool="external_context_aggregator_scheduler",
                payload={
                    "report": report,
                    "hours": hours,
                },
            )
        except Exception:
            # Non-critical: event logging failure shouldn't break aggregation
            pass
        
        # Reschedule next run
        next_due = next_aggregation_due_iso(hours=reschedule_hours)
        create_job(
            job_type="external_context_aggregation",
            scope={"scope_id": "GLOBAL"},
            due_at=next_due,
            payload={
                "hours": hours,
                "rescheduleHours": reschedule_hours,
                "reportToSlack": report_to_slack,
            },
        )
        
        finished_at = _now_iso()
        
        return {
            "ok": True,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "report": report,
            "nextRun": next_due,
        }
    
    except Exception as e:
        log.error("external_context_aggregation_failed", error=str(e), exc_info=True)
        
        # Still reschedule even on failure
        try:
            next_due = next_aggregation_due_iso(hours=reschedule_hours)
            create_job(
                job_type="external_context_aggregation",
                scope={"scope_id": "GLOBAL"},
                due_at=next_due,
                payload={
                    "hours": hours,
                    "rescheduleHours": reschedule_hours,
                    "reportToSlack": report_to_slack,
                },
            )
        except Exception as reschedule_error:
            log.error("external_context_aggregation_reschedule_failed", error=str(reschedule_error))
        
        return {
            "ok": False,
            "startedAt": started_at,
            "finishedAt": _now_iso(),
            "error": str(e),
        }
