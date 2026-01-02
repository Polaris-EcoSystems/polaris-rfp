from __future__ import annotations

import hashlib
import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from app.repositories.contracting_repo import (
    add_supporting_doc,
    create_client_package,
    create_esign_envelope,
    get_case_by_id,
    get_case_by_proposal_id,
    get_budget_version,
    get_contract_doc_version,
    list_budget_versions,
    list_client_packages,
    list_contract_doc_versions,
    list_esign_envelopes,
    get_esign_envelope,
    list_supporting_docs,
    publish_client_package,
    rotate_client_package_token,
    revoke_client_package,
    update_case,
)
from app.pipeline.contracting.contracting_schemas import validate_key_terms
from app.pipeline.contracting.contracting_docgen import generate_budget_xlsx as _generate_budget_xlsx
from app.pipeline.contracting.contracting_docgen import render_contract_docx as _render_contract_docx
from app.infrastructure.integrations.esign_service import mark_signed as _esign_mark_signed
from app.infrastructure.integrations.esign_service import send_envelope as _esign_send
from app.repositories.contracting_jobs_repo import create_job as create_contracting_job
from app.repositories.contracting_jobs_repo import get_job as get_contracting_job
from app.repositories.contracting_jobs_repo import list_jobs_for_case
from app.pipeline.contracting.contracting_queue import enqueue_contracting_job
from app.infrastructure.storage.s3_assets import presign_get_object, presign_put_object


router = APIRouter(tags=["contracting"])


def _user_sub(request: Request) -> str | None:
    u = getattr(getattr(request, "state", None), "user", None)
    sub = str(getattr(u, "sub", "") or "").strip() if u else ""
    return sub or None


def _iso_or_none(v: Any) -> str | None:
    s = str(v or "").strip()
    if not s:
        return None
    # accept already-iso-ish; hard validation happens elsewhere
    return s


def _safe_file_name(name: str) -> str:
    n = str(name or "").strip() or "document"
    n = re.sub(r"[^a-zA-Z0-9._ -]", "_", n)[:160]
    return n


def _supporting_doc_key(case_id: str, doc_id: str, file_name: str) -> str:
    ext = ""
    m = re.search(r"\.([a-zA-Z0-9]{1,10})$", str(file_name or "").strip())
    if m:
        ext = f".{m.group(1).lower()}"
    safe_doc = re.sub(r"[^a-zA-Z0-9_-]", "_", str(doc_id).strip())[:120]
    return f"contracting/{str(case_id).strip()}/supporting/{safe_doc}{ext}"


def _stable_file_id(prefix: str, s3_key: str) -> str:
    raw = f"{prefix}:{str(s3_key).strip()}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # stable id for portal file routing
    return f"f_{h[:18]}"


@router.get("/contracting/by-proposal/{proposalId}")
def get_by_proposal(proposalId: str):
    c = get_case_by_proposal_id(proposalId)
    if not c:
        raise HTTPException(status_code=404, detail="Contracting case not found")
    return {"ok": True, "case": c}


@router.get("/contracting/{caseId}")
def get_case(caseId: str):
    c = get_case_by_id(caseId)
    if not c:
        raise HTTPException(status_code=404, detail="Contracting case not found")
    return {"ok": True, "case": c}


@router.put("/contracting/{caseId}")
def update_one_case(request: Request, caseId: str, body: dict = Body(default_factory=dict)):
    patch = dict(body or {})
    # Schema-driven key terms validation (advanced JSON is stored separately).
    if "keyTerms" in patch or "keyTermsRawJson" in patch:
        raw = patch.get("keyTermsRawJson") if "keyTermsRawJson" in patch else None
        src = raw if raw is not None else patch.get("keyTerms")
        norm, errs = validate_key_terms(src)
        if errs:
            raise HTTPException(status_code=400, detail={"message": "Invalid key terms", "errors": errs})
        patch["keyTerms"] = norm
        if raw is not None:
            patch["keyTermsRawJson"] = raw
    updated = update_case(caseId, patch or {}, updated_by_user_sub=_user_sub(request))
    if not updated:
        raise HTTPException(status_code=404, detail="Contracting case not found")
    return {"ok": True, "case": updated}


@router.get("/contracting/{caseId}/contract/versions")
def list_contract_versions(caseId: str, limit: int = 50):
    return {"ok": True, "data": list_contract_doc_versions(caseId, limit=limit)}


@router.get("/contracting/{caseId}/contract/versions/{versionId}/presign")
def presign_contract_version_download(caseId: str, versionId: str, expiresIn: int = 900):
    v = get_contract_doc_version(caseId, versionId)
    if not v:
        raise HTTPException(status_code=404, detail="Contract version not found")
    key = str((v or {}).get("docxS3Key") or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="Contract file unavailable")
    signed = presign_get_object(key=key, expires_in=max(60, min(3600, int(expiresIn or 900))))
    return {"ok": True, "url": signed.get("url"), "expiresIn": max(60, min(3600, int(expiresIn or 900)))}


