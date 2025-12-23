from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from ..repositories.agent.jobs_repo import (
    cancel_job,
    create_job,
    delete_job,
    get_job,
    list_jobs_by_scope,
    list_jobs_by_type,
    list_recent_jobs,
    update_job,
)
from ..repositories.agent.events_repo import list_recent_events_global
from ..domain.agents.telemetry.agent_telemetry import get_agent_metrics
from ..domain.agents.telemetry.agent_diagnostics import build_agent_diagnostics
from ..observability.logging import get_logger

log = get_logger("agents_router")

router = APIRouter(tags=["agents"])


def _user_sub(request: Request) -> str | None:
    """Extract user sub from request."""
    user = getattr(getattr(request, "state", None), "user", None)
    return str(getattr(user, "sub", "") or "").strip() if user else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/infrastructure")
def get_infrastructure_info() -> dict[str, Any]:
    """Get agent infrastructure information (no trailing slash)."""
    return _get_infrastructure_info_impl()


@router.get("/infrastructure/")
def get_infrastructure_info_slash() -> dict[str, Any]:
    """Get agent infrastructure information (with trailing slash)."""
    return _get_infrastructure_info_impl()


def _get_infrastructure_info_impl() -> dict[str, Any]:
    """
    Get agent infrastructure information.
    
    Returns information about agent infrastructure including:
    - Base agent class info
    - Available workers
    - Scheduled jobs configuration
    """
    return {
        "ok": True,
        "infrastructure": {
            "baseAgentClass": "app.agents.base.agent.Agent",
            "workers": [
                {
                    "name": "ambient_tick_worker",
                    "description": "Ambient tick worker for periodic tasks",
                    "schedule": "rate(15 minutes)",
                },
                {
                    "name": "agent_job_runner",
                    "description": "Executes scheduled agent jobs",
                    "schedule": "rate(240 minutes)",
                },
                {
                    "name": "daily_report_worker",
                    "description": "Generates daily reports",
                    "schedule": "cron(0 8 * * ? *) America/Chicago",
                },
                {
                    "name": "external_context_aggregator_worker",
                    "description": "Aggregates external context",
                    "schedule": "rate(240 minutes)",
                },
            ],
            "memory": {
                "type": "OpenSearch + DynamoDB",
                "tableName": "northstar-agent-memory-{environment}",
            },
        },
    }


@router.get("/jobs")
def list_jobs(
    request: Request,
    limit: int = 50,
    status: str | None = None,
    job_type: str | None = None,
    rfp_id: str | None = None,
) -> dict[str, Any]:
    """List agent jobs with optional filtering (no trailing slash)."""
    return _list_jobs_impl(request, limit, status, job_type, rfp_id)


@router.get("/jobs/")
def list_jobs_slash(
    request: Request,
    limit: int = 50,
    status: str | None = None,
    job_type: str | None = None,
    rfp_id: str | None = None,
) -> dict[str, Any]:
    """List agent jobs with optional filtering (with trailing slash)."""
    return _list_jobs_impl(request, limit, status, job_type, rfp_id)


def _list_jobs_impl(
    request: Request,
    limit: int = 50,
    status: str | None = None,
    job_type: str | None = None,
    rfp_id: str | None = None,
) -> dict[str, Any]:
    """
    List agent jobs with optional filtering.
    
    Args:
        limit: Maximum number of jobs to return (1-100)
        status: Filter by status (queued, running, checkpointed, completed, failed, cancelled)
        job_type: Filter by job type
        rfp_id: Filter by RFP ID in scope
    """
    lim = max(1, min(100, int(limit or 50)))
    
    if rfp_id:
        jobs = list_jobs_by_scope(scope={"rfpId": rfp_id}, limit=lim, status=status)
    elif job_type:
        jobs = list_jobs_by_type(job_type=job_type, limit=lim, status=status)
    else:
        jobs = list_recent_jobs(limit=lim, status=status)
    
    # Count by status
    status_counts: dict[str, int] = {}
    for job in jobs:
        s = str(job.get("status") or "unknown").strip()
        status_counts[s] = status_counts.get(s, 0) + 1
    
    return {
        "ok": True,
        "jobs": jobs,
        "count": len(jobs),
        "statusCounts": status_counts,
    }


