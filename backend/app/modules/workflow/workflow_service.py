from __future__ import annotations

from typing import Any

from ...modules.opportunities.opportunity_service import ensure_from_rfp, set_stage as set_opportunity_stage
from ...repositories.rfp.rfps_repo import get_rfp_by_id
from ...repositories.rfp.opportunity_state_repo import ensure_state_exists, patch_state
from ...repositories.rfp.rfps_repo import list_rfp_proposal_summaries
from ...repositories.workflows.tasks_repo import seed_missing_tasks_for_stage

from .stage_machine import compute_stage


def sync_for_rfp(
    *,
    rfp_id: str,
    actor_user_sub: str | None = None,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """
    Single entrypoint to sync workflow state for an RFP/Opportunity:
    - compute canonical stage
    - ensure Opportunity profile row exists + update stage
    - ensure OpportunityState exists + update embedded stage (best-effort)
    - seed missing tasks for this stage

    Returns a small summary object used by callers for diagnostics.
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")

    rfp = get_rfp_by_id(rid) or {}
    proposals = list_rfp_proposal_summaries(rid) or []
    stage = compute_stage(rfp=rfp if isinstance(rfp, dict) else {}, proposals_for_rfp=proposals)

    # 1) Ensure Opportunity profile exists and set stage (authoritative moving forward)
    try:
        ensure_from_rfp(rfp_id=rid, created_by_user_sub=actor_user_sub, initial_stage=stage)
        set_opportunity_stage(opportunity_id=rid, stage=stage, updated_by_user_sub=actor_user_sub)
    except Exception:
        # Best-effort; keep callers resilient.
        pass

    # 2) Ensure OpportunityState exists and patch embedded stage (legacy agent state)
    try:
        ensure_state_exists(rfp_id=rid, created_by_user_sub=actor_user_sub)
        patch_state(
            rfp_id=rid,
            patch={"stage": stage},
            updated_by_user_sub=actor_user_sub,
            create_snapshot=False,
        )
    except Exception:
        pass

    # 3) Seed workflow tasks for stage
    created = []
    try:
        created = seed_missing_tasks_for_stage(rfp_id=rid, stage=stage, proposal_id=proposal_id)
    except Exception:
        created = []

    return {"ok": True, "rfpId": rid, "stage": stage, "seededTasks": len(created)}


