from __future__ import annotations

import re

from fastapi import APIRouter, Body, HTTPException, Request

from ..services.contracting_repo import (
    add_contract_template_version,
    create_contract_template,
    get_contract_template,
    list_contract_template_versions,
    list_contract_templates,
    set_contract_template_current_version,
)
from ..services.s3_assets import get_object_bytes, presign_get_object, presign_put_object, put_object_bytes


router = APIRouter(tags=["contract_templates"])


def _user_sub(request: Request) -> str | None:
    u = getattr(getattr(request, "state", None), "user", None)
    sub = str(getattr(u, "sub", "") or "").strip() if u else ""
    return sub or None


def _safe_ext(file_name: str, default_ext: str) -> str:
    raw = str(file_name or "").strip()
    m = re.search(r"\.([a-zA-Z0-9]{1,10})$", raw)
    if not m:
        return default_ext
    ext = f".{m.group(1).lower()}"
    return ext


def _template_upload_key(*, template_id: str, version_id: str, file_name: str) -> str:
    ext = _safe_ext(file_name, ".docx")
    if ext not in (".docx",):
        ext = ".docx"
    return f"contract/templates/{str(template_id).strip()}/{str(version_id).strip()}{ext}"


@router.get("/contract-templates/")
def list_all(limit: int = 200, nextToken: str | None = None):
    return list_contract_templates(limit=limit, next_token=nextToken)


@router.post("/contract-templates/", status_code=201)
def create_one(request: Request, body: dict = Body(default_factory=dict)):
    name = str((body or {}).get("name") or "").strip()
    kind = str((body or {}).get("kind") or "").strip().lower() or "combined"
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if kind not in ("msa", "sow", "combined"):
        raise HTTPException(status_code=400, detail="kind must be one of: msa, sow, combined")
    return create_contract_template(name=name, kind=kind, created_by_user_sub=_user_sub(request))


@router.get("/contract-templates/{templateId}")
def get_one(templateId: str):
    t = get_contract_template(templateId)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.put("/contract-templates/{templateId}")
def update_one(request: Request, templateId: str, body: dict = Body(default_factory=dict)):
    current_version_id = str((body or {}).get("currentVersionId") or "").strip()
    if not current_version_id:
        raise HTTPException(status_code=400, detail="currentVersionId is required")
    try:
        t = set_contract_template_current_version(
            template_id=str(templateId),
            version_id=current_version_id,
            updated_by_user_sub=_user_sub(request),
        )
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        return {"ok": True, "template": t}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e) or "Invalid request") from e


@router.get("/contract-templates/{templateId}/versions")
def list_versions(templateId: str, limit: int = 50):
    return {"ok": True, "data": list_contract_template_versions(templateId, limit=limit)}


@router.post("/contract-templates/{templateId}/versions/presign")
def presign_version_upload(request: Request, templateId: str, body: dict = Body(default_factory=dict)):
    """
    Presign a direct-to-S3 upload for a contract template DOCX.

    Flow:
    1) POST presign -> { key, putUrl, versionId }
    2) client PUTs to putUrl
    3) client POST commit -> persists version + sets currentVersionId on template
    """
    file_name = str((body or {}).get("fileName") or "").strip() or "template.docx"
    content_type = str((body or {}).get("contentType") or "").strip().lower() or (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    if content_type not in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    ):
        raise HTTPException(status_code=400, detail="Unsupported contentType")

    # Ensure template exists.
    if not get_contract_template(templateId):
        raise HTTPException(status_code=404, detail="Template not found")

    # Generate a version id early so the upload key is stable.
    # We still require commit to record the version.
    from ..services.contracting_repo import _new_id as _new  # local import to keep module API private

    version_id = _new("ctv")
    key = _template_upload_key(template_id=templateId, version_id=version_id, file_name=file_name)
    presigned = presign_put_object(key=key, content_type=content_type, expires_in=900)
    return {
        "ok": True,
        "templateId": str(templateId),
        "versionId": version_id,
        "bucket": presigned.get("bucket"),
        "key": presigned.get("key"),
        "putUrl": presigned.get("url"),
    }


