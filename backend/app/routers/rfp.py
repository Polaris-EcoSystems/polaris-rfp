from __future__ import annotations

from typing import Any, Iterator

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.db.dynamodb.errors import DdbConflict
from app.db.dynamodb.table import get_main_table
from app.pipeline.proposal_generation.ai_section_titles import generate_section_titles
from app.pipeline.intake.rfp_analyzer import analyze_rfp
from app.pipeline.intake.opportunity_tracker_import import parse_opportunity_tracker_csv, row_to_rfp_and_tracker
from app.repositories.rfp_rfps_repo import (
    create_rfp_from_analysis,
    delete_rfp,
    get_rfp_by_id,
    list_rfp_proposal_summaries,
    list_rfps,
    now_iso,
    update_rfp,
)
from app.workflow import sync_for_rfp
from app.repositories.attachments_repo import list_attachments
from app.infrastructure.storage.s3_assets import (
    get_assets_bucket_name,
    get_object_bytes,
    head_object,
    make_rfp_upload_key_for_hash,
    presign_get_object,
    presign_put_object,
    to_s3_uri,
)
from app.repositories.rfp_upload_jobs_repo import create_job, get_job, get_job_item, update_job
from app.repositories.rfp_pdf_dedup_repo import (
    dedup_key,
    ensure_record,
    get_by_sha256,
    normalize_sha256,
    reset_stale_mapping,
)
from app.repositories.rfp_opportunity_state_repo import ensure_state_exists, get_state, patch_state
from app.repositories.opportunity_tracker_repo import compute_row_key_sha, get_mapping, put_mapping, touch_mapping
from app.repositories.rfp_scraper_jobs_repo import (
    create_job as create_scraper_job,
    get_job as get_scraper_job,
    list_jobs as list_scraper_jobs,
)
from app.repositories import rfp_intake_queue_repo, rfp_scraper_schedules_repo
from app.repositories.rfp_scraped_rfps_repo import (
    get_scraped_rfp_by_id,
    list_scraped_rfps,
    mark_scraped_rfp_imported,
    update_scraped_rfp,
)
from app.pipeline.search.rfp_scrapers.scraper_registry import (
    get_available_sources,
    is_source_available,
    is_source_available_for_user,
)
from app.pipeline.search.rfp_scraper_job_runner import process_scraper_job
from app.repositories.outbox_repo import enqueue_event
from app.observability.logging import get_logger
from app.settings import settings
from app.ai.client import AiNotConfigured, AiError, AiUpstreamError
from app.ai.context import clip_text
from app.ai.schemas import RfpDatesAI, RfpListsAI, RfpMetaAI
from app.ai.verified_calls import call_json_verified, call_text_verified

import json
import time
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

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
            source_pdf_data=data,
        )
        # Best-effort: notify Slack (machine channel) for direct uploads too.
        try:
            rfp_id = str(saved.get("_id") or saved.get("rfpId") or "").strip()
            enqueue_event(
                event_type="slack.rfp_upload_completed",
                payload={
                    "jobId": "direct_upload",
                    "rfpId": rfp_id,
                    "fileName": file.filename or "upload.pdf",
                    "channel": str(settings.slack_rfp_machine_channel or "").strip() or None,
                },
                dedupe_key=f"rfp_upload_completed:direct_upload:{rfp_id}",
            )
        except Exception:
            pass
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


@router.post("/opportunity-tracker/import")
async def import_opportunity_tracker(request: Request, file: UploadFile = File(...)):
    """
    Import the Opportunity Tracker CSV (Google Sheets export).

    This creates/upserts:
    - RFP records (minimal fields: title/clientName/submissionDeadline)
    - OpportunityState.state.tracker fields (Point Person, Notes, Value, etc.)

    Idempotency/dedupe:
    - A stable row key (sha256) is computed from Opportunity + Due Date + Entity + Applying Entity + Q/A link.
    - If a row was previously imported, we update the existing RFP + tracker instead of creating a duplicate.
    """
    try:
        raw = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    text = (raw or b"").decode("utf-8", errors="ignore")
    try:
        rows = parse_opportunity_tracker_csv(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Opportunity Tracker CSV: {str(e) or 'parse error'}")

    created: list[str] = []
    updated: list[str] = []
    errors: list[dict[str, Any]] = []

    # CSV is small, but keep a hard cap to avoid accidental huge uploads.
    for idx, row in enumerate(rows[:2000], start=1):
        try:
            conv = row_to_rfp_and_tracker(row)
            opportunity = str(conv.get("opportunity") or "").strip()
            entity = str(conv.get("entity") or "").strip()
            applying_entity = str(conv.get("applyingEntity") or "").strip()
            due_date = str(conv.get("dueDate") or "").strip()
            qa = str((row or {}).get("Question/Answers") or "").strip()

            row_sha = compute_row_key_sha(parts=[opportunity, due_date, entity, applying_entity, qa])
            mapping = get_mapping(row_key_sha=row_sha) or {}
            rfp_id = str(mapping.get("rfpId") or "").strip() or None

            # Build patches.
            analysis = conv.get("rfpAnalysis") if isinstance(conv.get("rfpAnalysis"), dict) else {}
            tracker_patch = conv.get("trackerPatch") if isinstance(conv.get("trackerPatch"), dict) else {}
            due_patch = conv.get("dueDatesPatch") if isinstance(conv.get("dueDatesPatch"), dict) else {}

            st_patch: dict[str, Any] = {"tracker": tracker_patch}
            if due_patch:
                st_patch["dueDates"] = due_patch

            if rfp_id:
                # Update minimal RFP fields.
                patch: dict[str, Any] = {}
                if isinstance(analysis, dict):
                    if analysis.get("title"):
                        patch["title"] = analysis.get("title")
                    if analysis.get("clientName"):
                        patch["clientName"] = analysis.get("clientName")
                    if analysis.get("submissionDeadline"):
                        patch["submissionDeadline"] = analysis.get("submissionDeadline")
                if patch:
                    update_rfp(rfp_id, patch)

                # Update tracker (no snapshot spam on bulk import).
                patch_state(rfp_id=rfp_id, patch=st_patch, updated_by_user_sub=None, create_snapshot=False)
                touch_mapping(row_key_sha=row_sha)
                updated.append(rfp_id)
                continue

            # Create new RFP.
            saved = create_rfp_from_analysis(
                analysis=analysis if isinstance(analysis, dict) else {},
                source_file_name=f"OpportunityTrackerCSV:{file.filename or 'upload.csv'}",
                source_file_size=int(len(raw or b"")),
            )
            rfp_id = str((saved or {}).get("_id") or "").strip() or None
            if not rfp_id:
                raise RuntimeError("Failed to create RFP")

            put_mapping(row_key_sha=row_sha, rfp_id=rfp_id)
            patch_state(rfp_id=rfp_id, patch=st_patch, updated_by_user_sub=None, create_snapshot=False)
            created.append(rfp_id)
        except Exception as e:
            errors.append(
                {
                    "row": idx,
                    "error": str(e) or "Failed to import row",
                    "opportunity": str((row or {}).get("Opportunity") or "")[:200],
                }
            )

    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "errors": errors[:50],
        "stats": {"rows": len(rows), "created": len(created), "updated": len(updated), "errors": len(errors)},
    }


