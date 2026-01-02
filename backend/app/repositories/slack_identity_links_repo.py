from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slack_identity_link_key(*, slack_user_id: str, slack_team_id: str | None = None) -> dict[str, str]:
    uid = str(slack_user_id or "").strip()
    if not uid:
        raise ValueError("slack_user_id is required")
    # Single-org default: team id is optional. When present, include to avoid collisions.
    tid = str(slack_team_id or "").strip() or None
    pk = f"SLACK_USER#{uid}" if not tid else f"SLACK_USER#{tid}#{uid}"
    return {"pk": pk, "sk": "IDENTITY_LINK"}


def get_user_sub_by_slack_user_id(
    *, slack_user_id: str, slack_team_id: str | None = None
) -> str | None:
    it = get_main_table().get_item(key=slack_identity_link_key(slack_user_id=slack_user_id, slack_team_id=slack_team_id))
    if not isinstance(it, dict):
        return None
    sub = str(it.get("userSub") or "").strip()
    return sub or None


def upsert_slack_identity_link(
    *,
    slack_user_id: str,
    user_sub: str,
    slack_team_id: str | None = None,
    slack_enterprise_id: str | None = None,
) -> dict[str, Any]:
    uid = str(slack_user_id or "").strip()
    sub = str(user_sub or "").strip()
    if not uid:
        raise ValueError("slack_user_id is required")
    if not sub:
        raise ValueError("user_sub is required")

    now = _now_iso()
    key = slack_identity_link_key(slack_user_id=uid, slack_team_id=slack_team_id)
    item: dict[str, Any] = {
        **key,
        "entityType": "SlackIdentityLink",
        "slackUserId": uid,
        "slackTeamId": str(slack_team_id or "").strip() or None,
        "slackEnterpriseId": str(slack_enterprise_id or "").strip() or None,
        "userSub": sub,
        "createdAt": now,
        "updatedAt": now,
    }

    # Preserve createdAt on update if it exists.
    existing = get_main_table().get_item(key=key) or {}
    if isinstance(existing, dict) and str(existing.get("createdAt") or "").strip():
        item["createdAt"] = existing.get("createdAt")

    item = {k: v for k, v in item.items() if v is not None}
    get_main_table().put_item(item=item)
    return {k: v for k, v in item.items() if k not in ("pk", "sk")}


def list_slack_identity_links(*, limit: int = 50, next_token: str | None = None) -> dict[str, Any]:
    """
    Debug/admin listing (best-effort).

    This is a scan-by-prefix in a single-table design; avoid using in hot paths.
    """
    # This repo intentionally avoids a table scan helper; leave listing as a non-goal for now.
    return {"data": [], "nextToken": None, "warning": "not_implemented"}