@router.get("/jobs/{job_id}")
def get_job_detail(job_id: str) -> dict[str, Any]:
    """Get detailed information about a specific agent job."""
    jid = str(job_id or "").strip()
    if not jid:
        raise HTTPException(status_code=400, detail="job_id is required")
    
    job = get_job(job_id=jid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {"ok": True, "job": job}


@router.post("/jobs")
def create_job_endpoint(request: Request, body: dict = Body(...)) -> dict[str, Any]:
    """
    Create a new agent job.
    
    Body:
        - jobType: string (required)
        - scope: object (required) - e.g., {"rfpId": "..."}
        - dueAt: string (required) - ISO timestamp
        - payload: object (optional)
        - dependsOn: string[] (optional) - List of job IDs this job depends on
    """
    user_sub = _user_sub(request)
    
    job_type = str((body or {}).get("jobType") or "").strip()
    scope = (body or {}).get("scope")
    due_at = str((body or {}).get("dueAt") or "").strip()
    payload = (body or {}).get("payload")
    depends_on = (body or {}).get("dependsOn")
    
    if not job_type:
        raise HTTPException(status_code=400, detail="jobType is required")
    if not scope or not isinstance(scope, dict):
        raise HTTPException(status_code=400, detail="scope is required and must be an object")
    if not due_at:
        raise HTTPException(status_code=400, detail="dueAt is required")
    
    try:
        # Validate ISO timestamp
        datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="dueAt must be a valid ISO timestamp")
    
    job = create_job(
        job_type=job_type,
        scope=scope,
        due_at=due_at,
        payload=payload if isinstance(payload, dict) else None,
        requested_by_user_sub=user_sub,
        depends_on=depends_on if isinstance(depends_on, list) else None,
    )
    
    return {"ok": True, "job": job}