@router.post("/upload/presign")
def presign_upload(body: dict = Body(...)):
    """
    Presign a direct-to-S3 upload for a PDF. This avoids sending large multipart
    bodies through the Next.js proxy layer (which often triggers 413).
    """
    file_name = str((body or {}).get("fileName") or "").strip() or "upload.pdf"
    content_type = str((body or {}).get("contentType") or "").strip().lower()
    sha256 = str((body or {}).get("sha256") or "").strip()
    if content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        sha = normalize_sha256(sha256)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e) or "Invalid sha256") from e

    existing = get_by_sha256(sha) or {}
    existing_rfp_id = str(existing.get("rfpId") or "").strip()
    existing_status = str(existing.get("status") or "").strip().lower()
    if existing_rfp_id and existing_status == "completed":
        # Guard against stale de-dupe mappings: only treat as a duplicate if the
        # referenced RFP record still exists.
        try:
            if get_rfp_by_id(existing_rfp_id):
                return {
                    "ok": True,
                    "duplicate": True,
                    "rfpId": existing_rfp_id,
                }
        except Exception:
            # If lookup errors, fall through and allow a fresh upload path.
            pass

    key = make_rfp_upload_key_for_hash(sha256=sha)
    # If a de-dupe record exists but points to a missing RFP, clear it so the
    # transactional completion path can succeed.
    if existing_rfp_id and existing_status == "completed":
        try:
            reset_stale_mapping(
                sha256=sha,
                s3_key=key,
                reason=f"stale dedup mapping: rfpId {existing_rfp_id} not found",
            )
        except Exception:
            pass
    # Ensure a de-dupe record exists (best-effort reservation).
    try:
        ensure_record(sha256=sha, s3_key=key)
    except Exception:
        pass

    put = presign_put_object(key=key, content_type=content_type, expires_in=900)
    return {
        "ok": True,
        "duplicate": False,
        "fileName": file_name,
        "bucket": put["bucket"],
        "key": key,
        "s3Uri": to_s3_uri(bucket=put["bucket"], key=key),
        "putUrl": put["url"],
        "expiresInSeconds": 900,
        "maxSizeBytes": 60 * 1024 * 1024,
    }

@router.post("/upload/presign/", include_in_schema=False)
def presign_upload_slash(body: dict = Body(...)):
    # Accept trailing slash to avoid 307 redirect loops through the Next proxy.
    return presign_upload(body=body)


@router.post("/upload/from-s3", status_code=201)
def upload_from_s3(request: Request, background_tasks: BackgroundTasks, body: dict = Body(...)):
    """
    Create an async analysis job for an uploaded S3 PDF.
    """
    key = str((body or {}).get("key") or "").strip()
    file_name = str((body or {}).get("fileName") or "").strip() or "upload.pdf"
    sha256 = str((body or {}).get("sha256") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    try:
        sha = normalize_sha256(sha256)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e) or "Invalid sha256") from e

    expected_key = make_rfp_upload_key_for_hash(sha256=sha)
    if key != expected_key:
        raise HTTPException(status_code=400, detail="Invalid key for sha256")

    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip()
    if not user_sub:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Ensure a de-dupe record exists (best-effort; keeps processor logic simple).
    try:
        ensure_record(sha256=sha, s3_key=key)
    except Exception:
        pass

    # Basic sanity check (fast) before enqueueing.
    meta = head_object(key=key)
    size = int(meta.get("ContentLength") or 0)
    if size <= 0:
        raise HTTPException(status_code=400, detail="Uploaded object is empty")
    if size > 60 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    job = create_job(user_sub=user_sub, s3_key=key, file_name=file_name, sha256=sha)
    background_tasks.add_task(_process_rfp_upload_job, job["jobId"])
    return {"ok": True, "job": job}

@router.post("/upload/from-s3/", status_code=201, include_in_schema=False)
def upload_from_s3_slash(request: Request, background_tasks: BackgroundTasks, body: dict = Body(...)):
    # Accept trailing slash to avoid 307 redirect loops through the Next proxy.
    return upload_from_s3(request=request, background_tasks=background_tasks, body=body)


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


