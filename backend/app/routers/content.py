from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..infrastructure.storage import content_repo
from ..domain.pipeline.proposal_generation.company_capabilities import regenerate_company_capabilities
from ..infrastructure.storage.s3_assets import (
    get_assets_bucket_name,
    get_cached_headshot_url,
    make_key,
    move_object,
    presign_get_object,
    presign_put_object,
    set_cached_headshot_url,
    to_s3_uri,
)

router = APIRouter(tags=["content"])


def _clean_string(v: Any, max_len: int = 5000) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    return s[:max_len]


def _clean_nullable_string(v: Any, max_len: int = 5000) -> str | None:
    s = _clean_string(v, max_len=max_len)
    return s or None


def _clean_string_array(v: Any, max_items: int = 100, max_len: int = 200) -> list[str]:
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


def _ensure_https_url_or_empty(v: Any) -> str:
    s = _clean_string(v, max_len=2048)
    if not s:
        return ""
    if not (s.startswith("http://") or s.startswith("https://")):
        return ""
    return s


def _ensure_bullet_text(v: Any) -> str:
    s = _clean_string(v, max_len=20000)
    if not s:
        return ""
    if s.startswith("•"):
        return s
    if s.startswith("-"):
        return "• " + re.sub(r"^-+\s*", "", s)
    if s.startswith("*"):
        return "• " + re.sub(r"^\*+\s*", "", s)
    return f"• {s}"


def _assert_version(existing: dict[str, Any] | None, expected_version: Any) -> str | None:
    if expected_version is None:
        return None
    try:
        exp = int(expected_version)
    except Exception:
        return "Invalid version"
    cur = int(existing.get("version") or 0) if existing else 0
    if exp != cur:
        return f"Version conflict (expected {exp}, current {cur})"
    return None


def _with_signed_headshot(member: dict[str, Any]) -> dict[str, Any]:
    key = str(member.get("headshotS3Key") or "").strip()
    if not key:
        return member

    cached = get_cached_headshot_url(key)
    if cached:
        member = dict(member)
        member["headshotUrl"] = cached
        member["headshotS3Uri"] = member.get("headshotS3Uri") or to_s3_uri(
            bucket=get_assets_bucket_name(), key=key
        )
        return member

    try:
        signed = presign_get_object(key=key, expires_in=3600)
        url = signed["url"]
        set_cached_headshot_url(key, url)
        member = dict(member)
        member["headshotUrl"] = url
        member["headshotS3Uri"] = member.get("headshotS3Uri") or to_s3_uri(
            bucket=signed["bucket"], key=key
        )
        return member
    except Exception:
        return member


def _normalize_member_headshot_storage(member: dict[str, Any]) -> dict[str, Any]:
    member_id = str(member.get("memberId") or "").strip()
    key = str(member.get("headshotS3Key") or "").strip()
    if not member_id or not key:
        return member
    if not key.startswith("team/unassigned/"):
        return member

    new_key = make_key(kind="headshot", file_name=key, member_id=member_id)
    try:
        move_object(source_key=key, dest_key=new_key)
        member = dict(member)
        member["headshotS3Key"] = new_key
        member["headshotS3Uri"] = to_s3_uri(bucket=get_assets_bucket_name(), key=new_key)
        return member
    except Exception:
        return member


# --- Companies ---


@router.get("/companies")
@router.get("/companies/")
def companies():
    return content_repo.list_companies(limit=200)


@router.get("/company")
@router.get("/company/")
def company(companyId: str | None = None):
    if companyId:
        c = content_repo.get_company_by_company_id(companyId)
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
        return c

    items = content_repo.list_companies(limit=1)
    return items[0] if items else None


@router.get("/companies/{companyId}")
@router.get("/companies/{companyId}/")
def company_by_id(companyId: str):
    c = content_repo.get_company_by_company_id(companyId)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    return c


