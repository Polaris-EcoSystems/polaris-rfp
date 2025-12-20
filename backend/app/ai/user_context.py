from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from .context import clip_text
from ..services.user_profiles_repo import get_user_profile


def load_user_profile_from_request(request: Request) -> dict[str, Any] | None:
    """
    Best-effort: load the current authenticated user's profile.

    Returns None if no authenticated user is present or profile is missing.
    """
    user = getattr(getattr(request, "state", None), "user", None)
    sub = str(getattr(user, "sub", "") or "").strip() if user else ""
    if not sub:
        return None
    try:
        prof = get_user_profile(user_sub=sub)
        return prof if isinstance(prof, dict) else None
    except Exception:
        return None


def user_context_block(*, user_profile: dict[str, Any] | None, fallback_name: str | None = None) -> str:
    """
    Convert a UserProfile into a compact, prompt-safe context block.
    """
    prof = user_profile if isinstance(user_profile, dict) else {}
    preferred = str(prof.get("preferredName") or "").strip()
    full = str(prof.get("fullName") or "").strip()
    nm = preferred or full or str(fallback_name or "").strip()

    prefs = prof.get("aiPreferences") if isinstance(prof.get("aiPreferences"), dict) else {}
    mem = str(prof.get("aiMemorySummary") or "").strip()

    lines: list[str] = []
    if nm:
        lines.append(f"- name: {nm}")
    if isinstance(prefs, dict) and prefs:
        try:
            lines.append(
                f"- preferences_json: {clip_text(json.dumps(prefs, ensure_ascii=False), max_chars=1200)}"
            )
        except Exception:
            pass
    if mem:
        lines.append(f"- memory_summary: {clip_text(mem, max_chars=1200)}")
    return "\n".join(lines).strip()

