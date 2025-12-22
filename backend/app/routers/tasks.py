from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from ..repositories.rfp.rfps_repo import get_rfp_by_id, list_rfp_proposal_summaries
from ..services.slack_notifier import notify_task_assigned, notify_task_completed
from ..services.workflow_tasks_repo import (
    assign_task,
    complete_task,
    compute_pipeline_stage,
    get_task_by_id,
    list_tasks_for_rfp,
    reopen_task,
    seed_missing_tasks_for_stage,
)


router = APIRouter(tags=["tasks"])


class AssignTaskRequest(BaseModel):
    assigneeUserSub: str = Field(..., min_length=1)
    assigneeDisplayName: str | None = None


@router.get("/rfps/{rfpId}/tasks")
@router.get("/rfp/{rfpId}/tasks")
def list_rfp_tasks(rfpId: str):
    rid = str(rfpId or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="rfpId is required")
    return list_tasks_for_rfp(rfp_id=rid, limit=500, next_token=None)


@router.post("/rfps/{rfpId}/tasks/seed")
@router.post("/rfp/{rfpId}/tasks/seed")
def seed_rfp_tasks(rfpId: str):
    rid = str(rfpId or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="rfpId is required")

    rfp = get_rfp_by_id(rid)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    proposals = list_rfp_proposal_summaries(rid) or []
    stage = compute_pipeline_stage(rfp=rfp, proposals_for_rfp=proposals)

    proposal_id: str | None = None
    try:
        if proposals:
            p = sorted(proposals, key=lambda x: str(x.get("updatedAt") or ""), reverse=True)[0]
            proposal_id = str(p.get("proposalId") or "").strip() or None
    except Exception:
        proposal_id = None

    created = seed_missing_tasks_for_stage(rfp_id=rid, stage=stage, proposal_id=proposal_id)
    tasks = list_tasks_for_rfp(rfp_id=rid, limit=500, next_token=None)
    return {
        "ok": True,
        "rfpId": rid,
        "stage": stage,
        "createdCount": len(created),
        "created": created,
        **tasks,
    }


@router.post("/tasks/{taskId}/assign")
def assign_one_task(taskId: str, request: Request, body: AssignTaskRequest):
    tid = str(taskId or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="taskId is required")

    user = getattr(request.state, "user", None)
    actor_sub = str(getattr(user, "sub", "") or "").strip() if user else ""

    assignee_sub = str(body.assigneeUserSub or "").strip()
    if assignee_sub.lower() == "me":
        if not actor_sub:
            raise HTTPException(status_code=401, detail="Unauthorized")
        assignee_sub = actor_sub

    updated = assign_task(
        task_id=tid,
        assignee_user_sub=assignee_sub,
        assignee_display_name=body.assigneeDisplayName,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")

    # Best-effort Slack notifications.
    try:
        notify_task_assigned(task=updated, actor_user_sub=actor_sub or None)
    except Exception:
        pass

    return {"ok": True, "task": updated}


@router.post("/tasks/{taskId}/complete")
def complete_one_task(taskId: str, request: Request, body: dict = Body(default_factory=dict)):
    tid = str(taskId or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="taskId is required")

    user = getattr(request.state, "user", None)
    actor_sub = str(getattr(user, "sub", "") or "").strip() if user else ""
    if not actor_sub:
        raise HTTPException(status_code=401, detail="Unauthorized")

    updated = complete_task(task_id=tid, completed_by_user_sub=actor_sub)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        notify_task_completed(task=updated, actor_user_sub=actor_sub)
    except Exception:
        pass

    return {"ok": True, "task": updated}


@router.post("/tasks/{taskId}/reopen")
def reopen_one_task(taskId: str, request: Request):
    tid = str(taskId or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="taskId is required")

    # Auth required; only authenticated users can reopen.
    user = getattr(request.state, "user", None)
    actor_sub = str(getattr(user, "sub", "") or "").strip() if user else ""
    if not actor_sub:
        raise HTTPException(status_code=401, detail="Unauthorized")

    updated = reopen_task(task_id=tid)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True, "task": updated}


@router.get("/tasks/{taskId}")
def get_one_task(taskId: str):
    tid = str(taskId or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="taskId is required")
    t = get_task_by_id(tid)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True, "task": t}

