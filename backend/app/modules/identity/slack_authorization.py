from __future__ import annotations

from typing import Any

from ...domain.agents.messaging.agent_message import UserIdentity
from .roles import is_admin, is_operator_or_admin, normalize_roles


def _action_family(kind: str) -> str:
    k = str(kind or "").strip()
    if k.startswith("self_modify_"):
        return "self_modify"
    if k.startswith("github_"):
        return "github"
    if k.startswith("ecs_") or k.startswith("s3_") or k.startswith("sqs_") or k.startswith("cognito_"):
        return "infra"
    return "app"


def authorize_slack_action_execution(
    *,
    kind: str,
    args: dict[str, Any],
    actor: UserIdentity,
    requested_by_slack_user_id: str | None,
    requested_by_user_sub: str | None,
) -> tuple[bool, str | None]:
    """
    Authorization for Slack-confirmed actions.

    Policy:
    - If action was requested by the same actor (Slack user or user_sub), allow.
    - Otherwise, require Operator/Admin for app actions.
    - For infra + self_modify families, require Admin.
    """
    k = str(kind or "").strip()
    actor_sub = str(actor.user_sub or "").strip() or None
    actor_slack = str(actor.slack_user_id or "").strip() or None
    if not actor_sub and not actor_slack:
        return False, "actor_not_resolved"

    # Self-service match
    if requested_by_slack_user_id and actor_slack and requested_by_slack_user_id == actor_slack:
        return True, None
    if requested_by_user_sub and actor_sub and requested_by_user_sub == actor_sub:
        return True, None

    roles = normalize_roles((actor.user_profile or {}).get("roles") if isinstance(actor.user_profile, dict) else None)
    fam = _action_family(k)

    if fam in ("infra", "self_modify"):
        if not is_admin(roles):
            return False, "admin_required"
        return True, None

    # Default: app actions can be executed by Operator/Admin when acting on behalf of others.
    if not is_operator_or_admin(roles):
        return False, "operator_required"

    return True, None


