from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..services import canva_repo, content_repo

router = APIRouter(tags=["integrations_canva"])


def _user_id_from_request(request: Request) -> str:
    # set by auth middleware (VerifiedUser dataclass)
    u = getattr(request.state, "user", None)
    user_id = getattr(u, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(user_id)


@router.get("/status")
def status(request: Request):
    try:
        user_id = _user_id_from_request(request)
        conn = canva_repo.get_connection_for_user(user_id)
        if not conn:
            return {"connected": False, "connection": None}

        safe = dict(conn)
        safe.pop("accessTokenEnc", None)
        safe.pop("refreshTokenEnc", None)
        return {"connected": True, "connection": safe}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail={"error": "Failed to get Canva status"})


@router.post("/disconnect")
def disconnect(request: Request):
    try:
        user_id = _user_id_from_request(request)
        canva_repo.delete_connection_for_user(user_id)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail={"error": "Failed to disconnect Canva"})


@router.get("/connect-url")
def connect_url(_request: Request, returnTo: str = "/integrations/canva"):
    # Full Canva OAuth flow is not yet implemented in FastAPI.
    raise HTTPException(status_code=500, detail={"error": "Canva connect is not configured"})


@router.get("/callback")
def callback():
    # Placeholder: in Node this redirects back to the frontend.
    raise HTTPException(status_code=500, detail={"error": "Canva callback is not implemented"})


@router.get("/brand-templates")
def list_brand_templates(_request: Request, query: str = ""):
    raise HTTPException(status_code=500, detail={"error": "Canva is not configured"})


@router.get("/brand-templates/{id}/dataset")
def get_dataset(id: str, _request: Request):
    raise HTTPException(status_code=500, detail={"error": "Canva is not configured"})


@router.get("/company-mappings")
def list_company_mappings(_request: Request):
    try:
        items = canva_repo.list_company_mappings(limit=200)
        return {"data": items}
    except Exception:
        raise HTTPException(status_code=500, detail={"error": "Failed to load Canva mappings"})


@router.put("/company-mappings/{companyId}")
def save_company_mapping(companyId: str, request: Request, body: dict):
    _ = _user_id_from_request(request)

    company_id = str(companyId or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail={"error": "companyId is required"})

    brand_template_id = (body or {}).get("brandTemplateId")
    field_mapping = (body or {}).get("fieldMapping")

    if not brand_template_id:
        raise HTTPException(status_code=400, detail={"error": "brandTemplateId is required"})

    try:
        doc = canva_repo.upsert_company_mapping(
            company_id,
            str(brand_template_id).strip(),
            field_mapping if isinstance(field_mapping, dict) else {},
        )
        return doc
    except Exception:
        raise HTTPException(status_code=500, detail={"error": "Failed to save Canva mapping"})


@router.get("/companies/{companyId}/logo")
def get_company_logo(companyId: str, request: Request):
    _ = _user_id_from_request(request)

    company_id = str(companyId or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail={"error": "companyId is required"})

    try:
        link = canva_repo.get_asset_link("company", company_id, "logo")
        if link:
            link = dict(link)
            link["assetId"] = link.get("canvaAssetId")
        return {"ok": True, "link": link or None}
    except Exception:
        raise HTTPException(
            status_code=500, detail={"error": "Failed to load company logo asset link"}
        )


@router.post("/companies/{companyId}/logo/upload-url")
def upload_company_logo(companyId: str, request: Request, body: dict):
    _ = _user_id_from_request(request)

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

    # Not yet implemented: upload to Canva and store returned asset id.
    raise HTTPException(status_code=500, detail={"error": "Canva is not configured"})


@router.get("/team/{memberId}/headshot")
def get_team_headshot(memberId: str, request: Request):
    _ = _user_id_from_request(request)

    member_id = str(memberId or "").strip()
    if not member_id:
        raise HTTPException(status_code=400, detail={"error": "memberId is required"})

    try:
        link = canva_repo.get_asset_link("teamMember", member_id, "headshot")
        if link:
            link = dict(link)
            link["assetId"] = link.get("canvaAssetId")
        return {"ok": True, "link": link or None}
    except Exception:
        raise HTTPException(status_code=500, detail={"error": "Failed to load headshot asset link"})


@router.post("/team/{memberId}/headshot/upload-url")
def upload_team_headshot(memberId: str, request: Request, body: dict):
    _ = _user_id_from_request(request)

    member_id = str(memberId or "").strip()
    url = str((body or {}).get("url") or "").strip()

    if not member_id:
        raise HTTPException(status_code=400, detail={"error": "memberId is required"})
    if not url:
        raise HTTPException(status_code=400, detail={"error": "url is required"})

    # Not yet implemented: upload to Canva and store returned asset id.
    raise HTTPException(status_code=500, detail={"error": "Canva is not configured"})


@router.post("/proposals/{proposalId}/create-design")
def create_design_from_proposal(proposalId: str, request: Request):
    _ = _user_id_from_request(request)
    raise HTTPException(status_code=500, detail={"error": "Canva is not configured"})


@router.post("/proposals/{proposalId}/validate")
def validate_proposal(proposalId: str, request: Request):
    _ = _user_id_from_request(request)
    raise HTTPException(status_code=500, detail={"error": "Canva is not configured"})


@router.get("/proposals/{proposalId}/export-pdf")
def export_proposal_pdf(proposalId: str, request: Request):
    _ = _user_id_from_request(request)
    raise HTTPException(status_code=500, detail={"error": "Canva is not configured"})