@router.get("/contracting/{caseId}/budget/versions")
def list_budget(caseId: str, limit: int = 50):
    return {"ok": True, "data": list_budget_versions(caseId, limit=limit)}


@router.get("/contracting/{caseId}/budget/versions/{versionId}/presign")
def presign_budget_version_download(caseId: str, versionId: str, expiresIn: int = 900):
    v = get_budget_version(caseId, versionId)
    if not v:
        raise HTTPException(status_code=404, detail="Budget version not found")
    key = str((v or {}).get("xlsxS3Key") or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="Budget file unavailable")
    signed = presign_get_object(key=key, expires_in=max(60, min(3600, int(expiresIn or 900))))
    return {"ok": True, "url": signed.get("url"), "expiresIn": max(60, min(3600, int(expiresIn or 900)))}


@router.get("/contracting/{caseId}/supporting-docs")
def list_support_docs(caseId: str, limit: int = 200):
    return {"ok": True, "data": list_supporting_docs(caseId, limit=limit)}


@router.post("/contracting/{caseId}/supporting-docs/presign")
def presign_support_doc_upload(request: Request, caseId: str, body: dict = Body(default_factory=dict)):
    file_name = _safe_file_name(str((body or {}).get("fileName") or "document"))
    content_type = str((body or {}).get("contentType") or "").strip().lower() or "application/octet-stream"
    kind = str((body or {}).get("kind") or "").strip().lower() or "other"
    required = bool((body or {}).get("required") is True)
    expires_at = _iso_or_none((body or {}).get("expiresAt"))

    # Generate a doc id early so the key is stable between presign and commit.
    from app.repositories.contracting_repo import _new_id as _new  # keep repo API minimal

    doc_id = _new("support_doc")
    key = _supporting_doc_key(case_id=caseId, doc_id=doc_id, file_name=file_name)
    presigned = presign_put_object(key=key, content_type=content_type, expires_in=900)
    return {
        "ok": True,
        "caseId": str(caseId),
        "docId": doc_id,
        "kind": kind,
        "required": required,
        "expiresAt": expires_at,
        "fileName": file_name,
        "contentType": content_type,
        "bucket": presigned.get("bucket"),
        "key": presigned.get("key"),
        "putUrl": presigned.get("url"),
    }


@router.post("/contracting/{caseId}/supporting-docs/commit", status_code=201)
def commit_support_doc(request: Request, caseId: str, body: dict = Body(default_factory=dict)):
    doc_id = str((body or {}).get("docId") or "").strip()
    key = str((body or {}).get("key") or "").strip()
    kind = str((body or {}).get("kind") or "").strip().lower() or "other"
    required = bool((body or {}).get("required") is True)
    file_name = _safe_file_name(str((body or {}).get("fileName") or "document"))
    content_type = str((body or {}).get("contentType") or "").strip().lower() or "application/octet-stream"
    expires_at = _iso_or_none((body or {}).get("expiresAt"))

    if not doc_id:
        raise HTTPException(status_code=400, detail="docId is required")
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    if not str(key).startswith(f"contracting/{str(caseId).strip()}/supporting/"):
        raise HTTPException(status_code=400, detail="Invalid key for case")

    doc = add_supporting_doc(
        case_id=str(caseId),
        doc_id=doc_id,
        kind=kind,
        required=required,
        file_name=file_name,
        content_type=content_type,
        s3_key=key,
        expires_at=expires_at,
        uploaded_by_user_sub=_user_sub(request),
    )
    return {"ok": True, "doc": doc}


@router.get("/contracting/{caseId}/packages")
def list_packages(caseId: str, limit: int = 100):
    return {"ok": True, "data": list_client_packages(caseId, limit=limit)}


@router.post("/contracting/{caseId}/packages", status_code=201)
def create_package(request: Request, caseId: str, body: dict = Body(default_factory=dict)):
    name = str((body or {}).get("name") or "").strip() or None
    selected_files = (body or {}).get("selectedFiles")
    files_in = selected_files if isinstance(selected_files, list) else []
    normalized_files: list[dict[str, Any]] = []
    for f in files_in:
        if not isinstance(f, dict):
            continue
        s3_key = str(f.get("s3Key") or "").strip()
        if not s3_key:
            continue
        kind = str(f.get("kind") or "").strip().lower() or "file"
        file_id = str(f.get("id") or "").strip() or _stable_file_id(kind, s3_key)
        normalized_files.append(
            {
                "id": file_id,
                "kind": kind,
                "label": str(f.get("label") or f.get("fileName") or kind).strip() or kind,
                "fileName": _safe_file_name(str(f.get("fileName") or f.get("label") or kind)),
                "contentType": str(f.get("contentType") or "").strip().lower() or "application/octet-stream",
                "s3Key": s3_key,
            }
        )
    pkg = create_client_package(
        case_id=str(caseId),
        name=name,
        selected_files=normalized_files,
        created_by_user_sub=_user_sub(request),
    )
    return {"ok": True, "package": pkg}


