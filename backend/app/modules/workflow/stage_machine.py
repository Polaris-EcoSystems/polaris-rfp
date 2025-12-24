from __future__ import annotations

from typing import Any, Iterable


PipelineStage = str


def compute_stage(*, rfp: dict[str, Any], proposals_for_rfp: Iterable[dict[str, Any]]) -> PipelineStage:
    """
    Canonical pipeline stage computation.

    This mirrors the current frontend logic (and existing backend behavior),
    but is now located in the workflow module so all callers share one definition.
    """
    try:
        if bool((rfp or {}).get("isDisqualified")):
            return "Disqualified"
        review = (rfp or {}).get("review") if isinstance((rfp or {}).get("review"), dict) else {}
        decision = str((review or {}).get("decision") or "").strip().lower()
        if decision == "no_bid":
            return "NoBid"
        if decision != "bid":
            return "BidDecision"

        ps = [p for p in (proposals_for_rfp or []) if isinstance(p, dict)]
        if not ps:
            return "ProposalDraft"

        p = sorted(ps, key=lambda x: str(x.get("updatedAt") or ""), reverse=True)[0]
        status = str(p.get("status") or "").strip().lower()
        if status == "won":
            return "Contracting"
        if status == "submitted":
            return "Submitted"
        if status == "ready_to_submit":
            return "ReadyToSubmit"
        if status in ("rework", "needs_changes"):
            return "Rework"
        if status == "in_review":
            return "ReviewRebuttal"
        return "ProposalDraft"
    except Exception:
        return "BidDecision"


