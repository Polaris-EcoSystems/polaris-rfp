from __future__ import annotations

from typing import Any

from app.infrastructure.storage import content_repo


def _pick_first_job_title(job_titles: Any) -> str:
    titles = job_titles if isinstance(job_titles, list) else []
    for t in titles:
        s = str(t or "").strip()
        if s:
            return s[:200]
    return ""


def _merge_if_user_managed(
    *,
    existing: dict[str, Any] | None,
    updates: dict[str, Any],
    user_managed: dict[str, bool],
    field: str,
    value: Any,
) -> None:
    """
    Only overwrite a field if:
      - it doesn't exist, OR
      - we previously marked it as user-managed.
    """
    ex = existing or {}
    if field not in ex or user_managed.get(field) is True:
        updates[field] = value


def upsert_linked_team_member_from_user_profile(
    *,
    user_sub: str,
    user_email: str | None,
    user_profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Sync user profile -> Content Library TeamMember.

    Strategy:
    - Find existing member by `linkedTeamMemberId` if present, else search for member with `linkedUserSub`.
    - Update only a small set of user-managed fields and preserve admin-entered fields.
    - Mark which fields are user-managed in `userManagedFields` so future syncs don't clobber admin edits.
    """
    sub = str(user_sub or "").strip()
    if not sub:
        raise ValueError("user_sub is required")

    email = str(user_email or "").strip().lower() or None
    prof = dict(user_profile or {})

    linked_id = str(prof.get("linkedTeamMemberId") or "").strip() or None
    existing: dict[str, Any] | None = None
    if linked_id:
        existing = content_repo.get_team_member_by_id(linked_id)

    if not existing:
        try:
            # No index yet; small dataset so list+scan is fine.
            for m in content_repo.list_team_members(limit=500):
                if not isinstance(m, dict):
                    continue
                if str(m.get("linkedUserSub") or "").strip() == sub:
                    existing = m
                    break
        except Exception:
            existing = None

    # User-managed fields from profile
    full_name = str(prof.get("fullName") or "").strip()[:200] or None
    job_title = _pick_first_job_title(prof.get("jobTitles"))
    certs_raw = prof.get("certifications")
    certs: list[Any] = certs_raw if isinstance(certs_raw, list) else []
    certifications = [str(x or "").strip()[:200] for x in certs if str(x or "").strip()][:50]

    resume_raw = prof.get("resumeAssets")
    resume_assets: list[Any] = resume_raw if isinstance(resume_raw, list) else []

    user_managed_fields = (
        dict(existing.get("userManagedFields") or {}) if isinstance(existing, dict) else {}
    )
    # Defaults: first sync marks these as user-managed
    for f in ("name", "email", "title", "position", "certifications", "resumeAssets"):
        if f not in user_managed_fields:
            user_managed_fields[f] = True

    updates: dict[str, Any] = {
        "linkedUserSub": sub,
        "linkedUserEmail": email,
        "userManagedFields": user_managed_fields,
    }

    if full_name:
        _merge_if_user_managed(
            existing=existing,
            updates=updates,
            user_managed=user_managed_fields,
            field="name",
            value=full_name,
        )
        # Keep nameWithCredentials in sync unless admin set it.
        _merge_if_user_managed(
            existing=existing,
            updates=updates,
            user_managed=user_managed_fields,
            field="nameWithCredentials",
            value=full_name,
        )

    if email:
        _merge_if_user_managed(
            existing=existing,
            updates=updates,
            user_managed=user_managed_fields,
            field="email",
            value=email,
        )

    if job_title:
        _merge_if_user_managed(
            existing=existing,
            updates=updates,
            user_managed=user_managed_fields,
            field="title",
            value=job_title,
        )
        _merge_if_user_managed(
            existing=existing,
            updates=updates,
            user_managed=user_managed_fields,
            field="position",
            value=job_title,
        )

    if certifications:
        _merge_if_user_managed(
            existing=existing,
            updates=updates,
            user_managed=user_managed_fields,
            field="certifications",
            value=certifications,
        )

    if isinstance(resume_assets, list):
        _merge_if_user_managed(
            existing=existing,
            updates=updates,
            user_managed=user_managed_fields,
            field="resumeAssets",
            value=resume_assets[:25],
        )

    # Persist
    if existing and isinstance(existing, dict) and str(existing.get("memberId") or "").strip():
        member_id = str(existing.get("memberId") or "").strip()
        # Use repo-level upsert (not API validation), so extra fields persist.
        updated = content_repo.upsert_team_member({**existing, **updates, "memberId": member_id})
        return updated

    created = content_repo.upsert_team_member(
        {
            "memberId": None,
            "isActive": True,
            **updates,
        }
    )
    return created