@router.post("/companies", status_code=201)
@router.post("/companies/", status_code=201)
def create_company(body: dict):
    name = _clean_string((body or {}).get("name"), max_len=200)
    description = _clean_string((body or {}).get("description"), max_len=20000)
    if not name or not description:
        raise HTTPException(status_code=400, detail="name and description are required")

    doc = {
        "companyId": _clean_nullable_string((body or {}).get("companyId"), max_len=80),
        "name": name,
        "tagline": _clean_string((body or {}).get("tagline"), max_len=500),
        "description": description,
        "founded": _clean_nullable_string((body or {}).get("founded"), max_len=120),
        "location": _clean_string((body or {}).get("location"), max_len=500),
        "website": _ensure_https_url_or_empty((body or {}).get("website")),
        "email": _clean_string((body or {}).get("email"), max_len=200),
        "phone": _clean_string((body or {}).get("phone"), max_len=60),
        "coreCapabilities": _clean_string_array((body or {}).get("coreCapabilities"), max_items=50),
        "certifications": _clean_string_array((body or {}).get("certifications"), max_items=50),
        "industryFocus": _clean_string_array((body or {}).get("industryFocus"), max_items=50),
        "missionStatement": _clean_string((body or {}).get("missionStatement"), max_len=20000),
        "visionStatement": _clean_string((body or {}).get("visionStatement"), max_len=20000),
        "values": _clean_string_array((body or {}).get("values"), max_items=50),
        "statistics": (body or {}).get("statistics") if isinstance((body or {}).get("statistics"), dict) else None,
        "socialMedia": (body or {}).get("socialMedia") if isinstance((body or {}).get("socialMedia"), dict) else None,
        "coverLetter": _clean_string((body or {}).get("coverLetter"), max_len=50000),
        "firmQualificationsAndExperience": _clean_string(
            (body or {}).get("firmQualificationsAndExperience"), max_len=50000
        ),
        "sharedInfo": (body or {}).get("sharedInfo") if isinstance((body or {}).get("sharedInfo"), dict) else None,
        "isActive": True,
        "version": 1,
    }

    return content_repo.upsert_company(doc)


@router.put("/companies/{companyId}")
@router.put("/companies/{companyId}/")
def update_company(companyId: str, body: dict):
    existing = content_repo.get_company_by_company_id(companyId)
    if not existing:
        raise HTTPException(status_code=404, detail="Company not found")

    conflict = _assert_version(existing, (body or {}).get("version"))
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)

    next_version = int(existing.get("version") or 0) + 1
    updates = dict(body or {})
    updates["companyId"] = companyId
    updates["version"] = next_version

    # normalize common fields
    if "name" in updates:
        updates["name"] = _clean_string(updates.get("name"), max_len=200)
    if "tagline" in updates:
        updates["tagline"] = _clean_string(updates.get("tagline"), max_len=500)
    if "description" in updates:
        updates["description"] = _clean_string(updates.get("description"), max_len=20000)
    if "website" in updates:
        updates["website"] = _ensure_https_url_or_empty(updates.get("website"))
    if "email" in updates:
        updates["email"] = _clean_string(updates.get("email"), max_len=200)
    if "phone" in updates:
        updates["phone"] = _clean_string(updates.get("phone"), max_len=60)
    if "coreCapabilities" in updates:
        updates["coreCapabilities"] = _clean_string_array(updates.get("coreCapabilities"))
    if "certifications" in updates:
        updates["certifications"] = _clean_string_array(updates.get("certifications"))
    if "industryFocus" in updates:
        updates["industryFocus"] = _clean_string_array(updates.get("industryFocus"))
    if "values" in updates:
        updates["values"] = _clean_string_array(updates.get("values"))

    updated = content_repo.upsert_company({**existing, **updates})
    return {"company": updated, "affectedCompanies": [updated]}


@router.post("/companies/{companyId}/capabilities/regenerate")
@router.post("/companies/{companyId}/capabilities/regenerate/")
def regenerate_capabilities(companyId: str):
    c = content_repo.get_company_by_company_id(companyId)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    updated = regenerate_company_capabilities(companyId)
    if not updated:
        raise HTTPException(status_code=404, detail="Company not found")
    return updated


