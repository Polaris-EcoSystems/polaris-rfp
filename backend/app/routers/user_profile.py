from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.s3_assets import get_assets_bucket_name, presign_get_object, presign_put_object, to_s3_uri
from ..services.user_profile_team_sync import upsert_linked_team_member_from_user_profile
from ..repositories.users.user_profiles_repo import (
    get_user_profile,
    mark_profile_complete,
    new_resume_asset_id,
    upsert_user_profile,
)


router = APIRouter(tags=["user-profile"])


def _clean_string(v: Any, *, max_len: int = 5000) -> str:
    s = str(v or "").strip()
    return s[:max_len] if s else ""


def _clean_string_list(v: Any, *, max_items: int = 100, max_len: int = 200) -> list[str]:
    arr = v if isinstance(v, list) else []
    out: list[str] = []
    for x in arr:
        s = _clean_string(x, max_len=max_len)
        if not s:
            continue
        if s not in out:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _current_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    sub = str(getattr(user, "sub", "") or "").strip()
    if not sub:
        raise HTTPException(status_code=401, detail="Unauthorized")
    email = str(getattr(user, "email", "") or "").strip().lower() or None
    username = str(getattr(user, "username", "") or "").strip() or None
    return sub, email, username


def _is_complete(profile: dict[str, Any] | None) -> bool:
    if not isinstance(profile, dict):
        return False
    return bool(str(profile.get("profileCompletedAt") or "").strip())


class PutUserProfileRequest(BaseModel):
    fullName: str | None = None
    jobTitles: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    resumeAssets: list[dict[str, Any]] = Field(default_factory=list)
    slackUserId: str | None = None
    preferredName: str | None = None
    aiPreferences: dict[str, Any] = Field(default_factory=dict)
    aiMemorySummary: str | None = None


@router.get("/user-profile")
@router.get("/user-profile/")
def get_profile(request: Request):
    sub, email, username = _current_user(request)
    profile = get_user_profile(user_sub=sub) or {}
    # Ensure we always return at least a skeleton profile.
    if not profile:
        profile = upsert_user_profile(user_sub=sub, email=email, updates={})
    return {
        "ok": True,
        "user": {"sub": sub, "email": email, "username": username},
        "profile": profile,
        "isComplete": _is_complete(profile),
    }


@router.put("/user-profile")
@router.put("/user-profile/")
def put_profile(request: Request, body: PutUserProfileRequest):
    sub, email, username = _current_user(request)

    updates: dict[str, Any] = {}
    if body.fullName is not None:
        nm = _clean_string(body.fullName, max_len=200) or None
        updates["fullName"] = nm
    if body.preferredName is not None:
        pn = _clean_string(body.preferredName, max_len=120) or None
        updates["preferredName"] = pn
    if body.jobTitles is not None:
        updates["jobTitles"] = _clean_string_list(body.jobTitles, max_items=20, max_len=200)
    if body.certifications is not None:
        updates["certifications"] = _clean_string_list(body.certifications, max_items=50, max_len=200)

    # Resume assets are pointers only; enforce minimal shape and size limits.
    if body.resumeAssets is not None:
        out_assets: list[dict[str, Any]] = []
        arr = body.resumeAssets if isinstance(body.resumeAssets, list) else []
        for a in arr[:25]:
            if not isinstance(a, dict):
                continue
            asset_id = _clean_string(a.get("assetId"), max_len=80) or None
            file_name = _clean_string(a.get("fileName"), max_len=255) or None
            content_type = _clean_string(a.get("contentType"), max_len=120) or None
            s3_key = _clean_string(a.get("s3Key"), max_len=1024) or None
            s3_uri = _clean_string(a.get("s3Uri"), max_len=2048) or None
            uploaded_at = _clean_string(a.get("uploadedAt"), max_len=80) or None
            if not asset_id or not s3_key:
                continue
            out_assets.append(
                {
                    "assetId": asset_id,
                    "fileName": file_name,
                    "contentType": content_type,
                    "s3Key": s3_key,
                    "s3Uri": s3_uri,
                    "uploadedAt": uploaded_at,
                }
            )
        updates["resumeAssets"] = out_assets

    if body.slackUserId is not None:
        suid = _clean_string(body.slackUserId, max_len=80) or None
        # Slack user IDs are usually like U123..., W123...
        if suid and not re.fullmatch(r"[UW][A-Z0-9]{6,}", suid):
            suid = None
        updates["slackUserId"] = suid

    # AI prefs/memory (bounded + safe)
    if body.aiPreferences is not None:
        prefs = body.aiPreferences if isinstance(body.aiPreferences, dict) else {}
        # Keep small and JSON-serializable-ish; store only shallow keys.
        slim: dict[str, Any] = {}
        for k, v in list(prefs.items())[:50]:
            kk = _clean_string(k, max_len=60)
            if not kk:
                continue
            # Bound individual values; allow primitives + small strings.
            if isinstance(v, (int, float, bool)) or v is None:
                slim[kk] = v
            elif isinstance(v, str):
                slim[kk] = _clean_string(v, max_len=500)
            else:
                # Drop complex nested objects for now to keep the prompt injection safe.
                slim[kk] = _clean_string(str(v), max_len=500)
        updates["aiPreferences"] = slim
    if body.aiMemorySummary is not None:
        ms = _clean_string(body.aiMemorySummary, max_len=4000) or None
        updates["aiMemorySummary"] = ms

    saved = upsert_user_profile(user_sub=sub, email=email, updates=updates)

    # Best-effort: if already completed, sync linked Team Member on key field changes.
    try:
        if _is_complete(saved):
            member = upsert_linked_team_member_from_user_profile(
                user_sub=sub,
                user_email=email,
                user_profile=saved,
            )
            # Store link on profile (best-effort; does not block response).
            mid = str(member.get("memberId") or "").strip() if isinstance(member, dict) else ""
            if mid and str(saved.get("linkedTeamMemberId") or "").strip() != mid:
                saved = upsert_user_profile(user_sub=sub, email=email, updates={"linkedTeamMemberId": mid})
    except Exception:
        pass

    return {
        "ok": True,
        "user": {"sub": sub, "email": email, "username": username},
        "profile": saved,
        "isComplete": _is_complete(saved),
    }


