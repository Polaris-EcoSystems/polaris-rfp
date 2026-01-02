from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from jose import jwt

from app.settings import settings
from app.repositories import integrations_canva_repo as canva_repo_module
from app.infrastructure.storage import content_repo
from app.repositories import rfp_proposals_repo as proposals_repo
from app.repositories import rfp_rfps_repo as rfps_repo
from app.infrastructure.integrations.canva.canva_client import (
    build_authorize_url,
    create_autofill_job,
    create_export_job,
    create_url_asset_upload_job,
    download_url,
    exchange_code_for_token,
    get_autofill_job,
    get_brand_template_dataset,
    get_export_job,
    get_url_asset_upload_job,
    list_brand_templates,
    poll_job,
    upsert_connection_for_user,
)
from app.infrastructure.integrations.canva.canva_mapper import build_dataset_values, diagnose_dataset_values
from app.infrastructure.token_crypto import decrypt_string, encrypt_string

router = APIRouter(tags=["integrations_canva"])


def _user_id_from_request(request: Request) -> str:
    u = getattr(request.state, "user", None)
    # request.state.user is set by auth middleware and is a VerifiedUser (Cognito JWT).
    # Use the stable Cognito subject as the user identifier for per-user records.
    sub = getattr(u, "sub", None)
    if sub:
        return str(sub)
    # Legacy compatibility (older auth middleware)
    user_id = getattr(u, "user_id", None)
    if user_id:
        return str(user_id)
    raise HTTPException(status_code=401, detail="Unauthorized")


def _frontend_base_url() -> str:
    return (
        settings.frontend_base_url
        or settings.frontend_url
        or "https://rfp.polariseco.com"
    )


def _jwt_secret() -> str:
    # Align with legacy behavior: JWT_SECRET is used to sign Canva state
    secret = settings.jwt_secret or settings.canva_token_enc_key
    if not secret:
        raise HTTPException(
            status_code=500,
            detail={"error": "Missing JWT secret", "message": "Set JWT_SECRET or CANVA_TOKEN_ENC_KEY"},
        )
    return str(secret)


