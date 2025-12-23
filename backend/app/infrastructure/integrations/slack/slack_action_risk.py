from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Risk = Literal["low", "medium", "high", "destructive"]


@dataclass(frozen=True)
class ActionRiskDecision:
    risk: Risk
    requires_confirmation: bool


def classify_action_risk(*, action: str, args: dict[str, Any] | None = None) -> ActionRiskDecision:
    """
    Central risk model for Slack-triggered actions.

    Policy target (per product direction): auto-do low-risk, confirm risky.
    """
    k = str(action or "").strip()

    # Purely personal preference/memory updates (non-destructive, reversible).
    if k == "update_user_profile":
        return ActionRiskDecision(risk="low", requires_confirmation=False)

    # Task and workflow changes affect shared work; confirm.
    if k in ("seed_tasks_for_rfp", "assign_task", "complete_task", "update_rfp_review", "assign_rfp_review"):
        return ActionRiskDecision(risk="medium", requires_confirmation=True)

    # Infra / data operations: always confirm.
    if k.startswith(("ecs_", "s3_", "cognito_", "sqs_")):
        # deletes are destructive
        if k in ("s3_delete_object",):
            return ActionRiskDecision(risk="destructive", requires_confirmation=True)
        return ActionRiskDecision(risk="high", requires_confirmation=True)

    # Self-modifying pipeline and GitHub actions: confirm.
    if k.startswith("self_modify_") or k.startswith("github_"):
        return ActionRiskDecision(risk="high", requires_confirmation=True)

    # Default: confirm unknown actions.
    return ActionRiskDecision(risk="medium", requires_confirmation=True)