@router.get("/upload/jobs/{jobId}/", include_in_schema=False)
def upload_job_status_slash(request: Request, jobId: str):
    # Accept trailing slash to avoid 307 redirect loops through the Next proxy.
    return upload_job_status(request=request, jobId=jobId)


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
        sha_claim = str(job.get("sha256") or "").strip()
        try:
            sha = normalize_sha256(sha_claim)
        except Exception:
            # Fall back to extracting from the deterministic key format.
            m = re.search(r"^rfp/uploads/sha256/([a-f0-9]{64})\.pdf$", key or "")
            sha = m.group(1) if m else ""
        if not sha:
            update_job(
                job_id=job_id,
                updates_obj={
                    "status": "failed",
                    "error": "Missing sha256 on upload job",
                    "finishedAt": now_iso(),
                    "updatedAt": now_iso(),
                },
            )
            enqueue_event(
                event_type="slack.rfp_upload_failed",
                payload={"jobId": job_id, "fileName": file_name, "error": "Missing sha256 on upload job"},
                dedupe_key=f"rfp_upload_failed:{job_id}",
            )
            return

        # If we've already processed this exact PDF before, short-circuit.
        existing = get_by_sha256(sha) or {}
        existing_rfp_id = str(existing.get("rfpId") or "").strip()
        existing_status = str(existing.get("status") or "").strip().lower()
        if existing_rfp_id and existing_status == "completed":
            # Only treat as deduped if the referenced RFP still exists. If the mapping
            # is stale, clear it and continue with processing.
            try:
                if get_rfp_by_id(existing_rfp_id):
                    update_job(
                        job_id=job_id,
                        updates_obj={
                            "status": "completed",
                            "rfpId": existing_rfp_id,
                            "sourceS3Uri": to_s3_uri(bucket=get_assets_bucket_name(), key=key),
                            "finishedAt": now_iso(),
                            "updatedAt": now_iso(),
                        },
                    )
                    log.info(
                        "rfp_upload_job_deduped",
                        jobId=job_id,
                        rfpId=existing_rfp_id,
                        sha256=sha,
                    )
                    enqueue_event(
                        event_type="slack.rfp_upload_completed",
                        payload={
                            "jobId": job_id,
                            "rfpId": existing_rfp_id,
                            "fileName": file_name,
                            "channel": str(settings.slack_rfp_machine_channel or "").strip() or None,
                        },
                        dedupe_key=f"rfp_upload_completed:{job_id}:{existing_rfp_id}",
                    )
                    return
                else:
                    try:
                        reset_stale_mapping(
                            sha256=sha,
                            s3_key=key,
                            reason=f"stale dedup mapping: rfpId {existing_rfp_id} not found",
                        )
                    except Exception:
                        pass
            except Exception:
                # If anything goes wrong with validation, keep going and attempt a fresh create.
                pass

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
            enqueue_event(
                event_type="slack.rfp_upload_failed",
                payload={"jobId": job_id, "fileName": file_name, "error": "Uploaded object is empty"},
                dedupe_key=f"rfp_upload_failed:{job_id}",
            )
            return

        sha_actual = hashlib.sha256(data).hexdigest()
        if sha_actual != sha:
            # Don't poison de-dupe state with mismatched content; mark failed and allow retry.
            try:
                from app.repositories.rfp_pdf_dedup_repo import mark_failed

                mark_failed(sha256=sha, error="sha256 mismatch between claimed hash and uploaded object")
            except Exception:
                pass

            update_job(
                job_id=job_id,
                updates_obj={
                    "status": "failed",
                    "error": "sha256 mismatch between claimed hash and uploaded object",
                    "finishedAt": now_iso(),
                    "updatedAt": now_iso(),
                },
            )
            enqueue_event(
                event_type="slack.rfp_upload_failed",
                payload={
                    "jobId": job_id,
                    "fileName": file_name,
                    "error": "sha256 mismatch between claimed hash and uploaded object",
                },
                dedupe_key=f"rfp_upload_failed:{job_id}",
            )
            return

        # Ensure the de-dupe record exists before attempting the transactional completion.
        try:
            ensure_record(sha256=sha, s3_key=key)
        except Exception:
            pass

        analysis = analyze_rfp(data, file_name)

        # Create the RFP using create_rfp_from_analysis which handles Drive folder creation and PDF upload
        saved = create_rfp_from_analysis(
            analysis=analysis,
            source_file_name=file_name,
            source_file_size=len(data),
            source_pdf_data=data,
            source_s3_key=key,
        )
        rfp_id = str(saved.get("_id") or saved.get("rfpId") or "").strip()
        
        if not rfp_id:
            raise ValueError("RFP created but no ID returned")

        # Transactionally: mark this sha256 as completed (RFP already created above)
        t = get_main_table()
        try:
            t.transact_write(
                updates=[
                    t.tx_update(
                        key=dedup_key(sha),
                        update_expression=(
                            "SET #s = :s, rfpId = :r, s3Key = :k, sha256 = :h, entityType = :et, "
                            "createdAt = if_not_exists(createdAt, :c), updatedAt = :u"
                        ),
                        expression_attribute_names={"#s": "status"},
                        expression_attribute_values={
                            ":s": "completed",
                            ":r": rfp_id,
                            ":k": key,
                            ":h": sha,
                            ":et": "RfpPdfDedup",
                            ":c": now_iso(),
                            ":u": now_iso(),
                        },
                        condition_expression="attribute_not_exists(rfpId)",
                    )
                ],
            )
        except DdbConflict:
            # Another worker won the race; load the canonical rfpId.
            dup = get_by_sha256(sha) or {}
            existing_rfp_id = str(dup.get("rfpId") or "").strip()
            if existing_rfp_id:
                rfp_id = existing_rfp_id
            else:
                raise

        # Persist the source PDF reference on the RFP so it can be viewed later.
        try:
            if rfp_id and key:
                update_rfp(
                    rfp_id,
                    {
                        "sourceS3Key": key,
                        "sourceS3Uri": to_s3_uri(
                            bucket=get_assets_bucket_name(),
                            key=key,
                        ),
                    },
                )
        except Exception:
            # Best-effort only; do not fail the upload job if this metadata update fails.
            pass

        # Best-effort: generate AI section titles immediately so the RFP page
        # can offer AI proposal scaffolding without another round trip.
        try:
            rfp_for_titles = saved if saved else (get_rfp_by_id(rfp_id) or {})
            titles = generate_section_titles(rfp_for_titles)
            if titles:
                update_rfp(rfp_id, {"sectionTitles": titles})
        except Exception:
            # Do not fail the upload job if AI generation errors.
            pass

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
        enqueue_event(
            event_type="slack.rfp_upload_completed",
            payload={
                "jobId": job_id,
                "rfpId": rfp_id,
                "fileName": file_name,
                "channel": str(settings.slack_rfp_machine_channel or "").strip() or None,
            },
            dedupe_key=f"rfp_upload_completed:{job_id}:{rfp_id}",
        )
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
        enqueue_event(
            event_type="slack.rfp_upload_failed",
            payload={
                "jobId": job_id,
                "fileName": str(job.get("fileName") or "").strip() or file_name,
                "error": str(e) or "Failed to process RFP",
                "channel": str(settings.slack_rfp_machine_channel or "").strip() or None,
            },
            dedupe_key=f"rfp_upload_failed:{job_id}",
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


@router.get("/{id}/", include_in_schema=False)
def get_one_slash(id: str):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return get_one(id)


@router.get("/{id}/drive-folder")
def get_drive_folder(id: str):
    """
    Get Google Drive folder information for an RFP.
    
    Returns the root folder URL and folder structure.
    """
    # Minimal mode: do not attempt Drive folder automation.
    return {"ok": False, "error": "drive_folder_automation_pruned", "folderUrl": None}


@router.get("/{id}/drive-folder/", include_in_schema=False)
def get_drive_folder_slash(id: str):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return get_drive_folder(id)


@router.get("/{id}/source-pdf/presign")
def presign_source_pdf(id: str):
    """
    Return a short-lived signed URL for the originally uploaded RFP PDF (if present).
    """
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    key = str(rfp.get("sourceS3Key") or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="No source PDF stored for this RFP")

    signed = presign_get_object(key=key, expires_in=3600)
    return {
        "ok": True,
        "url": signed.get("url"),
        "bucket": signed.get("bucket"),
        "key": signed.get("key"),
        "expiresInSeconds": 3600,
    }


@router.get("/{id}/source-pdf/presign/", include_in_schema=False)
def presign_source_pdf_slash(id: str):
    return presign_source_pdf(id)


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


@router.post("/{id}/ai-section-titles/", include_in_schema=False)
def ai_section_titles_slash(id: str):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return ai_section_titles(id)


@router.post("/{id}/ai-reanalyze")
def ai_reanalyze(id: str):
    """
    Re-run RFP analysis using the stored rawText (and AI if configured).
    Updates the RFP fields in-place and returns the updated record.
    """
    try:
        rfp = get_rfp_by_id(id)
        if not rfp:
            raise HTTPException(status_code=404, detail="RFP not found")

        raw_text = str(rfp.get("rawText") or "").strip()
        if not raw_text:
            raise HTTPException(
                status_code=409,
                detail="RFP has no rawText to re-analyze (re-upload required)",
            )

        source_name = str(rfp.get("fileName") or rfp.get("title") or "rfp").strip()
        analysis = analyze_rfp(raw_text, source_name)

        # Overwrite only the analysis-derived fields (plus AI artifacts).
        updated = update_rfp(id, analysis)
        if not updated:
            raise HTTPException(status_code=404, detail="RFP not found")

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"error": "Failed to re-analyze RFP", "message": str(e)}
        )


