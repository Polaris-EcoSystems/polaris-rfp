from __future__ import annotations

from typing import Any

from .opportunity_repo import ensure_opportunity_exists_for_rfp, update_opportunity


def ensure_from_rfp(
    *,
    rfp_id: str,
    created_by_user_sub: str | None = None,
    initial_stage: str | None = None,
) -> dict[str, Any]:
    return ensure_opportunity_exists_for_rfp(
        rfp_id=rfp_id,
        created_by_user_sub=created_by_user_sub,
        initial_stage=initial_stage,
    )


def attach_active_proposal(
    *,
    opportunity_id: str,
    proposal_id: str,
    updated_by_user_sub: str | None = None,
) -> dict[str, Any] | None:
    return update_opportunity(
        opportunity_id,
        {"activeProposalId": str(proposal_id or "").strip() or None},
        updated_by_user_sub=updated_by_user_sub,
    )


def attach_contracting_case(
    *,
    opportunity_id: str,
    case_id: str,
    updated_by_user_sub: str | None = None,
) -> dict[str, Any] | None:
    return update_opportunity(
        opportunity_id,
        {"contractingCaseId": str(case_id or "").strip() or None},
        updated_by_user_sub=updated_by_user_sub,
    )


def set_stage(
    *,
    opportunity_id: str,
    stage: str,
    updated_by_user_sub: str | None = None,
) -> dict[str, Any] | None:
    return update_opportunity(
        opportunity_id,
        {"stage": str(stage or "").strip() or None},
        updated_by_user_sub=updated_by_user_sub,
    )