@router.put("/company")
@router.put("/company/")
def update_company_compat(body: dict):
    company_id = str((body or {}).get("companyId") or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail="companyId is required")

    existing = content_repo.get_company_by_company_id(company_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Company not found")

    conflict = _assert_version(existing, (body or {}).get("version"))
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)

    next_version = int(existing.get("version") or 0) + 1
    updated = content_repo.upsert_company({**existing, **dict(body or {}), "companyId": company_id, "version": next_version})
    return updated


@router.delete("/companies/{companyId}")
@router.delete("/companies/{companyId}/")
def delete_company(companyId: str):
    existing = content_repo.get_company_by_company_id(companyId)
    if not existing:
        raise HTTPException(status_code=404, detail="Company not found")

    content_repo.upsert_company({**existing, "isActive": False, "companyId": companyId})
    return {"success": True}


# --- Team ---


@router.get("/team")
@router.get("/team/")
def team():
    members = content_repo.list_team_members(limit=500)
    active = [m for m in members if m.get("isActive", True) is True]
    return [_with_signed_headshot(m) for m in active]


@router.get("/team/{memberId}")
@router.get("/team/{memberId}/")
def team_member(memberId: str):
    m = content_repo.get_team_member_by_id(memberId)
    if not m:
        raise HTTPException(status_code=404, detail="Team member not found")
    return _with_signed_headshot(m)


@router.post("/team/headshot/presign")
@router.post("/team/headshot/presign/")
def presign_team_headshot(body: dict):
    file_name = str((body or {}).get("fileName") or "").strip()
    content_type = str((body or {}).get("contentType") or "").strip().lower()
    member_id = (body or {}).get("memberId")

    if not file_name:
        raise HTTPException(status_code=400, detail="fileName is required")
    if not content_type:
        raise HTTPException(status_code=400, detail="contentType is required")
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are allowed")

    allowed_ext = {".jpg", ".jpeg", ".png", ".webp"}
    m = re.search(r"(\.[a-z0-9]{1,10})$", file_name.lower())
    ext = m.group(1) if m else ""
    if ext and ext not in allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(allowed_ext))}",
        )

    key = make_key(kind="headshot", file_name=file_name, member_id=str(member_id) if member_id else None)

    put = presign_put_object(key=key, content_type=content_type, expires_in=900)
    get = presign_get_object(key=key, expires_in=3600)

    return {
        "ok": True,
        "bucket": put["bucket"],
        "key": key,
        "s3Uri": to_s3_uri(bucket=put["bucket"], key=key),
        "putUrl": put["url"],
        "getUrl": get["url"],
        "expiresInSeconds": {"put": 900, "get": 3600},
    }


@router.post("/team", status_code=201)
@router.post("/team/", status_code=201)
def create_team_member(body: dict):
    doc = {
        "memberId": _clean_nullable_string((body or {}).get("memberId"), max_len=80),
        "nameWithCredentials": _clean_string((body or {}).get("nameWithCredentials"), max_len=200),
        "name": _clean_string((body or {}).get("name"), max_len=200),
        "position": _clean_string((body or {}).get("position"), max_len=200),
        "title": _clean_string((body or {}).get("title"), max_len=200),
        "email": _clean_string((body or {}).get("email"), max_len=200),
        "companyId": _clean_nullable_string((body or {}).get("companyId"), max_len=80),
        "biography": _ensure_bullet_text((body or {}).get("biography")),
        "experienceYears": (body or {}).get("experienceYears"),
        "education": _clean_string_array((body or {}).get("education"), max_items=50),
        "certifications": _clean_string_array((body or {}).get("certifications"), max_items=50),
        "bioProfiles": (body or {}).get("bioProfiles") if isinstance((body or {}).get("bioProfiles"), list) else [],
        "headshotUrl": _ensure_https_url_or_empty((body or {}).get("headshotUrl")),
        "headshotS3Key": _clean_nullable_string((body or {}).get("headshotS3Key"), max_len=1024),
        "headshotS3Uri": _clean_nullable_string((body or {}).get("headshotS3Uri"), max_len=2048),
        "isActive": True,
        "version": 1,
    }

    created = content_repo.upsert_team_member(doc)
    normalized = _normalize_member_headshot_storage(created)
    final = created
    if normalized.get("headshotS3Key") != created.get("headshotS3Key"):
        final = content_repo.upsert_team_member({**normalized, "memberId": created["memberId"], "version": 1})
    return _with_signed_headshot(final)