class ResumePresignRequest(BaseModel):
    fileName: str = Field(..., min_length=1)
    contentType: str = Field(..., min_length=1)


@router.post("/user-profile/resume/presign")
@router.post("/user-profile/resume/presign/")
def presign_resume_upload(request: Request, body: ResumePresignRequest):
    sub, email, _username = _current_user(request)

    file_name = _clean_string(body.fileName, max_len=255)
    content_type = _clean_string(body.contentType, max_len=120).lower()
    if not file_name:
        raise HTTPException(status_code=400, detail="fileName is required")
    if not content_type:
        raise HTTPException(status_code=400, detail="contentType is required")

    allowed_types = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported resume file type")

    # Key namespace: org-shared resumes under team/resumes/{sub}/...
    ext = ""
    m = re.search(r"\.([a-zA-Z0-9]{1,10})$", file_name)
    if m:
        ext = f".{m.group(1).lower()}"
    asset_id = new_resume_asset_id()
    key = f"team/resumes/{sub}/{asset_id}{ext}"

    put = presign_put_object(key=key, content_type=content_type, expires_in=900)
    get = presign_get_object(key=key, expires_in=3600)

    return {
        "ok": True,
        "asset": {
            "assetId": asset_id,
            "fileName": file_name,
            "contentType": content_type,
            "s3Key": key,
            "s3Uri": to_s3_uri(bucket=get_assets_bucket_name(), key=key),
        },
        "putUrl": put["url"],
        "getUrl": get["url"],
        "expiresInSeconds": {"put": 900, "get": 3600},
        "maxSizeBytes": 25 * 1024 * 1024,
    }


@router.post("/user-profile/complete")
@router.post("/user-profile/complete/")
def complete_profile(request: Request, body: dict = Body(default_factory=dict)):
    sub, email, username = _current_user(request)
    # Ensure profile exists
    get_user_profile(user_sub=sub) or upsert_user_profile(user_sub=sub, email=email, updates={})
    saved = mark_profile_complete(user_sub=sub, onboarding_version=1)

    # Sync to Team Member and persist link
    try:
        member = upsert_linked_team_member_from_user_profile(user_sub=sub, user_email=email, user_profile=saved)
        mid = str(member.get("memberId") or "").strip() if isinstance(member, dict) else ""
        if mid and str(saved.get("linkedTeamMemberId") or "").strip() != mid:
            saved = upsert_user_profile(user_sub=sub, email=email, updates={"linkedTeamMemberId": mid})
    except Exception:
        pass

    return {
        "ok": True,
        "user": {"sub": sub, "email": email, "username": username},
        "profile": saved,
        "isComplete": _is_complete(saved),
    }