@router.post("/{id}/ai-reanalyze/", include_in_schema=False)
def ai_reanalyze_slash(id: str):
    return ai_reanalyze(id)


@router.get("/{id}/ai-refresh/stream")
def ai_refresh_stream(id: str):
    """
    Stream incremental AI extraction updates over SSE.

    Events:
      - meta | dates | lists: { bucket, updates, meta }
      - done: { ok: true, rfp }
      - error: { ok: false, error }
    """
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    raw_text = str(rfp.get("rawText") or "").strip()
    if not raw_text:
        raise HTTPException(
            status_code=409,
            detail="RFP has no rawText to refresh (re-upload required)",
        )

    source_name = str(rfp.get("fileName") or rfp.get("title") or "rfp").strip()
    text_clip = clip_text(raw_text, max_chars=200000)

    def sse(event: str, data: dict[str, Any]) -> bytes:
        return (
            f"event: {event}\n"
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        ).encode("utf-8")

    def _prompt_meta() -> str:
        return (
            "Extract basic RFP metadata from the text.\n"
            "Take time to reason step-by-step and cross-check the text, then output ONLY the JSON.\n"
            "Return JSON ONLY (no markdown):\n"
            "{"
            '"title": string, '
            '"clientName": string, '
            '"projectType": string, '
            '"budgetRange": string, '
            '"location": string, '
            '"contactInformation": string'
            "}\n\n"
            f"SOURCE_NAME: {source_name}\n\n"
            f"RFP_TEXT:\n{text_clip}"
        )

    def _prompt_dates() -> str:
        return (
            "Extract the key RFP dates.\n"
            "Use 'Not available' if unknown. Prefer MM/DD/YYYY when possible.\n"
            "Take time to reason step-by-step and cross-check the text, then output ONLY the JSON.\n"
            "Return JSON ONLY:\n"
            "{"
            '"submissionDeadline": string, '
            '"questionsDeadline": string, '
            '"bidMeetingDate": string, '
            '"bidRegistrationDate": string, '
            '"projectDeadline": string'
            "}\n\n"
            f"RFP_TEXT:\n{text_clip}"
        )

    def _prompt_lists() -> str:
        return (
            "Extract lists from the RFP.\n"
            "Take time to reason step-by-step and cross-check the text, then output ONLY the JSON.\n"
            "Return JSON ONLY:\n"
            "{"
            '"keyRequirements": string[], '
            '"deliverables": string[], '
            '"criticalInformation": string[], '
            '"timeline": string[], '
            '"clarificationQuestions": string[]'
            "}\n\n"
            f"RFP_TEXT:\n{text_clip}"
        )

    def gen() -> Iterator[bytes]:
        # Initial hello
        yield sse("hello", {"ok": True, "rfpId": id})

        jobs = [
            ("meta", "rfp_analysis_meta", RfpMetaAI, _prompt_meta(), 800),
            ("dates", "rfp_analysis_dates", RfpDatesAI, _prompt_dates(), 600),
            ("lists", "rfp_analysis_lists", RfpListsAI, _prompt_lists(), 1400),
        ]

        def _call(purpose: str, model_cls: type, prompt: str, max_tokens: int) -> tuple[Any, Any]:
            parsed: Any
            meta: Any
            parsed, meta = call_json_verified(
                purpose=purpose,
                response_model=model_cls,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
                retries=2,
                fallback=None,
            )
            return parsed, meta

        fields_meta: list[dict[str, Any]] = []
        buckets_ok = 0

        try:
            with ThreadPoolExecutor(max_workers=3) as ex:
                fut_map = {
                    ex.submit(_call, purpose, model_cls, prmpt, mt): (bucket, purpose)
                    for (bucket, purpose, model_cls, prmpt, mt) in jobs
                }
                for fut in as_completed(fut_map):
                    bucket, purpose = fut_map[fut]
                    try:
                        parsed, meta = fut.result()
                        updates = parsed.model_dump()

                        update_rfp(id, updates)
                        fields_meta.append(
                            {
                                "purpose": meta.purpose,
                                "model": meta.model,
                                "attempts": meta.attempts,
                                "responseFormat": meta.used_response_format,
                            }
                        )
                        buckets_ok += 1
                        yield sse(
                            bucket,
                            {
                                "ok": True,
                                "bucket": bucket,
                                "updates": updates,
                                "meta": {
                                    "purpose": meta.purpose,
                                    "model": meta.model,
                                    "attempts": meta.attempts,
                                    "responseFormat": meta.used_response_format,
                                },
                            },
                        )
                    except Exception as e:
                        fields_meta.append({"purpose": purpose, "error": str(e)[:200]})
                        yield sse(
                            "error",
                            {
                                "ok": False,
                                "bucket": bucket,
                                "error": str(e) or "bucket_failed",
                            },
                        )

            # If nothing succeeded, fall back to heuristic analysis (keeps UX usable).
            if buckets_ok == 0:
                try:
                    analysis = analyze_rfp(raw_text, source_name)
                    update_rfp(id, analysis)
                    yield sse(
                        "warning",
                        {
                            "ok": True,
                            "warning": "AI unavailable; used heuristic extraction instead.",
                        },
                    )
                except Exception as e:
                    yield sse(
                        "error",
                        {
                            "ok": False,
                            "error": str(e) or "fallback_failed",
                        },
                    )

            # Attach bucket execution metadata (best-effort)
            try:
                update_rfp(
                    id,
                    {
                        "_analysis": {
                            "version": 2,
                            "usedAi": bool(buckets_ok > 0),
                            "model": settings.openai_model_for("rfp_analysis"),
                            "sourceName": source_name,
                            "extractedChars": len(raw_text),
                            "ts": int(time.time()),
                            "fields": fields_meta[:20],
                        }
                    },
                )
            except Exception:
                pass

            final = get_rfp_by_id(id) or {}
            yield sse("done", {"ok": True, "rfp": final})
        except AiNotConfigured as e:
            # Keep the UI responsive and avoid leaving it hanging.
            try:
                analysis = analyze_rfp(raw_text, source_name)
                update_rfp(id, analysis)
            except Exception:
                pass
            yield sse("error", {"ok": False, "error": str(e)})
        except AiError as e:
            yield sse("error", {"ok": False, "error": str(e) or "ai_failed"})
        except Exception as e:
            yield sse("error", {"ok": False, "error": str(e) or "stream_failed"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # helpful behind some proxies
        },
    )