@router.post("/contract-templates/{templateId}/versions/commit", status_code=201)
def commit_version(request: Request, templateId: str, body: dict = Body(default_factory=dict)):
    version_id = str((body or {}).get("versionId") or "").strip()
    key = str((body or {}).get("key") or "").strip()
    sha256 = str((body or {}).get("sha256") or "").strip().lower() or None
    variables_schema = (body or {}).get("variablesSchema")
    changelog = str((body or {}).get("changelog") or "").strip() or None

    if not version_id:
        raise HTTPException(status_code=400, detail="versionId is required")
    if not key:
        raise HTTPException(status_code=400, detail="key is required")

    # Basic guard: key should look like our namespace to avoid arbitrary writes.
    if not str(key).startswith(f"contract/templates/{str(templateId).strip()}/"):
        raise HTTPException(status_code=400, detail="Invalid key for template")

    v = add_contract_template_version(
        template_id=str(templateId),
        version_id=version_id,
        s3_key=key,
        sha256=sha256,
        variables_schema=variables_schema if isinstance(variables_schema, dict) else {},
        changelog=changelog,
        created_by_user_sub=_user_sub(request),
    )
    return {"ok": True, "version": v}


@router.post("/contract-templates/{templateId}/versions/{versionId}/preview")
def preview_version(
    request: Request,
    templateId: str,
    versionId: str,
    body: dict = Body(default_factory=dict),
    expiresIn: int = 900,
):
    """
    Render a template version with sample inputs for preview.
    Does NOT create a contracting case or version records; stores a temporary artifact in S3.
    """
    tid = str(templateId or "").strip()
    vid = str(versionId or "").strip()
    if not tid or not vid:
        raise HTTPException(status_code=400, detail="templateId and versionId are required")
    tpl_ver = None
    try:
        from ..services.contracting_repo import get_contract_template_version

        tpl_ver = get_contract_template_version(tid, vid)
    except Exception:
        tpl_ver = None
    if not tpl_ver:
        raise HTTPException(status_code=404, detail="Template version not found")
    s3_key = str((tpl_ver or {}).get("s3Key") or "").strip()
    if not s3_key:
        raise HTTPException(status_code=400, detail="Template version missing s3Key")

    key_terms = (body or {}).get("keyTerms") if isinstance((body or {}).get("keyTerms"), dict) else {}
    render_inputs = (body or {}).get("renderInputs") if isinstance((body or {}).get("renderInputs"), dict) else {}

    try:
        from docxtpl import DocxTemplate  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail="DOCX template dependency not installed") from e

    template_bytes = get_object_bytes(key=s3_key, max_bytes=20 * 1024 * 1024)
    if not template_bytes:
        raise HTTPException(status_code=404, detail="Template object is missing")

    import io
    from datetime import datetime, timezone

    doc = DocxTemplate(io.BytesIO(template_bytes))
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    context = {
        "keyTerms": key_terms,
        "renderInputs": render_inputs,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "preview": True,
        "templateId": tid,
        "versionId": vid,
        "requestedBy": _user_sub(request),
    }
    if isinstance(render_inputs, dict):
        context.update({k: v for k, v in render_inputs.items() if k not in ("keyTerms",)})

    try:
        doc.render(context)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Template render failed: {str(e) or 'render_failed'}") from e

    buf = io.BytesIO()
    doc.save(buf)
    out_bytes = buf.getvalue() or b""
    if not out_bytes:
        raise HTTPException(status_code=500, detail="Rendered output was empty")

    out_key = f"contract/template-previews/{tid}/{vid}/{ts}.docx"
    put_object_bytes(
        key=out_key,
        data=out_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    signed = presign_get_object(key=out_key, expires_in=max(60, min(3600, int(expiresIn or 900))))
    return {"ok": True, "key": out_key, "url": signed.get("url"), "expiresIn": max(60, min(3600, int(expiresIn or 900)))}