@router.put("/jobs/{job_id}")
def update_job_endpoint(job_id: str, request: Request, body: dict = Body(...)) -> dict[str, Any]:
    """
    Update an agent job. Only allowed for queued or checkpointed jobs.
    
    Body:
        - dueAt: string (optional) - ISO timestamp
        - payload: object (optional)
        - scope: object (optional)
        - dependsOn: string[] (optional)
    """
    jid = str(job_id or "").strip()
    if not jid:
        raise HTTPException(status_code=400, detail="job_id is required")
    
    updates: dict[str, Any] = {}
    
    if "dueAt" in body:
        due_at = str(body.get("dueAt") or "").strip()
        if due_at:
            try:
                datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                updates["dueAt"] = due_at
            except Exception:
                raise HTTPException(status_code=400, detail="dueAt must be a valid ISO timestamp")
    
    if "payload" in body:
        updates["payload"] = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    
    if "scope" in body:
        scope = body.get("scope")
        if isinstance(scope, dict):
            updates["scope"] = scope
        else:
            raise HTTPException(status_code=400, detail="scope must be an object")
    
    if "dependsOn" in body:
        depends_on = body.get("dependsOn")
        if isinstance(depends_on, list):
            updates["dependsOn"] = [str(d) for d in depends_on if str(d).strip()][:20]
        else:
            raise HTTPException(status_code=400, detail="dependsOn must be an array")
    
    if not updates:
        raise HTTPException(status_code=400, detail="No valid updates provided")
    
    updated = update_job(job_id=jid, updates=updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found or cannot be updated")
    
    return {"ok": True, "job": updated}


@router.delete("/jobs/{job_id}")
def delete_job_endpoint(job_id: str) -> dict[str, Any]:
    """
    Delete an agent job permanently. Only works for cancelled, completed, or failed jobs.
    For queued or running jobs, use the cancel endpoint first.
    """
    jid = str(job_id or "").strip()
    if not jid:
        raise HTTPException(status_code=400, detail="job_id is required")
    
    try:
        delete_job(job_id=jid)
        return {"ok": True, "message": "Job deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("delete_job_failed", job_id=jid, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete job")


@router.post("/jobs/{job_id}/cancel")
def cancel_job_endpoint(job_id: str) -> dict[str, Any]:
    """
    Cancel a job (mark as cancelled). Only works for queued or checkpointed jobs.
    """
    jid = str(job_id or "").strip()
    if not jid:
        raise HTTPException(status_code=400, detail="job_id is required")
    
    cancelled = cancel_job(job_id=jid)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Job not found or cannot be cancelled")
    
    return {"ok": True, "job": cancelled}


@router.get("/activity")
def get_recent_activity(
    hours: int = 24,
    limit: int = 100,
    rfp_id: str | None = None,
    user_sub_filter: str | None = None,
) -> dict[str, Any]:
    """Get recent agent activity/logs (no trailing slash)."""
    return _get_recent_activity_impl(hours, limit, rfp_id, user_sub_filter)


@router.get("/activity/")
def get_recent_activity_slash(
    hours: int = 24,
    limit: int = 100,
    rfp_id: str | None = None,
    user_sub_filter: str | None = None,
) -> dict[str, Any]:
    """Get recent agent activity/logs (with trailing slash)."""
    return _get_recent_activity_impl(hours, limit, rfp_id, user_sub_filter)


def _get_recent_activity_impl(
    hours: int = 24,
    limit: int = 100,
    rfp_id: str | None = None,
    user_sub_filter: str | None = None,
) -> dict[str, Any]:
    """
    Get recent agent activity/logs.
    
    Args:
        hours: Number of hours to look back (1-72)
        limit: Maximum number of events to return (1-500)
        rfp_id: Filter by RFP ID
        user_sub_filter: Filter by user sub
    """
    h = max(1, min(72, int(hours or 24)))
    lim = max(1, min(500, int(limit or 100)))
    
    since = datetime.now(timezone.utc) - timedelta(hours=h)
    since_iso = since.isoformat().replace("+00:00", "Z")
    
    events = list_recent_events_global(since_iso=since_iso, limit=lim * 2)  # Get more for filtering
    
    # Filter by RFP ID if provided
    if rfp_id:
        events = [
            e for e in events
            if isinstance(e, dict) and str(e.get("rfpId") or "").strip() == rfp_id
        ]
    
    # Filter by user sub if provided
    if user_sub_filter:
        events = [
            e for e in events
            if isinstance(e, dict) and user_sub_filter in str(e.get("createdBy") or "")
        ]
    
    events = events[:lim]
    
    return {
        "ok": True,
        "since": since_iso,
        "count": len(events),
        "events": events,
    }


@router.get("/metrics")
def get_metrics(
    hours: int = 24,
    operation_type: str | None = None,
) -> dict[str, Any]:
    """Get agent metrics/telemetry (no trailing slash)."""
    return _get_metrics_impl(hours, operation_type)


@router.get("/metrics/")
def get_metrics_slash(
    hours: int = 24,
    operation_type: str | None = None,
) -> dict[str, Any]:
    """Get agent metrics/telemetry (with trailing slash)."""
    return _get_metrics_impl(hours, operation_type)


def _get_metrics_impl(
    hours: int = 24,
    operation_type: str | None = None,
) -> dict[str, Any]:
    """
    Get agent metrics/telemetry.
    
    Args:
        hours: Number of hours to look back (1-168)
        operation_type: Filter by operation type (optional)
    """
    h = max(1, min(168, int(hours or 24)))
    since = datetime.now(timezone.utc) - timedelta(hours=h)
    since_iso = since.isoformat().replace("+00:00", "Z")
    
    metrics = get_agent_metrics(since_iso=since_iso, operation_type=operation_type)
    
    return {
        "ok": True,
        "since": since_iso,
        "hours": h,
        "operationType": operation_type,
        "metrics": metrics,
    }


@router.get("/diagnostics")
def get_diagnostics(
    hours: int = 24,
    rfp_id: str | None = None,
    user_sub: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """Get comprehensive agent diagnostics (no trailing slash)."""
    return _get_diagnostics_impl(hours, rfp_id, user_sub, channel_id)


@router.get("/diagnostics/")
def get_diagnostics_slash(
    hours: int = 24,
    rfp_id: str | None = None,
    user_sub: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """Get comprehensive agent diagnostics (with trailing slash)."""
    return _get_diagnostics_impl(hours, rfp_id, user_sub, channel_id)


def _get_diagnostics_impl(
    hours: int = 24,
    rfp_id: str | None = None,
    user_sub: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """
    Get comprehensive agent diagnostics.
    
    Includes metrics, recent activities, jobs, and more.
    """
    diagnostics = build_agent_diagnostics(
        hours=hours,
        rfp_id=rfp_id,
        user_sub=user_sub,
        channel_id=channel_id,
    )
    
    return {"ok": True, **diagnostics}


@router.get("/workers")
def get_workers_summary() -> dict[str, Any]:
    """Get summary information about worker processes (no trailing slash)."""
    return _get_workers_summary_impl()


@router.get("/workers/")
def get_workers_summary_slash() -> dict[str, Any]:
    """Get summary information about worker processes (with trailing slash)."""
    return _get_workers_summary_impl()


def _get_workers_summary_impl() -> dict[str, Any]:
    """
    Get summary information about worker processes.
    
    Returns information about scheduled workers and their status.
    """
    return {
        "ok": True,
        "workers": [
            {
                "name": "ambient_tick_worker",
                "schedule": "rate(15 minutes)",
                "description": "Runs ambient tick tasks",
                "logGroup": "/ecs/northstar-ambient-{environment}",
            },
            {
                "name": "agent_job_runner",
                "schedule": "rate(240 minutes)",
                "description": "Executes scheduled agent jobs",
                "logGroup": "/ecs/northstar-job-runner-{environment}",
                "resources": {"cpu": "2048", "memory": "4096"},
            },
            {
                "name": "daily_report_worker",
                "schedule": "cron(0 8 * * ? *) America/Chicago",
                "description": "Generates daily reports at 8am CT",
                "logGroup": "/ecs/northstar-daily-report-{environment}",
            },
            {
                "name": "external_context_aggregator_worker",
                "schedule": "rate(240 minutes)",
                "description": "Aggregates external context data",
                "logGroup": "/ecs/northstar-external-context-aggregator-{environment}",
                "resources": {"cpu": "2048", "memory": "4096"},
            },
        ],
        "note": "Worker status is determined by EventBridge Scheduler and ECS task execution. Check CloudWatch Logs for detailed execution logs.",
    }