@router.get("/{id}/ai-summary/stream")
def ai_summary_stream(id: str):
    """
    Stream an AI summary (token-by-token) over SSE and persist it to the RFP.
    """
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    raw_text = str(rfp.get("rawText") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=409, detail="RFP has no rawText")

    source_name = str(rfp.get("fileName") or rfp.get("title") or "rfp").strip()
    text_clip = clip_text(raw_text, max_chars=120000)

    def sse(event: str, data: dict[str, Any]) -> bytes:
        return (
            f"event: {event}\n"
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        ).encode("utf-8")

    def gen() -> Iterator[bytes]:
        yield sse("hello", {"ok": True, "rfpId": id})
        prompt = (
            "Write a concise, skimmable summary of this RFP for internal triage.\n"
            "Include:\n"
            "- What it is\n"
            "- Key requirements (bullets)\n"
            "- Deadlines and budget (if present)\n"
            "- Open questions / risks\n\n"
            "Use markdown.\n\n"
            f"SOURCE_NAME: {source_name}\n\n"
            f"RFP_TEXT:\n{text_clip}"
        )

        try:
            # Prefer GPT-5.2 Responses API path (non-stream) and stream deltas ourselves.
            full, meta = call_text_verified(
                purpose="generate_content",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.3,
                timeout_s=120,
                retries=2,
            )
            full = (full or "").strip()
            if full:
                # Emit in small chunks so Slack/clients feel "streaming" without relying on
                # upstream token streaming semantics (which vary by model/API).
                step = 80
                for i in range(0, len(full), step):
                    yield sse("delta", {"text": full[i : i + step]})
            if full:
                try:
                    update_rfp(id, {"aiSummary": full, "aiSummaryUpdatedAt": now_iso()})
                except Exception:
                    pass
            yield sse("done", {"ok": True, "meta": meta.__dict__, "aiSummary": full})
        except AiNotConfigured as e:
            yield sse("error", {"ok": False, "error": str(e)})
        except Exception as e:
            yield sse("error", {"ok": False, "error": str(e) or "ai_summary_failed"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{id}/ai-section-summary")
def ai_section_summary(id: str, body: dict = Body(...)):
    """
    Generate (and persist) a short, section-specific AI summary based on the stored rawText.

    Body:
      - sectionId: string (required)
      - topic: string (optional; defaults to sectionId)
      - force: boolean (optional; if true, regenerate even if cached)
    """
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    b = body or {}
    section_id = str(b.get("sectionId") or "").strip()
    if not section_id:
        raise HTTPException(status_code=400, detail="sectionId is required")
    if len(section_id) > 80:
        raise HTTPException(status_code=400, detail="sectionId is too long")

    topic = str(b.get("topic") or section_id).strip()
    if len(topic) > 200:
        topic = topic[:200]

    force = bool(b.get("force") or False)

    existing = rfp.get("aiSectionSummaries")
    existing_map: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    cached = existing_map.get(section_id) if isinstance(existing_map, dict) else None
    if not force and isinstance(cached, dict) and str(cached.get("text") or "").strip():
        return {
            "ok": True,
            "sectionId": section_id,
            "topic": str(cached.get("topic") or topic),
            "summary": str(cached.get("text") or "").strip(),
            "updatedAt": cached.get("updatedAt"),
            "cached": True,
        }

    raw_text = str(rfp.get("rawText") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=409, detail="RFP has no rawText")

    # Keep prompt sizes bounded and deterministic.
    text_clip = clip_text(raw_text, max_chars=120000)
    title = str(rfp.get("title") or "").strip()
    client = str(rfp.get("clientName") or "").strip()
    submission_deadline = str(rfp.get("submissionDeadline") or "").strip()
    questions_deadline = str(rfp.get("questionsDeadline") or "").strip()
    budget = str(rfp.get("budgetRange") or "").strip()
    project_type = str(rfp.get("projectType") or "").strip()

    system_prompt = (
        "You are an expert RFP analyst. "
        "Write a short, specific summary for the given TOPIC using only the provided RFP text. "
        "If the RFP text does not mention the topic, explicitly say it is not specified in the RFP text. "
        "Return plain text only (no markdown, no bullets)."
    )
    user_prompt = (
        f"TOPIC: {topic}\n\n"
        "CONSTRAINTS:\n"
        "- 2 to 4 sentences\n"
        "- Max ~80 words\n"
        "- Plain text only\n"
        "- No speculation; use 'Not specified in the RFP text.' when missing\n\n"
        "RFP_META:\n"
        f"- Title: {title or '—'}\n"
        f"- Client: {client or '—'}\n"
        f"- Project type: {project_type or '—'}\n"
        f"- Budget: {budget or '—'}\n"
        f"- Submission deadline: {submission_deadline or '—'}\n"
        f"- Questions deadline: {questions_deadline or '—'}\n\n"
        f"RFP_TEXT:\n{text_clip}"
    )

    try:
        summary, meta = call_text_verified(
            purpose="rfp_section_summary",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=220,
            temperature=0.2,
            retries=2,
        )
        summary = str(summary or "").strip()
        if not summary:
            raise HTTPException(status_code=502, detail="AI returned empty summary")

        now = now_iso()
        next_map = dict(existing_map)
        next_map[section_id] = {
            "text": summary,
            "topic": topic,
            "updatedAt": now,
            "model": meta.model,
            "purpose": meta.purpose,
        }
        try:
            update_rfp(id, {"aiSectionSummaries": next_map})
        except Exception:
            # Best-effort: don't fail the request if persistence errors.
            pass

        return {
            "ok": True,
            "sectionId": section_id,
            "topic": topic,
            "summary": summary,
            "updatedAt": now,
            "cached": False,
            "meta": {
                "purpose": meta.purpose,
                "model": meta.model,
                "attempts": meta.attempts,
            },
        }
    except HTTPException:
        raise
    except AiNotConfigured:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")
    except AiUpstreamError as e:
        raise HTTPException(status_code=502, detail={"error": "AI upstream failure", "details": str(e)})
    except AiError as e:
        raise HTTPException(status_code=502, detail={"error": "AI failure", "details": str(e)})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to generate section summary", "details": str(e)},
        )


@router.post("/{id}/ai-section-summary/", include_in_schema=False)
def ai_section_summary_slash(id: str, body: dict = Body(...)):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return ai_section_summary(id=id, body=body)


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


@router.put("/{id}/", include_in_schema=False)
def update_one_slash(id: str, body: dict):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return update_one(id, body)


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
      - assignedReviewerUserSub: string (optional) - user sub to assign review to
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

    if "assignedReviewerUserSub" in b:
        reviewer_sub = str(b.get("assignedReviewerUserSub") or "").strip()
        if reviewer_sub:
            base_review["assignedReviewerUserSub"] = reviewer_sub
        else:
            # Empty string means unassign
            base_review.pop("assignedReviewerUserSub", None)

    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip() if user else ""

    review: dict[str, Any] = dict(base_review)
    review["updatedAt"] = now_iso()
    if user_sub:
        review["updatedBy"] = user_sub

    updated = update_rfp(id, {"review": review})
    if not updated:
        raise HTTPException(status_code=404, detail="RFP not found")

    # Best-effort: sync workflow stage + seed tasks.
    try:
        proposals = list_rfp_proposal_summaries(id)
        proposal_id: str | None = None
        try:
            if proposals:
                p = sorted(proposals, key=lambda x: str(x.get("updatedAt") or ""), reverse=True)[0]
                proposal_id = str(p.get("proposalId") or "").strip() or None
        except Exception:
            proposal_id = None
        user = getattr(getattr(request, "state", None), "user", None)
        actor_sub = str(getattr(user, "sub", "") or "").strip() if user else ""
        sync_for_rfp(rfp_id=id, actor_user_sub=actor_sub or None, proposal_id=proposal_id)
    except Exception:
        pass

    # Keep compatibility with frontend expecting embedded attachments.
    try:
        out = dict(updated)
        out["attachments"] = list_attachments(id)
        return out
    except Exception:
        out = dict(updated)
        out["attachments"] = []
        return out


@router.put("/{id}/review/", include_in_schema=False)
def update_review_slash(id: str, request: Request, body: dict = Body(...)):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return update_review(id=id, request=request, body=body)


@router.get("/{id}/opportunity-state")
def get_opportunity_state(id: str):
    """
    Get the durable OpportunityState for this RFP (tracker/owners/dueDates/etc).
    """
    rid = str(id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="id is required")
    ensure_state_exists(rfp_id=rid)
    st = get_state(rfp_id=rid)
    if not st:
        raise HTTPException(status_code=404, detail="OpportunityState not found")
    return {"ok": True, "state": st}


@router.put("/{id}/opportunity-state")
def put_opportunity_state(id: str, request: Request, body: dict = Body(...)):
    """
    Patch OpportunityState.state (shallow merge with safe semantics).
    Body is a patch applied to the `state` object (see rfp_opportunity_state_repo.patch_state).
    """
    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip() if user else None

    rid = str(id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="id is required")
    patch = body if isinstance(body, dict) else {}
    ensure_state_exists(rfp_id=rid)
    updated = patch_state(rfp_id=rid, patch=patch, updated_by_user_sub=user_sub or None, create_snapshot=True)
    return {"ok": True, "state": updated}


@router.put("/{id}/opportunity-state/", include_in_schema=False)
def put_opportunity_state_slash(id: str, request: Request, body: dict = Body(...)):
    return put_opportunity_state(id=id, request=request, body=body)


@router.get("/{id}/proposals")
def proposals_for_rfp(id: str):
    try:
        proposals = list_rfp_proposal_summaries(id)
        return {"data": proposals}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch RFP proposals")


@router.get("/{id}/proposals/", include_in_schema=False)
def proposals_for_rfp_slash(id: str):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return proposals_for_rfp(id)


@router.delete("/{id}")
def delete_one(id: str):
    try:
        delete_rfp(id)
        return {"message": "RFP deleted successfully"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete RFP")


@router.delete("/{id}/", include_in_schema=False)
def delete_one_slash(id: str):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return delete_one(id)


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


@router.post("/{id}/buyer-profiles/remove/", include_in_schema=False)
def remove_buyer_profiles_slash(id: str, body: dict = Body(...)):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return remove_buyer_profiles(id=id, body=body)


# --- RFP Scraper Endpoints ---


@router.get("/scrapers/sources")
def list_scraper_sources(request: Request, refresh: bool = False, debug: bool = False):
    """Get list of available RFP scraper sources."""
    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip() if user else None
    sources = get_available_sources(user_sub=user_sub, force_refresh=bool(refresh))
    try:
        # Diagnostic logging: why are sources unavailable?
        rid = getattr(getattr(request, "state", None), "request_id", None)
        unavailable = [s for s in sources if not bool(s.get("available"))]
        available_count = len(sources) - len(unavailable)
        reason_counts: dict[str, int] = {}
        examples: dict[str, list[str]] = {}
        for s in unavailable:
            sid = str(s.get("id") or "").strip() or "unknown"
            reason = str(s.get("unavailableReason") or "").strip() or "unknown"
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if debug:
                examples.setdefault(reason, [])
                if len(examples[reason]) < 10:
                    examples[reason].append(sid)

        # Log more loudly when explicitly requested or in dev, otherwise keep it quiet.
        if debug or refresh or settings.is_development:
            log.info(
                "scraper_sources_listed",
                request_id=str(rid) if rid else None,
                user_sub=user_sub or None,
                total=len(sources),
                available=available_count,
                unavailable=len(unavailable),
                unavailable_reasons=reason_counts,
                unavailable_examples=examples if debug else None,
            )
        else:
            log.debug(
                "scraper_sources_listed",
                request_id=str(rid) if rid else None,
                user_sub=user_sub or None,
                total=len(sources),
                available=available_count,
                unavailable=len(unavailable),
                unavailable_reasons=reason_counts,
            )
    except Exception:
        # Never break the endpoint due to logging.
        pass
    return {"ok": True, "sources": sources}


@router.get("/scrapers/sources/", include_in_schema=False)
def list_scraper_sources_slash(request: Request, refresh: bool = False, debug: bool = False):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return list_scraper_sources(request=request, refresh=refresh, debug=debug)


@router.post("/scrapers/run", status_code=201)
def run_scraper(request: Request, background_tasks: BackgroundTasks, body: dict = Body(...)):
    """
    Trigger a scraper job for a given source.
    
    Body:
      - source: string (required) - source ID (e.g., "planning.org")
      - searchParams: object (optional) - source-specific search parameters
    """
    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip() if user else None

    source = str((body or {}).get("source") or "").strip()
    if not source:
        raise HTTPException(status_code=400, detail="source is required")

    ok, reason = is_source_available_for_user(source, user_sub=user_sub)
    if not ok:
        try:
            rid = getattr(getattr(request, "state", None), "request_id", None)
            log.info(
                "scraper_run_blocked",
                request_id=str(rid) if rid else None,
                user_sub=user_sub or None,
                source=source,
                reason=reason or None,
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail=f"Scraper not available for source: {source}" + (f" ({reason})" if reason else ""),
        )

    search_params = (body or {}).get("searchParams")
    if not isinstance(search_params, dict):
        search_params = None

    job = create_scraper_job(source=source, search_params=search_params, user_sub=user_sub)
    background_tasks.add_task(process_scraper_job, job["id"])

    return {"ok": True, "job": job}


@router.get("/scrapers/jobs")
def list_scraper_jobs_endpoint(
    source: str | None = None,
    status: str | None = None,
    limit: int = 50,
    nextToken: str | None = None,
):
    """List scraper jobs."""
    try:
        if not source:
            raise HTTPException(status_code=400, detail="source parameter is required")
        res = list_scraper_jobs(source=source, status=status, limit=limit, next_token=nextToken)
        return {"ok": True, "jobs": res.get("data") or [], "nextToken": res.get("nextToken")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("list_scraper_jobs_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list scraper jobs")


@router.get("/scrapers/jobs/", include_in_schema=False)
def list_scraper_jobs_endpoint_slash(
    source: str | None = None,
    status: str | None = None,
    limit: int = 50,
    nextToken: str | None = None,
):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return list_scraper_jobs_endpoint(source=source, status=status, limit=limit, nextToken=nextToken)


@router.get("/scrapers/jobs/{jobId}")
def get_scraper_job_endpoint(jobId: str):
    """Get a specific scraper job."""
    job = get_scraper_job(jobId)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": job}


@router.get("/scrapers/candidates")
def list_scraped_candidates(
    source: str,
    status: str | None = None,
    limit: int = 50,
    nextToken: str | None = None,
):
    """List scraped RFP candidates."""
    try:
        res = list_scraped_rfps(source=source, status=status, limit=limit, next_token=nextToken)
        return {"ok": True, "candidates": res.get("data") or [], "nextToken": res.get("nextToken")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("list_scraped_candidates_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list scraped candidates")


@router.get("/scrapers/candidates/", include_in_schema=False)
def list_scraped_candidates_slash(
    source: str,
    status: str | None = None,
    limit: int = 50,
    nextToken: str | None = None,
):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return list_scraped_candidates(source=source, status=status, limit=limit, nextToken=nextToken)


@router.get("/scrapers/candidates/{candidateId}")
def get_scraped_candidate(candidateId: str):
    """Get a specific scraped RFP candidate."""
    candidate = get_scraped_rfp_by_id(candidateId)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "candidate": candidate}


@router.post("/scrapers/candidates/{candidateId}/import", status_code=201)
def import_scraped_candidate(candidateId: str, background_tasks: BackgroundTasks):
    """
    Import a scraped RFP candidate by analyzing its detail URL and creating an RFP.
    """
    candidate = get_scraped_rfp_by_id(candidateId)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    status = str(candidate.get("status") or "").strip().lower()
    if status == "imported":
        raise HTTPException(status_code=409, detail="Candidate already imported")
    if status == "failed":
        raise HTTPException(status_code=409, detail="Candidate import previously failed")

    detail_url = str(candidate.get("detailUrl") or "").strip()
    if not detail_url:
        raise HTTPException(status_code=400, detail="Candidate has no detail URL")

    # Use analyze_url endpoint logic to create the RFP
    try:
        analysis = analyze_rfp(detail_url, detail_url)
        saved = create_rfp_from_analysis(
            analysis=analysis,
            source_file_name=f"scraped_{candidate.get('source', 'unknown')}_{int(__import__('time').time()*1000)}",
            source_file_size=0,
        )
        rfp_id = str(saved.get("_id") or saved.get("rfpId") or "").strip()

        # Mark candidate as imported
        mark_scraped_rfp_imported(candidateId, rfp_id)
        try:
            rfp_intake_queue_repo.update_status(candidate_id=candidateId, status="imported")
        except Exception:
            pass

        return {"ok": True, "rfp": saved, "candidateId": candidateId}
    except Exception as e:
        log.exception("import_scraped_candidate_failed", candidateId=candidateId, error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to import candidate", "message": str(e)},
        )


@router.post("/scrapers/candidates/{candidateId}/skip", status_code=200)
def skip_scraped_candidate(candidateId: str):
    """Skip a scraped candidate (removes it from the pending intake queue)."""
    candidate = get_scraped_rfp_by_id(candidateId)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    updated = update_scraped_rfp(candidateId, {"status": "skipped"})
    try:
        rfp_intake_queue_repo.update_status(candidate_id=candidateId, status="skipped")
    except Exception:
        pass
    return {"ok": True, "candidate": updated}


@router.post("/scrapers/candidates/{candidateId}/unskip", status_code=200)
def unskip_scraped_candidate(candidateId: str):
    """Move a skipped candidate back to pending."""
    candidate = get_scraped_rfp_by_id(candidateId)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    updated = update_scraped_rfp(candidateId, {"status": "pending"})
    try:
        rfp_intake_queue_repo.update_status(candidate_id=candidateId, status="pending")
    except Exception:
        pass
    return {"ok": True, "candidate": updated}


@router.get("/scrapers/intake")
def list_intake_queue(status: str | None = None, limit: int = 50, nextToken: str | None = None):
    """List intake queue items across all sources."""
    st = str(status or "pending").strip().lower()
    try:
        res = rfp_intake_queue_repo.list_intake(status=st, limit=limit, next_token=nextToken)  # type: ignore[arg-type]
        return {"ok": True, "items": res.get("data") or [], "nextToken": res.get("nextToken")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("list_intake_queue_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list intake queue")


@router.get("/scrapers/intake/", include_in_schema=False)
def list_intake_queue_slash(status: str | None = None, limit: int = 50, nextToken: str | None = None):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return list_intake_queue(status=status, limit=limit, nextToken=nextToken)


@router.get("/scrapers/schedules")
def list_scraper_schedules(limit: int = 100, nextToken: str | None = None):
    try:
        res = rfp_scraper_schedules_repo.list_schedules(limit=limit, next_token=nextToken)
        return {"ok": True, "schedules": res.get("data") or [], "nextToken": res.get("nextToken")}
    except Exception as e:
        log.exception("list_scraper_schedules_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list scraper schedules")


@router.get("/scrapers/schedules/", include_in_schema=False)
def list_scraper_schedules_slash(limit: int = 100, nextToken: str | None = None):
    # Accept trailing slash to avoid 404s when clients normalize URLs.
    return list_scraper_schedules(limit=limit, nextToken=nextToken)


@router.post("/scrapers/schedules", status_code=201)
def create_scraper_schedule(request: Request, body: dict = Body(...)):
    user = getattr(getattr(request, "state", None), "user", None)
    user_sub = str(getattr(user, "sub", "") or "").strip() if user else None

    name = str((body or {}).get("name") or "").strip() or None
    source = str((body or {}).get("source") or "").strip()
    if not source:
        raise HTTPException(status_code=400, detail="source is required")
    ok, reason = is_source_available_for_user(source, user_sub=user_sub)
    if not ok:
        try:
            rid = getattr(getattr(request, "state", None), "request_id", None)
            log.info(
                "scraper_schedule_create_blocked",
                request_id=str(rid) if rid else None,
                user_sub=user_sub or None,
                source=source,
                reason=reason or None,
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail=f"Scraper not available for source: {source}" + (f" ({reason})" if reason else ""),
        )

    frequency = str((body or {}).get("frequency") or "daily").strip().lower()
    if frequency != "daily":
        raise HTTPException(status_code=400, detail="Only daily schedules are supported")
    enabled = bool((body or {}).get("enabled", True))
    search_params = (body or {}).get("searchParams")
    if not isinstance(search_params, dict):
        search_params = {}

    sched = rfp_scraper_schedules_repo.create_schedule(
        name=name,
        source=source,
        frequency="daily",
        enabled=enabled,
        search_params=search_params,
        created_by_user_sub=user_sub,
    )
    return {"ok": True, "schedule": sched}


@router.put("/scrapers/schedules/{scheduleId}")
def update_scraper_schedule(scheduleId: str, body: dict = Body(...)):
    try:
        updated = rfp_scraper_schedules_repo.update_schedule(schedule_id=scheduleId, updates_obj=body or {})
        if not updated:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return {"ok": True, "schedule": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("update_scraper_schedule_failed", scheduleId=scheduleId, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update schedule")


@router.post("/scrapers/schedules/{scheduleId}/run", status_code=201)
def run_scraper_schedule_now(scheduleId: str, background_tasks: BackgroundTasks):
    sched = rfp_scraper_schedules_repo.get_schedule(schedule_id=scheduleId)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    source = str(sched.get("source") or "").strip()
    if not source or not is_source_available(source):
        raise HTTPException(status_code=400, detail=f"Scraper not available for source: {source}")
    search_params = sched.get("searchParams") if isinstance(sched.get("searchParams"), dict) else None
    job = create_scraper_job(source=source, search_params=search_params, user_sub=None)
    background_tasks.add_task(process_scraper_job, job["id"])
    try:
        # Optionally bump nextRunAt forward since it was run manually.
        rfp_scraper_schedules_repo.mark_ran(schedule_id=scheduleId)
    except Exception:
        pass
    return {"ok": True, "job": job, "scheduleId": scheduleId}


 
