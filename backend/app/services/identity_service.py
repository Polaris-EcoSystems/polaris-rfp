"""
Unified Identity Service - Single source for user identity resolution.

This service consolidates identity resolution logic from:
- slack_actor_context.py (Slack → Cognito)
- user_profiles_repo.py (profile management)
- cognito_idp.py (Cognito operations)

Provides a single, consistent interface for resolving user identity across platforms.
"""

from __future__ import annotations

import time
from typing import Any

from ..observability.logging import get_logger
from ..settings import settings
from . import cognito_idp
from .slack_web import get_user_info, slack_user_display_name
from ..repositories.users.user_profiles_repo import (
    get_user_profile,
    get_user_profile_by_slack_user_id,
    get_user_sub_by_email,
    upsert_user_email_index,
)
from .agent_message import UserIdentity

log = get_logger("identity_service")


# Cache for resolved identities (same as slack_actor_context)
_CTX_CACHE_TTL_S = 120
_ctx_cache: dict[str, tuple[float, UserIdentity]] = {}


def _cache_key(*, slack_user_id: str | None, team_id: str | None, email: str | None, user_sub: str | None) -> str:
    """Generate cache key from available identifiers."""
    if slack_user_id:
        return f"slack::{str(team_id or '').strip()}::{str(slack_user_id).strip()}"
    if email:
        return f"email::{str(email).strip().lower()}"
    if user_sub:
        return f"sub::{str(user_sub).strip()}"
    return "unknown"


def resolve_user_identity(
    *,
    slack_user_id: str | None = None,
    slack_team_id: str | None = None,
    slack_enterprise_id: str | None = None,
    email: str | None = None,
    user_sub: str | None = None,
    force_refresh: bool = False,
) -> UserIdentity:
    """
    Resolve user identity from any available identifier.
    
    This is the unified entry point for identity resolution. It:
    1. Checks cache if not forcing refresh
    2. Resolves from Slack user ID (if provided)
    3. Resolves from email (if provided)
    4. Resolves from user_sub (if provided)
    5. Returns a UserIdentity object with all available information
    
    Args:
        slack_user_id: Slack user ID (starts with 'U')
        slack_team_id: Slack team/workspace ID
        slack_enterprise_id: Slack enterprise ID (if applicable)
        email: User email address
        user_sub: Cognito user sub (primary identifier)
        force_refresh: If True, bypass cache and refresh all data
    
    Returns:
        UserIdentity object with all resolved information
    """
    # Check cache first
    if not force_refresh:
        cache_key = _cache_key(
            slack_user_id=slack_user_id,
            team_id=slack_team_id,
            email=email,
            user_sub=user_sub,
        )
        if cache_key != "unknown":
            cached = _ctx_cache.get(cache_key)
            if cached:
                ts, val = cached
                if (time.time() - float(ts)) < float(_CTX_CACHE_TTL_S):
                    return val
    
    # Start with provided information
    resolved_user_sub = user_sub
    resolved_email = email
    resolved_display_name: str | None = None
    resolved_user_profile: dict[str, Any] | None = None
    resolved_slack_user: dict[str, Any] | None = None
    
    # Resolution strategy 1: Start from Slack user ID
    if slack_user_id:
        resolved_slack_user = get_user_info(user_id=slack_user_id, force_refresh=bool(force_refresh))
        resolved_display_name = slack_user_display_name(resolved_slack_user) if resolved_slack_user else None
        
        if resolved_slack_user:
            prof = (resolved_slack_user.get("profile") if isinstance(resolved_slack_user, dict) else {}) or {}
            if not resolved_email:
                resolved_email = str(prof.get("email") or "").strip().lower() or None
        
        # Try to get user profile by Slack user ID
        if not resolved_user_profile:
            resolved_user_profile = get_user_profile_by_slack_user_id(slack_user_id=slack_user_id)
            if resolved_user_profile:
                resolved_user_sub = str(
                    (resolved_user_profile or {}).get("_id") or (resolved_user_profile or {}).get("userSub") or ""
                ).strip() or None
    
    # Resolution strategy 2: Resolve from email
    if not resolved_user_sub and resolved_email:
        # Try email index
        resolved_user_sub = get_user_sub_by_email(email=resolved_email)
        if resolved_user_sub:
            resolved_user_profile = get_user_profile(user_sub=resolved_user_sub)
        
        # If still no user_sub, try Cognito
        if not resolved_user_sub:
            try:
                pool_id = str(settings.cognito_user_pool_id or "").strip()
                if pool_id:
                    cu = cognito_idp.admin_get_user(user_pool_id=pool_id, username=resolved_email)
                    attrs = cu.get("UserAttributes") if isinstance(cu, dict) else None
                    for a in (attrs if isinstance(attrs, list) else []):
                        if isinstance(a, dict) and str(a.get("Name") or "").strip() == "sub":
                            resolved_user_sub = str(a.get("Value") or "").strip() or None
                            break
            except Exception as e:
                log.debug("cognito_lookup_failed", email=resolved_email, error=str(e))
            
            if resolved_user_sub:
                resolved_user_profile = get_user_profile(user_sub=resolved_user_sub)
                # Update email index for future lookups
                try:
                    upsert_user_email_index(email=resolved_email, user_sub=resolved_user_sub)
                except Exception:
                    pass
    
    # Resolution strategy 3: Resolve from user_sub
    if resolved_user_sub and not resolved_user_profile:
        resolved_user_profile = get_user_profile(user_sub=resolved_user_sub)
    
    # Build UserIdentity object
    identity = UserIdentity(
        user_sub=resolved_user_sub,
        slack_user_id=slack_user_id,
        slack_team_id=slack_team_id,
        slack_enterprise_id=slack_enterprise_id,
        email=resolved_email,
        display_name=resolved_display_name,
        user_profile=resolved_user_profile if isinstance(resolved_user_profile, dict) else None,
        slack_user=resolved_slack_user if isinstance(resolved_slack_user, dict) else None,
    )
    
    # Cache the result
    cache_key = _cache_key(
        slack_user_id=slack_user_id,
        team_id=slack_team_id,
        email=resolved_email,
        user_sub=resolved_user_sub,
    )
    if cache_key != "unknown":
        _ctx_cache[cache_key] = (time.time(), identity)
    
    return identity


def resolve_from_slack(
    *,
    slack_user_id: str | None,
    slack_team_id: str | None = None,
    slack_enterprise_id: str | None = None,
    force_refresh: bool = False,
) -> UserIdentity:
    """
    Convenience method to resolve identity from Slack user ID.
    
    This is the most common use case - resolving a Slack user to platform identity.
    
    Returns an empty UserIdentity if slack_user_id is None.
    """
    if not slack_user_id:
        return UserIdentity()
    return resolve_user_identity(
        slack_user_id=slack_user_id,
        slack_team_id=slack_team_id,
        slack_enterprise_id=slack_enterprise_id,
        force_refresh=force_refresh,
    )


def resolve_from_email(*, email: str, force_refresh: bool = False) -> UserIdentity:
    """
    Convenience method to resolve identity from email.
    """
    return resolve_user_identity(email=email, force_refresh=force_refresh)


def resolve_from_user_sub(*, user_sub: str, force_refresh: bool = False) -> UserIdentity:
    """
    Convenience method to resolve identity from Cognito user sub.
    """
    return resolve_user_identity(user_sub=user_sub, force_refresh=force_refresh)


def clear_cache() -> None:
    """Clear the identity cache. Useful for testing or forced refresh."""
    global _ctx_cache
    _ctx_cache.clear()
    log.info("identity_cache_cleared")
