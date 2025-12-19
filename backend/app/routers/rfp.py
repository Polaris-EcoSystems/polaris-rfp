from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, Request, UploadFile

from ..services.ai_section_titles import generate_section_titles
from ..services.rfp_analyzer import analyze_rfp
from ..services.rfps_repo import (
    create_rfp_from_analysis,
    delete_rfp,
    get_rfp_by_id,
    list_rfp_proposal_summaries,
    list_rfps,
    now_iso,
    update_rfp,
)
from ..services.attachments_repo import list_attachments
from ..services.s3_assets import (
    get_assets_bucket_name,
    get_object_bytes,
    head_object,
    make_rfp_upload_key,
    presign_put_object,
    to_s3_uri,
)
from ..services.rfp_upload_jobs_repo import create_job, get_job, get_job_item, update_job
from ..observability.logging import get_logger

router = APIRouter(tags=["rfp"])
log = get_logger("rfp")


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
    except RuntimeError as e:
        # Common user-facing errors should be 4xx, not 500s.
        msg = str(e) or "Failed to analyze URL"
        if "No extractable text" in msg:
            raise HTTPException(status_code=422, detail={"error": "Unable to extract text from URL", "message": msg})
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
    except RuntimeError as e:
        msg = str(e) or "Failed to analyze PDF"
        if "No extractable text" in msg:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Unable to extract text from PDF",
                    "message": "This PDF appears to contain no selectable text (scanned image). Please upload a text-based PDF or use Analyze URL for an HTML RFP page.",
                },
            )
        raise HTTPException(status_code=500, detail={"error": "Failed to process RFP", "message": msg})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Failed to process RFP", "message": str(e)})


@router.post("/upload/", status_code=201, include_in_schema=False)
async def upload_slash(file: UploadFile = File(...)):
    # Accept trailing slash to avoid 307 redirect (which breaks large uploads and proxying).
    return await upload(file=file)


@router.post("/upload/presign")
def presign_upload(body: dict = Body(...)):
    """
    Presign a direct-to-S3 upload for a PDF. This avoids sending large multipart
    bodies through the Next.js proxy layer (which often triggers 413).
    """
    file_name = str((body or {}).get("fileName") or "").strip() or "upload.pdf"
    content_type = str((body or {}).get("contentType") or "").strip().lower()
    if content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    key = make_rfp_upload_key(file_name=file_name)
    put = presign_put_object(key=key, content_type=content_type, expires_in=900)
    return {
        "ok": True,
        "bucket": put["bucket"],
        "key": key,
        "s3Uri": to_s3_uri(bucket=put["bucket"], key=key),
        "putUrl": put["url"],
        "expiresInSeconds": 900,
        "maxSizeBytes": 60 * 1024 * 1024,
    }


@router.post("/upload/from-s3", status_code=201)
def upload_from_s3(request: Request, background_tasks: BackgroundTasks, body: dict = Body(...)):
    """
    Create an async analysis job for an uploaded S3 PDF.
    """
    key = str((body or {}).get("key") or "").strip()
    file_name = str((body or {}).get("fileName") or "").strip() or "upload.pdf"
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    if not key.startswith("rfp/uploads/"):
        raise HTTPException(status_code=400, detail="Invalid key")

    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip()
    if not user_sub:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Basic sanity check (fast) before enqueueing.
    meta = head_object(key=key)
    size = int(meta.get("ContentLength") or 0)
    if size <= 0:
        raise HTTPException(status_code=400, detail="Uploaded object is empty")
    if size > 60 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    job = create_job(user_sub=user_sub, s3_key=key, file_name=file_name)
    background_tasks.add_task(_process_rfp_upload_job, job["jobId"])
    return {"ok": True, "job": job}


@router.get("/upload/jobs/{jobId}")
def upload_job_status(request: Request, jobId: str):
    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip()
    if not user_sub:
        raise HTTPException(status_code=401, detail="Unauthorized")

    raw = get_job_item(jobId)
    if not raw:
        raise HTTPException(status_code=404, detail="Job not found")
    if str(raw.get("userSub") or "") != user_sub:
        raise HTTPException(status_code=404, detail="Job not found")
    job = get_job(jobId)
    return {"ok": True, "job": job}