@router.post("/contracting/{caseId}/packages/{packageId}/publish")
def publish_package(request: Request, caseId: str, packageId: str, body: dict = Body(default_factory=dict)):
    ttl_days = int((body or {}).get("ttlDays") or 7)
    ttl_days = max(1, min(30, ttl_days))
    out = publish_client_package(
        case_id=str(caseId),
        package_id=str(packageId),
        token_ttl_days=ttl_days,
        published_by_user_sub=_user_sub(request),
    )
    return {"ok": True, "package": {k: v for k, v in out.items() if k != "portalToken"}, "portalToken": out.get("portalToken")}


@router.post("/contracting/{caseId}/packages/{packageId}/rotate")
def rotate_package_token(request: Request, caseId: str, packageId: str, body: dict = Body(default_factory=dict)):
    ttl_days = int((body or {}).get("ttlDays") or 7)
    ttl_days = max(1, min(30, ttl_days))
    out = rotate_client_package_token(
        case_id=str(caseId),
        package_id=str(packageId),
        token_ttl_days=ttl_days,
        rotated_by_user_sub=_user_sub(request),
    )
    return {"ok": True, "package": {k: v for k, v in out.items() if k != "portalToken"}, "portalToken": out.get("portalToken")}


@router.post("/contracting/{caseId}/packages/{packageId}/zip")
def create_package_zip_job(request: Request, caseId: str, packageId: str, body: dict = Body(default_factory=dict)):
    """
    Optional: generate a zip bundle asynchronously via the contracting jobs worker.
    """
    idempotency_key = str((body or {}).get("idempotencyKey") or "").strip()
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="idempotencyKey is required")
    job = create_contracting_job(
        idempotency_key=idempotency_key,
        job_type="package_zip",
        case_id=str(caseId),
        proposal_id=None,
        requested_by_user_sub=_user_sub(request),
        payload={"caseId": str(caseId), "packageId": str(packageId)},
    )
    try:
        enqueue_contracting_job(job_id=str(job.get("jobId") or ""))
    except Exception:
        raise HTTPException(status_code=503, detail="Contracting worker queue is not configured")
    return {"ok": True, "job": get_contracting_job(str(job.get("jobId") or "")) or job}


@router.post("/contracting/{caseId}/packages/{packageId}/revoke")
def revoke_package(request: Request, caseId: str, packageId: str):
    out = revoke_client_package(case_id=str(caseId), package_id=str(packageId), revoked_by_user_sub=_user_sub(request))
    if not out:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"ok": True, "package": out}


@router.get("/contracting/{caseId}/esign/envelopes")
def list_envelopes(caseId: str, limit: int = 50):
    return {"ok": True, "data": list_esign_envelopes(caseId, limit=limit)}


@router.get("/contracting/{caseId}/esign/envelopes/{envelopeId}")
def get_envelope(caseId: str, envelopeId: str):
    env = get_esign_envelope(caseId, envelopeId)
    if not env:
        raise HTTPException(status_code=404, detail="Envelope not found")
    return {"ok": True, "envelope": env}


@router.post("/contracting/{caseId}/esign/envelopes", status_code=201)
def create_envelope(request: Request, caseId: str, body: dict = Body(default_factory=dict)):
    provider = str((body or {}).get("provider") or "stub").strip().lower() or "stub"
    recipients = (body or {}).get("recipients")
    files = (body or {}).get("files")
    env = create_esign_envelope(
        case_id=str(caseId),
        provider=provider,
        recipients=recipients if isinstance(recipients, list) else [],
        files=files if isinstance(files, list) else [],
        created_by_user_sub=_user_sub(request),
    )
    return {"ok": True, "envelope": env}


@router.post("/contracting/{caseId}/esign/envelopes/{envelopeId}/send")
def send_envelope(request: Request, caseId: str, envelopeId: str):
    try:
        env = _esign_send(case_id=str(caseId), envelope_id=str(envelopeId))
        if not env:
            raise HTTPException(status_code=404, detail="Envelope not found")
        return {"ok": True, "envelope": env}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e) or "Unable to send envelope") from e


