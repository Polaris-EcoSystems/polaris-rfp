from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from ..repositories.rfp.rfps_repo import get_rfp_by_id, list_rfp_proposal_summaries
from ..repositories.outbox.outbox_repo import enqueue_event
from ..repositories.workflows.tasks_repo import (
    assign_task,
    complete_task,
    get_task_by_id,
    list_tasks_for_rfp,
    reopen_task,
)
from ..modules.workflow.workflow_service import sync_for_rfp


router = APIRouter(tags=["tasks"])


class AssignTaskRequest(BaseModel):
    assigneeUserSub: str = Field(..., min_length=1)
    assigneeDisplayName: str | None = None


def _list_rfp_tasks_impl(rfpId: str):
    rid = str(rfpId or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="rfpId is required")
    return list_tasks_for_rfp(rfp_id=rid, limit=500, next_token=None)


@router.get("/rfps/{rfpId}/tasks")
def list_rfp_tasks_plural(rfpId: str):
    return _list_rfp_tasks_impl(rfpId)


@router.get("/rfp/{rfpId}/tasks")
def list_rfp_tasks(rfpId: str):
    return _list_rfp_tasks_impl(rfpId)


@router.get("/rfp/{rfpId}/tasks/", include_in_schema=False)
def list_rfp_tasks_slash(rfpId: str):
    return _list_rfp_tasks_impl(rfpId)


def _seed_rfp_tasks_impl(rfpId: str):
    rid = str(rfpId or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="rfpId is required")

    rfp = get_rfp_by_id(rid)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    proposals = list_rfp_proposal_summaries(rid) or []

    proposal_id: str | None = None
    try:
        if proposals:
            p = sorted(proposals, key=lambda x: str(x.get("updatedAt") or ""), reverse=True)[0]
            proposal_id = str(p.get("proposalId") or "").strip() or None
    except Exception:
        proposal_id = None

    sync = sync_for_rfp(rfp_id=rid, actor_user_sub=None, proposal_id=proposal_id)
    tasks = list_tasks_for_rfp(rfp_id=rid, limit=500, next_token=None)
    return {
        "ok": True,
        "rfpId": rid,
        "stage": sync.get("stage"),
        "createdCount": int(sync.get("seededTasks") or 0),
        **tasks,
    }


@router.post("/rfps/{rfpId}/tasks/seed")
def seed_rfp_tasks_plural(rfpId: str):
    return _seed_rfp_tasks_impl(rfpId)


@router.post("/rfp/{rfpId}/tasks/seed")
def seed_rfp_tasks(rfpId: str):
    return _seed_rfp_tasks_impl(rfpId)


@router.post("/rfp/{rfpId}/tasks/seed/", include_in_schema=False)
def seed_rfp_tasks_slash(rfpId: str):
    return _seed_rfp_tasks_impl(rfpId)


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
        enqueue_event(
            event_type="slack.task_assigned",
            payload={"task": updated, "actorUserSub": actor_sub or None},
            dedupe_key=f"task_assigned:{str(updated.get('_id') or updated.get('taskId') or '')}:{str(updated.get('updatedAt') or '')}",
        )
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
        enqueue_event(
            event_type="slack.task_completed",
            payload={"task": updated, "actorUserSub": actor_sub},
            dedupe_key=f"task_completed:{str(updated.get('_id') or updated.get('taskId') or '')}:{str(updated.get('updatedAt') or '')}",
        )
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


def _get_one_task_impl(taskId: str):
    tid = str(taskId or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="taskId is required")
    t = get_task_by_id(tid)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True, "task": t}


@router.get("/tasks/{taskId}")
def get_one_task(taskId: str):
    return _get_one_task_impl(taskId)


@router.get("/tasks/{taskId}/", include_in_schema=False)
def get_one_task_slash(taskId: str):
    return _get_one_task_impl(taskId)