@router.put("/team/{memberId}")
@router.put("/team/{memberId}/")
def update_team_member(memberId: str, body: dict):
    existing = content_repo.get_team_member_by_id(memberId)
    if not existing:
        raise HTTPException(status_code=404, detail="Team member not found")

    conflict = _assert_version(existing, (body or {}).get("version"))
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)

    next_version = int(existing.get("version") or 0) + 1
    updates = dict(body or {})
    updates["memberId"] = memberId
    updates["version"] = next_version

    # normalize key fields
    if "nameWithCredentials" in updates:
        updates["nameWithCredentials"] = _clean_string(updates.get("nameWithCredentials"), max_len=200)
    if "name" in updates:
        updates["name"] = _clean_string(updates.get("name"), max_len=200)
    if "position" in updates:
        updates["position"] = _clean_string(updates.get("position"), max_len=200)
    if "title" in updates:
        updates["title"] = _clean_string(updates.get("title"), max_len=200)
    if "email" in updates:
        updates["email"] = _clean_string(updates.get("email"), max_len=200)
    if "companyId" in updates:
        updates["companyId"] = _clean_nullable_string(updates.get("companyId"), max_len=80)
    if "biography" in updates:
        updates["biography"] = _ensure_bullet_text(updates.get("biography"))
    if "education" in updates:
        updates["education"] = _clean_string_array(updates.get("education"), max_items=50)
    if "certifications" in updates:
        updates["certifications"] = _clean_string_array(updates.get("certifications"), max_items=50)
    if "headshotUrl" in updates:
        updates["headshotUrl"] = _ensure_https_url_or_empty(updates.get("headshotUrl"))
    if "headshotS3Key" in updates:
        updates["headshotS3Key"] = _clean_nullable_string(updates.get("headshotS3Key"), max_len=1024)
    if "headshotS3Uri" in updates:
        updates["headshotS3Uri"] = _clean_nullable_string(updates.get("headshotS3Uri"), max_len=2048)

    updated = content_repo.upsert_team_member({**existing, **updates})
    normalized = _normalize_member_headshot_storage(updated)
    final = updated
    if normalized.get("headshotS3Key") != updated.get("headshotS3Key"):
        final = content_repo.upsert_team_member({**normalized, "memberId": memberId, "version": next_version})
    return _with_signed_headshot(final)


@router.delete("/team/{memberId}")
@router.delete("/team/{memberId}/")
def delete_team_member(memberId: str):
    existing = content_repo.get_team_member_by_id(memberId)
    if not existing:
        raise HTTPException(status_code=404, detail="Team member not found")
    content_repo.upsert_team_member({**existing, "isActive": False, "memberId": memberId})
    return {"success": True}


# --- Projects ---


@router.get("/projects")
@router.get("/projects/")
def projects(
    project_type: str | None = None,
    industry: str | None = None,
    companyId: str | None = None,
    count: int = 20,
):
    items = content_repo.list_past_projects(limit=500)
    filtered = [p for p in items if p.get("isActive", True) is True]
    filtered = [p for p in filtered if p.get("isPublic", True) is True]
    if companyId:
        filtered = [p for p in filtered if str(p.get("companyId") or "") == str(companyId)]
    if project_type:
        filtered = [p for p in filtered if str(p.get("projectType")) == str(project_type)]
    if industry:
        filtered = [p for p in filtered if str(p.get("industry")) == str(industry)]
    return filtered[: max(1, int(count or 20))]


