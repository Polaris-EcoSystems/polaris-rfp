from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..observability.logging import get_logger
from ..repositories.contracting_repo import get_package_by_portal_token, hash_portal_token
from ..infrastructure.storage.s3_assets import presign_get_object


router = APIRouter(tags=["client_portal"])
log = get_logger("client_portal")


@router.get("/client/portal/{token}")
def get_portal_package(token: str):
    # Log token hash prefix only (never the token itself).
    try:
        tok_hash = hash_portal_token(token)
        log.info("portal_access", tokenHashPrefix=str(tok_hash)[:10])
    except Exception:
        log.info("portal_access", tokenHashPrefix="(invalid)")
    pkg = get_package_by_portal_token(token)
    if not pkg:
        raise HTTPException(status_code=404, detail="Portal package not found")
    # Return minimal safe payload for clients.
    raw_files = pkg.get("selectedFiles")
    files: list[object] = raw_files if isinstance(raw_files, list) else []
    safe_files = []
    for f in files:
        if not isinstance(f, dict):
            continue
        safe_files.append(
            {
                "id": str(f.get("id") or "").strip() or None,
                "kind": str(f.get("kind") or "").strip() or "file",
                "label": str(f.get("label") or f.get("fileName") or "").strip() or "File",
                "fileName": str(f.get("fileName") or "").strip() or None,
                "contentType": str(f.get("contentType") or "").strip().lower() or "application/octet-stream",
            }
        )
    return {
        "ok": True,
        "package": {
            "caseId": pkg.get("caseId"),
            "packageId": pkg.get("packageId"),
            "name": pkg.get("name"),
            "publishedAt": pkg.get("publishedAt"),
            "portalTokenExpiresAt": pkg.get("portalTokenExpiresAt"),
            "files": safe_files,
        },
    }


@router.get("/client/portal/{token}/files/{fileId}/presign")
def presign_portal_file(token: str, fileId: str, expiresIn: int = 900):
    try:
        tok_hash = hash_portal_token(token)
        log.info("portal_presign", tokenHashPrefix=str(tok_hash)[:10], fileId=str(fileId or "")[:32])
    except Exception:
        log.info("portal_presign", tokenHashPrefix="(invalid)", fileId=str(fileId or "")[:32])
    pkg = get_package_by_portal_token(token)
    if not pkg:
        raise HTTPException(status_code=404, detail="Portal package not found")
    fid = str(fileId or "").strip()
    if not fid:
        raise HTTPException(status_code=400, detail="fileId is required")
    raw_files = pkg.get("selectedFiles")
    files: list[object] = raw_files if isinstance(raw_files, list) else []
    match = None
    for f in files:
        if not isinstance(f, dict):
            continue
        if str(f.get("id") or "").strip() == fid:
            match = f
            break
    if not match:
        raise HTTPException(status_code=404, detail="File not found in package")
    key = str(match.get("s3Key") or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="File unavailable")
    signed = presign_get_object(key=key, expires_in=max(60, min(3600, int(expiresIn or 900))))
    return {"ok": True, "url": signed.get("url"), "expiresIn": max(60, min(3600, int(expiresIn or 900)))}

