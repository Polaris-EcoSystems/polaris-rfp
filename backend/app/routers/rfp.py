from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..services.ai_section_titles import generate_section_titles
from ..services.rfp_analyzer import analyze_rfp
from ..services.rfps_repo import (
    create_rfp_from_analysis,
    delete_rfp,
    get_rfp_by_id,
    list_rfp_proposal_summaries,
    list_rfps,
    update_rfp,
)

router = APIRouter(tags=["rfp"])


@router.post("/analyze-url", status_code=201)
def analyze_url(body: dict):
    url = str((body or {}).get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    try:
        analysis = analyze_rfp(url, url)
        saved = create_rfp_from_analysis(
            analysis=analysis, source_file_name=f"URL_{int(__import__('time').time()*1000)}", source_file_size=0
        )
        return saved
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"error": "Failed to analyze RFP from URL", "message": str(e)}
        )


@router.post("/analyze-urls", status_code=201)
def analyze_urls(body: dict):
    urls_in = (body or {}).get("urls")
    urls = [str(u or "").strip() for u in (urls_in if isinstance(urls_in, list) else [])]
    urls = [u for u in urls if u]
    if not urls:
        raise HTTPException(status_code=400, detail="urls[] is required")

    results: list[dict[str, Any]] = []
    for url in urls:
        try:
            analysis = analyze_rfp(url, url)
            saved = create_rfp_from_analysis(
                analysis=analysis, source_file_name=f"URL_{int(__import__('time').time()*1000)}", source_file_size=0
            )
            results.append({"url": url, "ok": True, "rfp": saved})
        except Exception as e:
            results.append({"url": url, "ok": False, "error": str(e) or "Failed to analyze URL"})

    return {"results": results}


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        analysis = analyze_rfp(data, file.filename or "upload.pdf")
        saved = create_rfp_from_analysis(
            analysis=analysis,
            source_file_name=file.filename or "upload.pdf",
            source_file_size=len(data),
        )
        return saved
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Failed to process RFP", "message": str(e)})


@router.get("/")
def get_all(page: int = 1, limit: int = 20):
    try:
        return list_rfps(page=page, limit=limit)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch RFPs")


@router.get("/search/{query}")
def search(query: str):
    try:
        q = str(query or "").lower()
        resp = list_rfps(page=1, limit=200)
        data = resp.get("data") or []
        filtered = []
        for r in data:
            hay = f"{r.get('title') or ''} {r.get('clientName') or ''} {r.get('projectType') or ''}".lower()
            if q in hay:
                filtered.append(r)
        return filtered[:20]
    except Exception:
        raise HTTPException(status_code=500, detail="Search failed")


@router.get("/{id}")
def get_one(id: str):
    try:
        rfp = get_rfp_by_id(id)
        if not rfp:
            raise HTTPException(status_code=404, detail="RFP not found")
        return rfp
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch RFP")


@router.post("/{id}/ai-section-titles")
def ai_section_titles(id: str):
    try:
        rfp = get_rfp_by_id(id)
        if not rfp:
            raise HTTPException(status_code=404, detail="RFP not found")
        if isinstance(rfp.get("sectionTitles"), list) and rfp.get("sectionTitles"):
            return {"titles": rfp["sectionTitles"]}
        titles = generate_section_titles(rfp)
        update_rfp(id, {"sectionTitles": titles})
        return {"titles": titles}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"error": "Failed to generate section titles", "message": str(e)}
        )


@router.put("/{id}")
def update_one(id: str, body: dict):
    try:
        updated = update_rfp(id, body or {})
        if not updated:
            raise HTTPException(status_code=404, detail="RFP not found")
        return updated
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update RFP")


@router.get("/{id}/proposals")
def proposals_for_rfp(id: str):
    try:
        proposals = list_rfp_proposal_summaries(id)
        return {"data": proposals}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch RFP proposals")


@router.delete("/{id}")
def delete_one(id: str):
    try:
        delete_rfp(id)
        return {"message": "RFP deleted successfully"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete RFP")
