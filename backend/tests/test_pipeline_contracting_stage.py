from __future__ import annotations

from app.services.workflow_tasks_repo import compute_pipeline_stage


def test_pipeline_stage_is_contracting_when_latest_proposal_won():
    rfp = {"review": {"decision": "bid"}}
    proposals = [
        {"proposalId": "p1", "updatedAt": "2025-01-01T00:00:00Z", "status": "ready_to_submit"},
        {"proposalId": "p2", "updatedAt": "2025-02-01T00:00:00Z", "status": "won"},
    ]
    stage = compute_pipeline_stage(rfp=rfp, proposals_for_rfp=proposals)
    assert stage == "Contracting"

