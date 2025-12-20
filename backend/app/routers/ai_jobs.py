from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..services.ai_jobs_repo import get_job, list_recent_jobs

router = APIRouter(tags=["ai_jobs"])


@router.get("/jobs/{job_id}")
def get_one(job_id: str):
    job = get_job(str(job_id or "").strip())
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


@router.get("/jobs")
def list_jobs(request: Request, limit: int = 50, nextToken: str | None = None):
    # Read-only list for operators; we intentionally do not scope by user yet.
    # (In production, this should be protected by RBAC and/or an admin-only route.)
    _ = request
    return list_recent_jobs(limit=limit, next_token=nextToken)

