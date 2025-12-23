from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ....observability.logging import get_logger
from ....settings import settings
from ...cognito_idp import admin_get_user
from .slack_web import get_user_info, slack_user_display_name
from ....repositories.users.user_profiles_repo import (
    get_user_profile,
    get_user_profile_by_slack_user_id,
    get_user_sub_by_email,
    upsert_user_email_index,
)

log = get_logger("slack_actor_context")


@dataclass(frozen=True)
class SlackActorContext:
    slack_user_id: str | None
    slack_team_id: str | None
    slack_enterprise_id: str | None
    email: str | None
    display_name: str | None
    user_sub: str | None
    user_profile: dict[str, Any] | None
    slack_user: dict[str, Any] | None


_CTX_CACHE_TTL_S = 120
_ctx_cache: dict[str, tuple[float, SlackActorContext]] = {}


def _cache_key(*, slack_user_id: str | None, team_id: str | None) -> str:
    return f"{str(team_id or '').strip()}::{str(slack_user_id or '').strip()}"


def resolve_actor_context(
    *,
    slack_user_id: str | None,
    slack_team_id: str | None = None,
    slack_enterprise_id: str | None = None,
    force_refresh: bool = False,
) -> SlackActorContext:
    """
    Resolve Slack actor identity into a stable platform user:
      Slack user -> Slack profile (email, display name) ->
      (1) UserProfile by slackUserId
      (2) else email index -> userSub
      (3) else Cognito admin_get_user(email) -> sub
    """
    uid = str(slack_user_id or "").strip() or None
    tid = str(slack_team_id or "").strip() or None
    eid = str(slack_enterprise_id or "").strip() or None

    if uid:
        ck = _cache_key(slack_user_id=uid, team_id=tid)
        now = time.time()
        if not force_refresh:
            cached = _ctx_cache.get(ck)
            if cached:
                ts, val = cached
                if (now - float(ts)) < float(_CTX_CACHE_TTL_S):
                    return val

    slack_user = get_user_info(user_id=uid or "", force_refresh=bool(force_refresh)) if uid else None
    display_name = slack_user_display_name(slack_user) if slack_user else None
    prof = (slack_user.get("profile") if isinstance(slack_user, dict) else {}) or {}
    email = str(prof.get("email") or "").strip().lower() or None

    # 1) Direct mapping: Slack user id -> profile (best case)
    user_profile = get_user_profile_by_slack_user_id(slack_user_id=uid or "") if uid else None
    user_sub = str((user_profile or {}).get("_id") or (user_profile or {}).get("userSub") or "").strip() or None

    # 2) Email index -> userSub
    if not user_profile and email:
        user_sub = get_user_sub_by_email(email=email)
        if user_sub:
            user_profile = get_user_profile(user_sub=user_sub)

    # 3) Cognito lookup by email -> sub
    if not user_profile and email:
        try:
            pool_id = str(settings.cognito_user_pool_id or "").strip()
            if not pool_id:
                raise ValueError("missing_cognito_user_pool_id")
            cu = admin_get_user(user_pool_id=pool_id, username=email)
            attrs = cu.get("UserAttributes") if isinstance(cu, dict) else None
            for a in (attrs if isinstance(attrs, list) else []):
                if isinstance(a, dict) and str(a.get("Name") or "").strip() == "sub":
                    user_sub = str(a.get("Value") or "").strip() or None
                    break
        except Exception:
            user_sub = None
        if user_sub:
            user_profile = get_user_profile(user_sub=user_sub)
            try:
                upsert_user_email_index(email=email, user_sub=user_sub)
            except Exception:
                pass

    ctx = SlackActorContext(
        slack_user_id=uid,
        slack_team_id=tid,
        slack_enterprise_id=eid,
        email=email,
        display_name=display_name,
        user_sub=user_sub,
        user_profile=user_profile if isinstance(user_profile, dict) else None,
        slack_user=slack_user if isinstance(slack_user, dict) else None,
    )
    if uid:
        _ctx_cache[_cache_key(slack_user_id=uid, team_id=tid)] = (time.time(), ctx)
    return ctx