@router.get("/projects/{id}")
@router.get("/projects/{id}/")
def project_by_id(id: str):
    p = content_repo.get_past_project_by_id(id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/projects", status_code=201)
@router.post("/projects/", status_code=201)
def create_project(body: dict, background_tasks: BackgroundTasks):
    required = ["title", "clientName", "description", "industry", "projectType", "duration"]
    for f in required:
        if not _clean_string((body or {}).get(f), max_len=20000):
            raise HTTPException(status_code=400, detail="Missing required fields")

    doc = dict(body or {})
    doc.update(
        {
            "companyId": _clean_nullable_string((body or {}).get("companyId"), max_len=80),
            "title": _clean_string((body or {}).get("title"), max_len=200),
            "clientName": _clean_string((body or {}).get("clientName"), max_len=200),
            "description": _clean_string((body or {}).get("description"), max_len=20000),
            "industry": _clean_string((body or {}).get("industry"), max_len=200),
            "projectType": _clean_string((body or {}).get("projectType"), max_len=120),
            "duration": _clean_string((body or {}).get("duration"), max_len=120),
            "keyOutcomes": _clean_string_array((body or {}).get("keyOutcomes"), max_items=50, max_len=300),
            "technologies": _clean_string_array((body or {}).get("technologies"), max_items=50, max_len=120),
            "challenges": _clean_string_array((body or {}).get("challenges"), max_items=50, max_len=300),
            "solutions": _clean_string_array((body or {}).get("solutions"), max_items=50, max_len=300),
            "isActive": True,
            "isPublic": (body or {}).get("isPublic") is not False,
            "version": 1,
        }
    )
    created = content_repo.upsert_past_project(doc)
    cid = str(created.get("companyId") or "").strip()
    if cid:
        background_tasks.add_task(regenerate_company_capabilities, cid)
    return created


@router.put("/projects/{id}")
@router.put("/projects/{id}/")
def update_project(id: str, body: dict, background_tasks: BackgroundTasks):
    existing = content_repo.get_past_project_by_id(id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    conflict = _assert_version(existing, (body or {}).get("version"))
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)

    next_version = int(existing.get("version") or 0) + 1
    updates = dict(body or {})
    updates["projectId"] = id
    updates["version"] = next_version

    for f, ml in ("title", 200), ("clientName", 200), ("description", 20000), ("industry", 200), ("projectType", 120), ("duration", 120):
        if f in updates:
            updates[f] = _clean_string(updates.get(f), max_len=ml)

    if "companyId" in updates:
        updates["companyId"] = _clean_nullable_string(updates.get("companyId"), max_len=80)

    if "keyOutcomes" in updates:
        updates["keyOutcomes"] = _clean_string_array(updates.get("keyOutcomes"), max_items=50, max_len=300)
    if "technologies" in updates:
        updates["technologies"] = _clean_string_array(updates.get("technologies"), max_items=50, max_len=120)
    if "challenges" in updates:
        updates["challenges"] = _clean_string_array(updates.get("challenges"), max_items=50, max_len=300)
    if "solutions" in updates:
        updates["solutions"] = _clean_string_array(updates.get("solutions"), max_items=50, max_len=300)

    updated = content_repo.upsert_past_project({**existing, **updates})
    prev_cid = str(existing.get("companyId") or "").strip()
    next_cid = str(updated.get("companyId") or "").strip()
    if prev_cid and prev_cid != next_cid:
        background_tasks.add_task(regenerate_company_capabilities, prev_cid)
    if next_cid:
        background_tasks.add_task(regenerate_company_capabilities, next_cid)
    return updated


@router.delete("/projects/{id}")
@router.delete("/projects/{id}/")
def delete_project(id: str, background_tasks: BackgroundTasks):
    existing = content_repo.get_past_project_by_id(id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    content_repo.upsert_past_project({**existing, "isActive": False, "projectId": id})
    cid = str(existing.get("companyId") or "").strip()
    if cid:
        background_tasks.add_task(regenerate_company_capabilities, cid)
    return {"success": True}


# --- References ---


@router.get("/references")
@router.get("/references/")
def references(project_type: str | None = None, companyId: str | None = None, count: int = 10):
    items = content_repo.list_project_references(limit=500)
    filtered = [r for r in items if r.get("isActive", True) is True]
    filtered = [r for r in filtered if r.get("isPublic", True) is True]
    if companyId:
        filtered = [r for r in filtered if str(r.get("companyId") or "") == str(companyId)]
    if project_type:
        filtered = [r for r in filtered if str(r.get("projectType")) == str(project_type)]
    return filtered[: max(1, int(count or 10))]


@router.get("/references/{id}")
@router.get("/references/{id}/")
def reference_by_id(id: str):
    r = content_repo.get_project_reference_by_id(id)
    if not r:
        raise HTTPException(status_code=404, detail="Reference not found")
    return r


@router.post("/references", status_code=201)
@router.post("/references/", status_code=201)
def create_reference(body: dict, background_tasks: BackgroundTasks):
    required = ["organizationName", "contactName", "contactEmail", "scopeOfWork"]
    for f in required:
        if not _clean_string((body or {}).get(f), max_len=20000):
            raise HTTPException(status_code=400, detail="Missing required fields")

    doc = dict(body or {})
    doc.update(
        {
            "companyId": _clean_nullable_string((body or {}).get("companyId"), max_len=80),
            "organizationName": _clean_string((body or {}).get("organizationName"), max_len=200),
            "contactName": _clean_string((body or {}).get("contactName"), max_len=200),
            "contactEmail": _clean_string((body or {}).get("contactEmail"), max_len=200),
            "scopeOfWork": _clean_string((body or {}).get("scopeOfWork"), max_len=20000),
            "contactTitle": _clean_string((body or {}).get("contactTitle"), max_len=200),
            "additionalTitle": _clean_string((body or {}).get("additionalTitle"), max_len=200),
            "contactPhone": _clean_string((body or {}).get("contactPhone"), max_len=60),
            "timePeriod": _clean_string((body or {}).get("timePeriod"), max_len=120),
            "projectType": _clean_string((body or {}).get("projectType"), max_len=120),
            "isPublic": (body or {}).get("isPublic") is not False,
            "isActive": True,
            "version": 1,
        }
    )
    created = content_repo.upsert_project_reference(doc)
    cid = str(created.get("companyId") or "").strip()
    if cid:
        background_tasks.add_task(regenerate_company_capabilities, cid)
    return created


@router.put("/references/{id}")
@router.put("/references/{id}/")
def update_reference(id: str, body: dict, background_tasks: BackgroundTasks):
    existing = content_repo.get_project_reference_by_id(id)
    if not existing:
        raise HTTPException(status_code=404, detail="Reference not found")

    conflict = _assert_version(existing, (body or {}).get("version"))
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)

    next_version = int(existing.get("version") or 0) + 1
    updates = dict(body or {})
    updates["referenceId"] = id
    updates["version"] = next_version

    for f, ml in (
        ("organizationName", 200),
        ("contactName", 200),
        ("contactEmail", 200),
        ("scopeOfWork", 20000),
        ("contactTitle", 200),
        ("additionalTitle", 200),
        ("contactPhone", 60),
        ("timePeriod", 120),
        ("projectType", 120),
    ):
        if f in updates:
            updates[f] = _clean_string(updates.get(f), max_len=ml)

    if "companyId" in updates:
        updates["companyId"] = _clean_nullable_string(updates.get("companyId"), max_len=80)

    if "isActive" in updates:
        updates["isActive"] = updates.get("isActive") is not False

    updated = content_repo.upsert_project_reference({**existing, **updates})
    prev_cid = str(existing.get("companyId") or "").strip()
    next_cid = str(updated.get("companyId") or "").strip()
    if prev_cid and prev_cid != next_cid:
        background_tasks.add_task(regenerate_company_capabilities, prev_cid)
    if next_cid:
        background_tasks.add_task(regenerate_company_capabilities, next_cid)
    return updated


@router.delete("/references/{id}")
@router.delete("/references/{id}/")
def delete_reference(id: str, background_tasks: BackgroundTasks):
    existing = content_repo.get_project_reference_by_id(id)
    if not existing:
        raise HTTPException(status_code=404, detail="Reference not found")

    content_repo.upsert_project_reference({**existing, "referenceId": id, "isActive": False})
    cid = str(existing.get("companyId") or "").strip()
    if cid:
        background_tasks.add_task(regenerate_company_capabilities, cid)
    return {"success": True}