def _process_rfp_upload_job(job_id: str) -> None:
    # Best-effort background processing. Status is persisted to DynamoDB.
    log.info("rfp_upload_job_starting", jobId=job_id)
    job = get_job_item(job_id) or {}
    if not job:
        return
    if job.get("status") not in ("queued", "processing"):
        return

    try:
        update_job(
            job_id=job_id,
            updates_obj={
                "status": "processing",
                "startedAt": now_iso(),
                "updatedAt": now_iso(),
            },
        )

        key = str(job.get("s3Key") or "").strip()
        file_name = str(job.get("fileName") or "upload.pdf").strip() or "upload.pdf"

        data = get_object_bytes(key=key, max_bytes=60 * 1024 * 1024)
        if not data:
            update_job(
                job_id=job_id,
                updates_obj={
                    "status": "failed",
                    "error": "Uploaded object is empty",
                    "finishedAt": now_iso(),
                    "updatedAt": now_iso(),
                },
            )
            return

        analysis = analyze_rfp(data, file_name)
        saved = create_rfp_from_analysis(
            analysis=analysis,
            source_file_name=file_name,
            source_file_size=len(data),
        )
        rfp_id = str(saved.get("_id") or saved.get("rfpId") or "").strip()

        update_job(
            job_id=job_id,
            updates_obj={
                "status": "completed",
                "rfpId": rfp_id,
                "sourceS3Uri": to_s3_uri(bucket=get_assets_bucket_name(), key=key),
                "finishedAt": now_iso(),
                "updatedAt": now_iso(),
            },
        )
        log.info("rfp_upload_job_completed", jobId=job_id, rfpId=rfp_id)
    except Exception as e:
        update_job(
            job_id=job_id,
            updates_obj={
                "status": "failed",
                "error": str(e) or "Failed to process RFP",
                "finishedAt": now_iso(),
                "updatedAt": now_iso(),
            },
        )
        log.exception("rfp_upload_job_failed", jobId=job_id)


@router.get("/")
def get_all(request: Request, page: int = 1, limit: int = 20, nextToken: str | None = None):
    try:
        return list_rfps(page=page, limit=limit, next_token=nextToken)
    except Exception as e:
        # Ensure we get a traceback in CloudWatch (these errors are otherwise swallowed by HTTPException).
        rid = getattr(getattr(request, "state", None), "request_id", None)
        user = getattr(getattr(request, "state", None), "user", None)
        user_sub = getattr(user, "sub", None) if user else None
        log.exception(
            "rfp_list_failed",
            request_id=str(rid) if rid else None,
            user_sub=str(user_sub) if user_sub else None,
        )
        raise HTTPException(status_code=500, detail="Failed to fetch RFPs") from e


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
        # Frontend expects attachments embedded on the RFP record.
        try:
            rfp = dict(rfp)
            rfp["attachments"] = list_attachments(id)
        except Exception:
            # If attachments table/layout isn't configured, keep RFP readable.
            rfp = dict(rfp)
            rfp["attachments"] = []
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
        # Keep compatibility with frontend expecting embedded attachments.
        try:
            out = dict(updated)
            out["attachments"] = list_attachments(id)
            return out
        except Exception:
            out = dict(updated)
            out["attachments"] = []
            return out
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update RFP")


