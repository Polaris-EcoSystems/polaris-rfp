from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def user_profile_key(*, user_sub: str) -> dict[str, str]:
    sub = str(user_sub or "").strip()
    if not sub:
        raise ValueError("user_sub is required")
    return {"pk": f"USER#{sub}", "sk": "PROFILE"}


def normalize_user_profile_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    out["_id"] = str(item.get("userSub") or "").strip() or None
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    return out


def get_user_profile(*, user_sub: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=user_profile_key(user_sub=user_sub))
    return normalize_user_profile_for_api(it)


def get_user_profile_by_slack_user_id(*, slack_user_id: str) -> dict[str, Any] | None:
    """
    Lookup a user profile by Slack user id using GSI1.

    Note: this relies on `upsert_user_profile()` writing:
      gsi1pk = "SLACK_USER#{slackUserId}"
    """
    uid = str(slack_user_id or "").strip()
    if not uid:
        return None
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(f"SLACK_USER#{uid}"),
        scan_index_forward=False,
        limit=1,
        next_token=None,
    )
    items = pg.items or []
    it0 = items[0] if items else None
    return normalize_user_profile_for_api(it0) if isinstance(it0, dict) else None


def upsert_user_profile(*, user_sub: str, email: str | None, updates: dict[str, Any]) -> dict[str, Any]:
    """
    Upsert an app-level UserProfile. `user_sub` and `email` are authoritative from auth,
    not from client input.
    """
    sub = str(user_sub or "").strip()
    if not sub:
        raise ValueError("user_sub is required")

    existing_raw = get_main_table().get_item(key=user_profile_key(user_sub=sub)) or {}
    now = now_iso()
    created_at = str(existing_raw.get("createdAt") or "").strip() or now

    item: dict[str, Any] = {
        **user_profile_key(user_sub=sub),
        "entityType": "UserProfile",
        "userSub": sub,
        "email": str(email or "").strip().lower() or None,
        "createdAt": created_at,
        "updatedAt": now,
        # Defaults
        "fullName": None,
        "preferredName": None,
        "jobTitles": [],
        "certifications": [],
        "resumeAssets": [],
        "profileCompletedAt": None,
        "onboardingVersion": 1,
        "linkedTeamMemberId": None,
        # AI agent personalization (bounded; stored per user)
        "aiPreferences": {},
        "aiMemorySummary": None,
    }

    # Merge existing fields first, then apply updates.
    if isinstance(existing_raw, dict) and existing_raw:
        item.update(existing_raw)
        # enforce invariants
        item["pk"] = user_profile_key(user_sub=sub)["pk"]
        item["sk"] = "PROFILE"
        item["entityType"] = "UserProfile"
        item["userSub"] = sub
        item["createdAt"] = created_at
        item["updatedAt"] = now
        item["email"] = str(email or "").strip().lower() or item.get("email") or None

    item.update(updates or {})

    # Final invariants
    item["pk"] = user_profile_key(user_sub=sub)["pk"]
    item["sk"] = "PROFILE"
    item["entityType"] = "UserProfile"
    item["userSub"] = sub
    item["updatedAt"] = now
    item["email"] = str(email or "").strip().lower() or item.get("email") or None

    # Optional GSI1 mapping: Slack user id → user profile
    suid = str(item.get("slackUserId") or "").strip()
    if suid:
        item["gsi1pk"] = f"SLACK_USER#{suid}"
        item["gsi1sk"] = f"USER#{sub}"
    else:
        # User profiles don't otherwise use GSI1; keep index clean.
        item.pop("gsi1pk", None)
        item.pop("gsi1sk", None)

    get_main_table().put_item(item=item)
    return normalize_user_profile_for_api(item) or {}


def mark_profile_complete(*, user_sub: str, onboarding_version: int = 1) -> dict[str, Any]:
    sub = str(user_sub or "").strip()
    if not sub:
        raise ValueError("user_sub is required")
    now = now_iso()
    updated = get_main_table().update_item(
        key=user_profile_key(user_sub=sub),
        update_expression="SET profileCompletedAt = :c, onboardingVersion = :v, updatedAt = :u",
        expression_attribute_names=None,
        expression_attribute_values={
            ":c": now,
            ":v": int(onboarding_version or 1),
            ":u": now,
        },
        return_values="ALL_NEW",
    )
    return normalize_user_profile_for_api(updated) or {}


def new_resume_asset_id() -> str:
    return f"asset_{uuid.uuid4()}"

