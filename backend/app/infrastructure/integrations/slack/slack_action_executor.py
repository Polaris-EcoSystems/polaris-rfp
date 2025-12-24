from __future__ import annotations

from typing import Any

from ....observability.logging import get_logger
from ....infrastructure import identity_service as ids
from ....repositories.users.user_profiles_repo import (
    get_user_profile,
    get_user_profile_by_slack_user_id,
    upsert_user_profile,
)

log = get_logger("slack_action_executor")


def _merge_dicts(*, base: dict[str, Any] | None, patch: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = dict(base or {})
    for k, v in (patch or {}).items():
        out[str(k)] = v
    return out


def execute_action(*, action_id: str, kind: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    Minimal Slack action executor.

    We intentionally keep only the action(s) covered by tests / required for core identity-link flows
    while pruning the rest of the legacy Slack operator/agent surface.
    """
    _ = action_id
    k = str(kind or "").strip()
    a: dict[str, Any] = args if isinstance(args, dict) else {}

    if k != "update_user_profile":
        return {"ok": False, "action": k or "unknown", "error": "unsupported_action"}

    actor_slack_user_id = str(a.get("_actorSlackUserId") or a.get("_requestedBySlackUserId") or "").strip() or None
    if not actor_slack_user_id:
        return {"ok": False, "action": "update_user_profile", "error": "missing_actorSlackUserId"}

    # Resolve Slack -> Polaris identity (email/sub) even if no profile exists yet.
    ident = ids.resolve_from_slack(slack_user_id=actor_slack_user_id)
    user_sub = str(getattr(ident, "user_sub", "") or "").strip()
    email = str(getattr(ident, "email", "") or "").strip() or None

    if not user_sub:
        return {"ok": False, "action": "update_user_profile", "error": "unresolved_identity"}

    # Load profile if it exists (optional).
    existing = get_user_profile(user_sub=user_sub)
    if not existing:
        # Some legacy flows try Slack-user-id lookup; keep for compatibility.
        existing = get_user_profile_by_slack_user_id(slack_user_id=actor_slack_user_id)

    existing_ai_prefs = (
        (existing or {}).get("aiPreferences") if isinstance((existing or {}).get("aiPreferences"), dict) else {}
    )
    merge = a.get("aiPreferencesMerge")
    ai_merge = merge if isinstance(merge, dict) else {}
    new_ai_prefs = _merge_dicts(base=existing_ai_prefs, patch=ai_merge)

    updates: dict[str, Any] = {
        "slackUserId": actor_slack_user_id,
        "aiPreferences": new_ai_prefs,
    }

    # Allow a small set of fields if provided.
    if "preferredName" in a:
        updates["preferredName"] = a.get("preferredName")
    if "aiMemorySummary" in a:
        updates["aiMemorySummary"] = a.get("aiMemorySummary")

    upsert_user_profile(user_sub=user_sub, email=email, updates=updates)
    log.info("slack_action_update_user_profile_ok", user_sub=user_sub, slack_user_id=actor_slack_user_id)
    return {"ok": True, "action": "update_user_profile", "updated": True, "userSub": user_sub}


