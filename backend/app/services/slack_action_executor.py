from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger
from .rfps_repo import get_rfp_by_id, list_rfp_proposal_summaries
from .workflow_tasks_repo import (
    assign_task,
    complete_task,
    compute_pipeline_stage,
    seed_missing_tasks_for_stage,
)

log = get_logger("slack_action_executor")


def execute_action(*, action_id: str, kind: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a previously proposed action.
    Returns a structured result dict safe to show in Slack.
    """
    k = str(kind or "").strip()
    a = args if isinstance(args, dict) else {}

    if k == "seed_tasks_for_rfp":
        rfp_id = str(a.get("rfpId") or "").strip()
        if not rfp_id:
            return {"ok": False, "error": "missing_rfpId"}

        rfp = get_rfp_by_id(rfp_id)
        if not rfp:
            return {"ok": False, "error": "rfp_not_found"}
        proposals = list_rfp_proposal_summaries(rfp_id) or []
        stage = compute_pipeline_stage(rfp=rfp, proposals_for_rfp=proposals)
        created = seed_missing_tasks_for_stage(rfp_id=rfp_id, stage=stage, proposal_id=None)
        return {"ok": True, "action": k, "rfpId": rfp_id, "stage": stage, "createdCount": len(created)}

    if k == "assign_task":
        task_id = str(a.get("taskId") or "").strip()
        assignee = str(a.get("assigneeUserSub") or "").strip()
        if not task_id:
            return {"ok": False, "error": "missing_taskId"}
        if not assignee:
            return {"ok": False, "error": "missing_assigneeUserSub"}
        if assignee.lower() == "me":
            # Slack workspace is open; we don't have a stable mapping here yet.
            return {"ok": False, "error": "assignee_me_not_supported_in_slack"}

        updated = assign_task(task_id=task_id, assignee_user_sub=assignee, assignee_display_name=None)
        if not updated:
            return {"ok": False, "error": "task_not_found"}
        return {"ok": True, "action": k, "task": updated}

    if k == "complete_task":
        task_id = str(a.get("taskId") or "").strip()
        if not task_id:
            return {"ok": False, "error": "missing_taskId"}
        updated = complete_task(task_id=task_id, completed_by_user_sub=None)
        if not updated:
            return {"ok": False, "error": "task_not_found"}
        return {"ok": True, "action": k, "task": updated}

    return {"ok": False, "error": "unknown_action", "action": k}