@router.put("/{id}/review")
def update_review(id: str, request: Request, body: dict = Body(...)):
    """
    Persist human review for bid/no-bid decisions and review artifacts.

    Body:
      - decision: "" | "bid" | "no_bid" | "maybe" (optional)
      - notes: string (optional)
      - reasons: string[] (optional)
      - blockers: { id?: string, text: string, status: "open"|"resolved"|"waived" }[] (optional)
      - requirements: {
            text: string,
            status: "unknown"|"ok"|"risk"|"gap",
            notes?: string,
            mappedSections?: string[]
        }[] (optional)
    """
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    b = body or {}
    existing_review = rfp.get("review")
    base_review: dict[str, Any] = (
        dict(existing_review) if isinstance(existing_review, dict) else {}
    )

    # Only validate/apply fields that were provided (PATCH semantics).
    if "decision" in b:
        decision = str(b.get("decision") or "").strip().lower()
        allowed = {"", "bid", "no_bid", "maybe"}
        if decision not in allowed:
            raise HTTPException(status_code=400, detail="Invalid decision")
        base_review["decision"] = decision

    if "notes" in b:
        notes_raw = b.get("notes")
        notes = str(notes_raw or "")
        if len(notes) > 20000:
            raise HTTPException(status_code=400, detail="notes is too long")
        base_review["notes"] = notes

    if "reasons" in b:
        reasons_in = b.get("reasons")
        reasons: list[str] = []
        if isinstance(reasons_in, list):
            for x in reasons_in[:50]:
                s = str(x or "").strip()
                if not s:
                    continue
                if len(s) > 140:
                    continue
                reasons.append(s)
        base_review["reasons"] = reasons

    if "blockers" in b:
        blockers_in = b.get("blockers")
        blockers: list[dict[str, Any]] = []
        if isinstance(blockers_in, list):
            for x in blockers_in[:100]:
                if not isinstance(x, dict):
                    continue
                text = str(x.get("text") or "").strip()
                if not text:
                    continue
                if len(text) > 300:
                    continue
                status = str(x.get("status") or "open").strip().lower()
                if status not in {"open", "resolved", "waived"}:
                    status = "open"
                bid = str(x.get("id") or "").strip()
                obj: dict[str, Any] = {"text": text, "status": status}
                if bid and len(bid) <= 80:
                    obj["id"] = bid
                blockers.append(obj)
        base_review["blockers"] = blockers

    if "requirements" in b:
        req_in = b.get("requirements")
        reqs: list[dict[str, Any]] = []
        if isinstance(req_in, list):
            for x in req_in[:250]:
                if not isinstance(x, dict):
                    continue
                text = str(x.get("text") or "").strip()
                if not text:
                    continue
                if len(text) > 600:
                    continue
                status = str(x.get("status") or "unknown").strip().lower()
                if status not in {"unknown", "ok", "risk", "gap"}:
                    status = "unknown"
                notes = str(x.get("notes") or "")
                if len(notes) > 20000:
                    notes = notes[:20000]
                mapped_in = x.get("mappedSections")
                mapped: list[str] = []
                if isinstance(mapped_in, list):
                    for m in mapped_in[:20]:
                        s = str(m or "").strip()
                        if s and len(s) <= 80:
                            mapped.append(s)
                obj = {"text": text, "status": status, "notes": notes, "mappedSections": mapped}
                reqs.append(obj)
        base_review["requirements"] = reqs

    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip() if user else ""

    review: dict[str, Any] = dict(base_review)
    review["updatedAt"] = now_iso()
    if user_sub:
        review["updatedBy"] = user_sub

    updated = update_rfp(id, {"review": review})
    if not updated:
        raise HTTPException(status_code=404, detail="RFP not found")

    # Keep compatibility with frontend expecting embedded attachments.
    try:
        out = dict(updated)
        out["attachments"] = list_attachments(id)
        return out
    except Exception:
        out = dict(updated)
        out["attachments"] = []
        return out


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


@router.post("/{id}/buyer-profiles/remove")
def remove_buyer_profiles(id: str, body: dict = Body(...)):
    """
    Remove saved buyer profiles from an RFP.

    Body:
      - selected: string[] (profileUrl/profileId tokens)
      - clear: boolean (if true, clears all buyerProfiles)
    """
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    clear = bool((body or {}).get("clear"))
    existing = (rfp or {}).get("buyerProfiles")
    existing_list: list[dict[str, Any]] = (
        existing if isinstance(existing, list) else []
    )

    if clear:
        updated = update_rfp(id, {"buyerProfiles": []})
        return {"success": True, "removed": len(existing_list), "rfp": updated}

    selected_in = (body or {}).get("selected")
    if not isinstance(selected_in, list):
        raise HTTPException(status_code=400, detail="selected[] is required (or set clear=true)")

    selected = [str(x or "").strip().lower() for x in selected_in]
    selected = [x for x in selected if x]
    if not selected:
        raise HTTPException(status_code=400, detail="selected[] is required (or set clear=true)")

    selected_set = set(selected)

    def token(p: dict[str, Any]) -> set[str]:
        toks: set[str] = set()
        pu = str(p.get("profileUrl") or "").strip().lower()
        pid = str(p.get("profileId") or "").strip().lower()
        if pu:
            toks.add(pu)
        if pid:
            toks.add(pid)
        return toks

    kept: list[dict[str, Any]] = []
    removed = 0
    for p in existing_list:
        if not isinstance(p, dict):
            continue
        toks = token(p)
        if toks and any(t in selected_set for t in toks):
            removed += 1
            continue
        kept.append(p)

    updated = update_rfp(id, {"buyerProfiles": kept})
    return {"success": True, "removed": removed, "remaining": len(kept), "rfp": updated}
