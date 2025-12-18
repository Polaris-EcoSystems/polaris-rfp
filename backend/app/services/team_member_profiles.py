from __future__ import annotations

from typing import Any


def _normalize_type(t: Any) -> str:
    return str(t or "").strip().lower()


def _get_bio_profiles(member: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = member.get("bioProfiles")
    return profiles if isinstance(profiles, list) else []


def _pick_profile_for_project_type(member: dict[str, Any], project_type: Any) -> dict[str, Any] | None:
    pt = _normalize_type(project_type)
    profiles = _get_bio_profiles(member)
    if not pt or not profiles:
        return None

    for p in profiles:
        types = p.get("projectTypes") if isinstance(p, dict) else None
        types_list = types if isinstance(types, list) else []
        if pt in [_normalize_type(x) for x in types_list]:
            return p if isinstance(p, dict) else None

    return None


def pick_team_member_bio(member: dict[str, Any], project_type: Any) -> str:
    matched = _pick_profile_for_project_type(member, project_type)
    bio = (
        (str((matched or {}).get("bio") or "").strip() if matched else "")
        or str(member.get("biography") or "").strip()
        or ""
    )
    return bio


def pick_team_member_experience(member: dict[str, Any], project_type: Any) -> str:
    matched = _pick_profile_for_project_type(member, project_type)
    exp = (
        (str((matched or {}).get("experience") or "").strip() if matched else "")
        or str(member.get("experience") or "").strip()
        or ""
    )
    return exp