@router.post("/contracting/{caseId}/esign/envelopes/{envelopeId}/mark-signed")
def mark_signed(request: Request, caseId: str, envelopeId: str):
    try:
        env = _esign_mark_signed(case_id=str(caseId), envelope_id=str(envelopeId))
        if not env:
            raise HTTPException(status_code=404, detail="Envelope not found")
        return {"ok": True, "envelope": env}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e) or "Unable to mark signed") from e


# Contract/budget generation endpoints are implemented in docgen todo.
# We register them now but return 501 until the generator is wired.


@router.post("/contracting/{caseId}/contract/generate")
def generate_contract(request: Request, caseId: str, body: dict = Body(default_factory=dict)):
    template_id = str((body or {}).get("templateId") or "").strip()
    template_version_id = str((body or {}).get("templateVersionId") or "").strip() or None
    render_inputs = (body or {}).get("renderInputs")
    idempotency_key = str((body or {}).get("idempotencyKey") or "").strip()
    if not template_id:
        raise HTTPException(status_code=400, detail="templateId is required")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="idempotencyKey is required")
    try:
        # Create job record (idempotent)
        job = create_contracting_job(
            idempotency_key=idempotency_key,
            job_type="contract_generate",
            case_id=str(caseId),
            proposal_id=None,
            requested_by_user_sub=_user_sub(request),
            payload={
                "caseId": str(caseId),
                "templateId": template_id,
                "templateVersionId": template_version_id,
                "renderInputs": render_inputs if isinstance(render_inputs, dict) else {},
            },
        )

        # Prefer durable async processing when queue is configured; fall back inline for dev.
        try:
            enqueue_contracting_job(job_id=str(job.get("jobId") or ""))
        except Exception:
            if str(job.get("status") or "") == "queued":
                out = _render_contract_docx(
                    case_id=str(caseId),
                    template_id=template_id,
                    template_version_id=template_version_id,
                    render_inputs=render_inputs if isinstance(render_inputs, dict) else {},
                    created_by_user_sub=_user_sub(request),
                )
                try:
                    from app.repositories.contracting_jobs_repo import complete_job

                    complete_job(job_id=str(job.get("jobId") or ""), result={"contract": out.get("version")})
                except Exception:
                    pass

        return {"ok": True, "job": get_contracting_job(str(job.get("jobId") or "")) or job}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e) or "Invalid request") from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e) or "Contract generation failed") from e


@router.post("/contracting/{caseId}/budget/generate-xlsx")
def generate_budget_xlsx(request: Request, caseId: str, body: dict = Body(default_factory=dict)):
    model = (body or {}).get("budgetModel")
    idempotency_key = str((body or {}).get("idempotencyKey") or "").strip()
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="idempotencyKey is required")
    try:
        job = create_contracting_job(
            idempotency_key=idempotency_key,
            job_type="budget_generate",
            case_id=str(caseId),
            proposal_id=None,
            requested_by_user_sub=_user_sub(request),
            payload={"caseId": str(caseId), "budgetModel": model if isinstance(model, dict) else {}},
        )

        try:
            enqueue_contracting_job(job_id=str(job.get("jobId") or ""))
        except Exception:
            if str(job.get("status") or "") == "queued":
                out = _generate_budget_xlsx(
                    case_id=str(caseId),
                    budget_model=model if isinstance(model, dict) else {},
                    created_by_user_sub=_user_sub(request),
                )
                try:
                    from app.repositories.contracting_jobs_repo import complete_job

                    complete_job(job_id=str(job.get("jobId") or ""), result={"budget": out.get("version")})
                except Exception:
                    pass

        return {"ok": True, "job": get_contracting_job(str(job.get("jobId") or "")) or job}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e) or "Invalid request") from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e) or "Budget generation failed") from e


@router.get("/contracting/jobs/{jobId}")
def get_job(jobId: str):
    job = get_contracting_job(str(jobId or "").strip())
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": job}


@router.get("/contracting/jobs/{jobId}/zip/presign")
def presign_zip_result(jobId: str, expiresIn: int = 900):
    job = get_contracting_job(str(jobId or "").strip()) or {}
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    raw_res = job.get("result")
    res: dict[str, Any] = raw_res if isinstance(raw_res, dict) else {}
    key = str(res.get("zipS3Key") or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="Zip result not available")
    signed = presign_get_object(key=key, expires_in=max(60, min(3600, int(expiresIn or 900))))
    return {"ok": True, "url": signed.get("url"), "expiresIn": max(60, min(3600, int(expiresIn or 900)))}


@router.get("/contracting/{caseId}/jobs")
def list_jobs(caseId: str, limit: int = 50, nextToken: str | None = None):
    return {"ok": True, **list_jobs_for_case(case_id=str(caseId), limit=limit, next_token=nextToken)}