def _safe_json(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _collect_selected_ids_from_proposal_sections(sections: Any) -> tuple[list[str], list[str]]:
    team_ids: set[str] = set()
    ref_ids: set[str] = set()
    obj = sections if isinstance(sections, dict) else {}
    for s in obj.values():
        ids = s.get("selectedIds") if isinstance(s, dict) else None
        arr = ids if isinstance(ids, list) else []
        for idv in arr:
            v = str(idv or "").strip()
            if not v:
                continue
            if v.startswith("member_"):
                team_ids.add(v)
            elif v.startswith("company_"):
                continue
            elif v.startswith("ref_") or (len(v) == 24 and all(c in "0123456789abcdefABCDEF" for c in v)):
                ref_ids.add(v)
    return list(team_ids), list(ref_ids)


def _ensure_canva_design_for_proposal(*, user_id: str, proposal: dict[str, Any], cfg: dict[str, Any], force: bool) -> dict[str, Any]:
    company_id = str(proposal.get("companyId") or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail={"error": "Proposal has no companyId; select a company/branding first."})

    brand_template_id = str(cfg.get("brandTemplateId") or "").strip()
    if not brand_template_id:
        raise HTTPException(status_code=400, detail={"error": "No Canva template configured for this company."})

    if force:
        try:
            canva_repo_module.delete_proposal_design_cache(
                proposal_id=str(proposal.get("_id") or proposal.get("proposalId") or ""),
                company_id=company_id,
                brand_template_id=brand_template_id,
            )
        except Exception:
            pass

    proposal_id = str(proposal.get("_id") or proposal.get("proposalId") or "").strip()
    proposal_updated_at_raw = str(proposal.get("updatedAt") or "") or ""
    proposal_updated_at = None
    if proposal_updated_at_raw:
        try:
            proposal_updated_at = datetime.fromisoformat(proposal_updated_at_raw.replace("Z", "+00:00"))
        except Exception:
            proposal_updated_at = None

    existing = canva_repo_module.get_proposal_design_cache(
        proposal_id=proposal_id,
        company_id=company_id,
        brand_template_id=brand_template_id,
    )

    if existing and proposal_updated_at:
        last = _safe_json(existing.get("meta")).get("lastProposalUpdatedAt")
        try:
            last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        except Exception:
            last_dt = None
        if last_dt and last_dt >= proposal_updated_at:
            return {"cached": True, "record": existing}

    # hydrate
    rfp = rfps_repo.get_rfp_by_id(str(proposal.get("rfpId") or ""))
    company = content_repo.get_company_by_company_id(company_id)

    dataset_resp = get_brand_template_dataset(user_id, brand_template_id)
    dataset_def = _safe_json(dataset_resp.get("dataset"))

    team_ids, ref_ids = _collect_selected_ids_from_proposal_sections(proposal.get("sections"))
    team_members = content_repo.get_team_members_by_ids(team_ids) if team_ids else []
    references = content_repo.get_project_references_by_ids(ref_ids) if ref_ids else []

    company_logo = canva_repo_module.get_asset_link("company", company_id, "logo") or {}
    company_logo_asset_id = str(company_logo.get("canvaAssetId") or "").strip()

    headshot_by_member_id: dict[str, str] = {}
    for mid in team_ids:
        link = canva_repo_module.get_asset_link("teamMember", mid, "headshot")
        if link and link.get("ownerId") and link.get("canvaAssetId"):
            headshot_by_member_id[str(link["ownerId"])] = str(link["canvaAssetId"])

    mapping = _safe_json(cfg.get("fieldMapping"))
    values = build_dataset_values(
        dataset_def=dataset_def,
        mapping=mapping,
        proposal=proposal,
        rfp=rfp or {},
        company=company or {},
        company_logo_asset_id=company_logo_asset_id,
        team_members=team_members,
        headshot_by_member_id=headshot_by_member_id,
        references=references,
    )

    title = str(proposal.get("title") or "") or (
        f"Proposal for {rfp.get('title')}" if rfp and rfp.get("title") else "Proposal"
    )

    created = create_autofill_job(user_id, brand_template_id=brand_template_id, title=title, data=values)
    job_id = str(_safe_json(created.get("job")).get("id") or "")
    final_job = poll_job(lambda: get_autofill_job(user_id, job_id), timeout_ms=120000)

    if _safe_json(final_job.get("job")).get("status") != "success":
        raise HTTPException(status_code=400, detail={"error": "Canva autofill failed", "details": _safe_json(_safe_json(final_job.get("job")).get("error")) or None})

    design_summary = _safe_json(_safe_json(_safe_json(final_job.get("job")).get("result")).get("design"))
    design_id = str(design_summary.get("id") or "").strip()
    if not design_id:
        raise HTTPException(status_code=400, detail={"error": "No design ID returned from Canva"})

    now = datetime.now(timezone.utc)
    temp_urls_expire_at = (now + timedelta(days=29)).isoformat().replace("+00:00", "Z")

    record = canva_repo_module.upsert_proposal_design_cache(
        proposal_id=proposal_id,
        company_id=company_id,
        brand_template_id=brand_template_id,
        design_id=design_id,
        design_url=str(design_summary.get("url") or ""),
        meta={
            "editUrl": _safe_json(design_summary.get("urls")).get("edit_url") or "",
            "viewUrl": _safe_json(design_summary.get("urls")).get("view_url") or "",
            "tempUrlsExpireAt": temp_urls_expire_at,
            "lastProposalUpdatedAt": proposal.get("updatedAt") or now.isoformat().replace("+00:00", "Z"),
            "lastGeneratedAt": now.isoformat().replace("+00:00", "Z"),
        },
    )

    return {"cached": False, "record": record}


@router.get("/status")
def status(request: Request):
    return _status_impl(request)


@router.get("/status/")
def status_slash(request: Request):
    return _status_impl(request)


def _status_impl(request: Request):
    user_id = _user_id_from_request(request)
    conn = canva_repo_module.get_connection_for_user(user_id)
    if not conn:
        return {"connected": False, "connection": None}
    safe = dict(conn)
    safe.pop("accessTokenEnc", None)
    safe.pop("refreshTokenEnc", None)
    return {"connected": True, "connection": safe}


@router.post("/disconnect")
def disconnect(request: Request):
    user_id = _user_id_from_request(request)
    canva_repo_module.delete_connection_for_user(user_id)
    return {"ok": True}


@router.get("/connect-url")
def connect_url(request: Request, returnTo: str = "/integrations/canva"):
    user_id = _user_id_from_request(request)

    pkce_id = base64.urlsafe_b64encode(os.urandom(24)).decode("ascii").rstrip("=")
    # PKCE verifier + challenge
    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(__import__("hashlib").sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")

    state = jwt.encode(
        {"userId": user_id, "returnTo": str(returnTo or "/integrations/canva"), "pkceId": pkce_id, "nonce": base64.urlsafe_b64encode(os.urandom(12)).decode("ascii").rstrip("=")},
        _jwt_secret(),
        algorithm="HS256",
    )

    canva_repo_module.upsert_pkce_for_user(
        user_id,
        pkce_id,
        {"codeVerifierEnc": encrypt_string(verifier), "expiresAt": expires_at},
    )

    scopes = [
        "asset:read",
        "asset:write",
        "brandtemplate:meta:read",
        "brandtemplate:content:read",
        "design:content:read",
        "design:content:write",
        "design:meta:read",
    ]

    url = build_authorize_url(state=state, scopes=scopes, code_challenge=challenge)
    return {"url": url}


@router.get("/callback")
def callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"{_frontend_base_url()}/integrations/canva?error={error}")
    if not code or not state:
        return RedirectResponse(f"{_frontend_base_url()}/integrations/canva?error=missing_code")

    try:
        decoded = jwt.decode(state, _jwt_secret(), algorithms=["HS256"])
    except Exception:
        return RedirectResponse(f"{_frontend_base_url()}/integrations/canva?error=invalid_state")

    user_id = str(decoded.get("userId") or "")
    return_to = str(decoded.get("returnTo") or "/integrations/canva")
    pkce_id = str(decoded.get("pkceId") or "")
    if not user_id:
        return RedirectResponse(f"{_frontend_base_url()}/integrations/canva?error=missing_user")

    pkce = canva_repo_module.get_pkce_for_user(user_id, pkce_id) if pkce_id else None
    if not pkce or not pkce.get("codeVerifierEnc"):
        return RedirectResponse(f"{_frontend_base_url()}/integrations/canva?error=missing_pkce")

    if pkce.get("expiresAt"):
        try:
            exp = datetime.fromisoformat(str(pkce["expiresAt"]).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp:
                canva_repo_module.delete_pkce_for_user(user_id, pkce_id)
                return RedirectResponse(f"{_frontend_base_url()}/integrations/canva?error=pkce_expired")
        except Exception:
            pass

    canva_repo_module.delete_pkce_for_user(user_id, pkce_id)

    verifier = decrypt_string(pkce.get("codeVerifierEnc"))
    if not verifier:
        return RedirectResponse(f"{_frontend_base_url()}/integrations/canva?error=invalid_pkce")

    try:
        token = exchange_code_for_token(code=code, code_verifier=str(verifier))
        upsert_connection_for_user(user_id, token)
        return RedirectResponse(f"{_frontend_base_url()}{return_to}?connected=1")
    except Exception:
        return RedirectResponse(f"{_frontend_base_url()}/integrations/canva?error=callback_failed")


@router.get("/brand-templates")
def brand_templates(request: Request, query: str = ""):
    user_id = _user_id_from_request(request)
    try:
        return list_brand_templates(user_id, query=query)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Failed to list brand templates", "message": str(e)})


@router.get("/brand-templates/{id}/dataset")
def dataset(request: Request, id: str):
    user_id = _user_id_from_request(request)
    try:
        return get_brand_template_dataset(user_id, id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Failed to get template dataset", "message": str(e)})


@router.get("/company-mappings")
def list_company_mappings(request: Request):
    return _list_company_mappings_impl(request)


@router.get("/company-mappings/")
def list_company_mappings_slash(request: Request):
    return _list_company_mappings_impl(request)


def _list_company_mappings_impl(request: Request):
    _ = _user_id_from_request(request)
    items = canva_repo_module.list_company_mappings(limit=200)
    return {"data": items}


@router.put("/company-mappings/{companyId}")
def save_company_mapping(companyId: str, request: Request, body: dict):
    _ = _user_id_from_request(request)
    company_id = str(companyId or "").strip()
    brand_template_id = str((body or {}).get("brandTemplateId") or "").strip()
    field_mapping = (body or {}).get("fieldMapping")
    if not company_id:
        raise HTTPException(status_code=400, detail={"error": "companyId is required"})
    if not brand_template_id:
        raise HTTPException(status_code=400, detail={"error": "brandTemplateId is required"})
    doc = canva_repo_module.upsert_company_mapping(company_id, brand_template_id, field_mapping if isinstance(field_mapping, dict) else {})
    return doc


@router.get("/companies/{companyId}/logo")
def get_company_logo(companyId: str, request: Request):
    _ = _user_id_from_request(request)
    company_id = str(companyId or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail={"error": "companyId is required"})
    link = canva_repo_module.get_asset_link("company", company_id, "logo")
    if link:
        link = dict(link)
        link["assetId"] = link.get("canvaAssetId")
    return {"ok": True, "link": link or None}


@router.post("/companies/{companyId}/logo/upload-url")
def upload_company_logo(companyId: str, request: Request, body: dict):
    user_id = _user_id_from_request(request)
    company_id = str(companyId or "").strip()
    url = str((body or {}).get("url") or "").strip()
    name = str((body or {}).get("name") or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail={"error": "companyId is required"})
    if not url:
        raise HTTPException(status_code=400, detail={"error": "url is required"})
    company = content_repo.get_company_by_company_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail={"error": "Company not found"})

    created = create_url_asset_upload_job(
        user_id,
        name=name or f"{company.get('name') or ''} logo",
        url=url,
    )
    job_id = str(_safe_json(created.get("job")).get("id") or "")
    final_job = poll_job(lambda: get_url_asset_upload_job(user_id, job_id), timeout_ms=120000)
    if _safe_json(final_job.get("job")).get("status") != "success":
        raise HTTPException(status_code=400, detail={"error": "Canva asset upload failed", "details": _safe_json(_safe_json(final_job.get("job")).get("error")) or None})
    asset = _safe_json(_safe_json(final_job.get("job")).get("asset"))
    asset_id = str(asset.get("id") or "").strip()
    if not asset_id:
        raise HTTPException(status_code=400, detail={"error": "Canva asset upload failed"})

    link = canva_repo_module.upsert_asset_link(
        "company",
        company_id,
        "logo",
        asset_id,
        meta={**asset, "name": str(asset.get("name") or "")} if isinstance(asset, dict) else {},
        source_url=url,
    )
    link = dict(link)
    link["assetId"] = link.get("canvaAssetId")
    return {"ok": True, "company": company, "asset": asset, "link": link}


@router.get("/team/{memberId}/headshot")
def get_team_headshot(memberId: str, request: Request):
    _ = _user_id_from_request(request)
    member_id = str(memberId or "").strip()
    if not member_id:
        raise HTTPException(status_code=400, detail={"error": "memberId is required"})
    link = canva_repo_module.get_asset_link("teamMember", member_id, "headshot")
    if link:
        link = dict(link)
        link["assetId"] = link.get("canvaAssetId")
    return {"ok": True, "link": link or None}


@router.post("/team/{memberId}/headshot/upload-url")
def upload_team_headshot(memberId: str, request: Request, body: dict):
    user_id = _user_id_from_request(request)
    member_id = str(memberId or "").strip()
    url = str((body or {}).get("url") or "").strip()
    name = str((body or {}).get("name") or "").strip()
    if not member_id:
        raise HTTPException(status_code=400, detail={"error": "memberId is required"})
    if not url:
        raise HTTPException(status_code=400, detail={"error": "url is required"})

    member = content_repo.get_team_member_by_id(member_id)
    if not member:
        raise HTTPException(status_code=404, detail={"error": "Team member not found"})

    created = create_url_asset_upload_job(
        user_id,
        name=name or f"{member.get('nameWithCredentials') or ''} headshot",
        url=url,
    )
    job_id = str(_safe_json(created.get("job")).get("id") or "")
    final_job = poll_job(lambda: get_url_asset_upload_job(user_id, job_id), timeout_ms=120000)
    if _safe_json(final_job.get("job")).get("status") != "success":
        raise HTTPException(status_code=400, detail={"error": "Canva asset upload failed", "details": _safe_json(_safe_json(final_job.get("job")).get("error")) or None})
    asset = _safe_json(_safe_json(final_job.get("job")).get("asset"))
    asset_id = str(asset.get("id") or "").strip()
    if not asset_id:
        raise HTTPException(status_code=400, detail={"error": "Canva asset upload failed"})

    link = canva_repo_module.upsert_asset_link(
        "teamMember",
        member_id,
        "headshot",
        asset_id,
        meta={**asset, "name": str(asset.get("name") or "")} if isinstance(asset, dict) else {},
        source_url=url,
    )
    link = dict(link)
    link["assetId"] = link.get("canvaAssetId")
    return {"ok": True, "member": member, "asset": asset, "link": link}


@router.post("/proposals/{proposalId}/create-design")
def create_design_from_proposal(proposalId: str, request: Request, force: str | None = None):
    user_id = _user_id_from_request(request)
    proposal = proposals_repo.get_proposal_by_id(proposalId, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail={"error": "Proposal not found"})
    if not proposal.get("companyId"):
        raise HTTPException(status_code=400, detail={"error": "Proposal has no companyId; select a company/branding first."})

    cfg = canva_repo_module.get_company_mapping(str(proposal.get("companyId")))
    if not cfg:
        raise HTTPException(status_code=400, detail={"error": "No Canva template configured for this company."})

    ensured = _ensure_canva_design_for_proposal(user_id=user_id, proposal=proposal, cfg=cfg, force=(force == "1"))
    record = ensured["record"]
    meta = _safe_json(record.get("meta"))
    return {
        "ok": True,
        "brandTemplateId": cfg.get("brandTemplateId"),
        "cached": ensured["cached"],
        "design": {
            "id": record.get("designId"),
            "url": record.get("designUrl") or "",
            "urls": {"edit_url": meta.get("editUrl") or "", "view_url": meta.get("viewUrl") or ""},
        },
        "meta": {"lastGeneratedAt": meta.get("lastGeneratedAt"), "lastProposalUpdatedAt": meta.get("lastProposalUpdatedAt")},
    }


@router.post("/proposals/{proposalId}/validate")
def validate_proposal(proposalId: str, request: Request):
    user_id = _user_id_from_request(request)
    proposal = proposals_repo.get_proposal_by_id(proposalId, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail={"error": "Proposal not found"})
    company_id = str(proposal.get("companyId") or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail={"error": "Proposal has no companyId; select a company/branding first."})
    cfg = canva_repo_module.get_company_mapping(company_id)
    if not cfg:
        raise HTTPException(status_code=400, detail={"error": "No Canva template configured for this company."})

    dataset_resp = get_brand_template_dataset(user_id, str(cfg.get("brandTemplateId") or ""))
    dataset_def = _safe_json(dataset_resp.get("dataset"))

    rfp = rfps_repo.get_rfp_by_id(str(proposal.get("rfpId") or "")) or {}
    company = content_repo.get_company_by_company_id(company_id) or {}

    team_ids, ref_ids = _collect_selected_ids_from_proposal_sections(proposal.get("sections"))
    team_members = content_repo.get_team_members_by_ids(team_ids) if team_ids else []
    references = content_repo.get_project_references_by_ids(ref_ids) if ref_ids else []

    company_logo = canva_repo_module.get_asset_link("company", company_id, "logo") or {}
    company_logo_asset_id = str(company_logo.get("canvaAssetId") or "").strip()

    headshot_by_member_id: dict[str, str] = {}
    for mid in team_ids:
        link = canva_repo_module.get_asset_link("teamMember", mid, "headshot")
        if link and link.get("ownerId") and link.get("canvaAssetId"):
            headshot_by_member_id[str(link["ownerId"])] = str(link["canvaAssetId"])

    diag = diagnose_dataset_values(
        dataset_def=dataset_def,
        mapping=_safe_json(cfg.get("fieldMapping")),
        proposal=proposal,
        rfp=rfp,
        company=company,
        company_logo_asset_id=company_logo_asset_id,
        team_members=team_members,
        headshot_by_member_id=headshot_by_member_id,
        references=references,
    )

    return {
        "ok": True,
        "companyId": company_id,
        "brandTemplateId": cfg.get("brandTemplateId"),
        "totals": diag.get("totals"),
        "results": diag.get("results"),
    }


@router.get("/proposals/{proposalId}/export-pdf")
def export_proposal_pdf(proposalId: str, request: Request, mode: str | None = None):
    user_id = _user_id_from_request(request)
    proposal = proposals_repo.get_proposal_by_id(proposalId, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail={"error": "Proposal not found"})
    company_id = str(proposal.get("companyId") or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail={"error": "Proposal has no companyId; select a company/branding first."})
    cfg = canva_repo_module.get_company_mapping(company_id)
    if not cfg:
        raise HTTPException(status_code=400, detail={"error": "No Canva template configured for this company."})

    ensured = _ensure_canva_design_for_proposal(user_id=user_id, proposal=proposal, cfg=cfg, force=False)
    record = ensured["record"]
    design_id = str(record.get("designId") or "").strip()
    if not design_id:
        raise HTTPException(status_code=400, detail={"error": "No design ID available"})

    export_created = create_export_job(user_id, design_id=design_id, format="pdf")
    export_id = str(_safe_json(export_created.get("job")).get("id") or "")
    export_final = poll_job(lambda: get_export_job(user_id, export_id), timeout_ms=180000)
    if _safe_json(export_final.get("job")).get("status") != "success":
        raise HTTPException(status_code=400, detail={"error": "Canva export failed", "details": _safe_json(_safe_json(export_final.get("job")).get("error")) or None})

    urls = _safe_json(export_final.get("job")).get("urls")
    urls_list = urls if isinstance(urls, list) else []
    if not urls_list:
        raise HTTPException(status_code=400, detail={"error": "No download URLs returned from Canva"})

    if len(urls_list) > 1 and (mode or "") == "urls":
        return {"ok": True, "designId": design_id, "urls": urls_list, "cached": ensured["cached"]}

    data, content_type = download_url(str(urls_list[0]))
    filename = f"{str(proposal.get('title') or 'proposal').replace(' ', '_')}_canva.pdf"
    return Response(
        content=data,
        media_type=content_type or "application/pdf",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )
