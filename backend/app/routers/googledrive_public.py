from __future__ import annotations

import json
from typing import Any

import importlib
from fastapi import APIRouter, Body, HTTPException, Request

from app.observability.logging import get_logger
from app.repositories.rfp_proposals_repo import get_proposal_by_id

router = APIRouter(tags=["googledrive"])
log = get_logger("googledrive_public")


@router.post("/upload-proposal/{proposalId}")
def upload_proposal_to_drive(proposalId: str, request: Request, body: dict = Body(...)) -> dict[str, Any]:
    """
    Upload a proposal JSON snapshot to Google Drive.

    Frontend contract:
    - POST /googledrive/upload-proposal/{proposalId}
    - body: { fileName: string }
    - response: { ok: boolean, file: { name: string, webViewLink?: string, fileId?: string } }
    """
    pid = str(proposalId or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="proposalId is required")

    file_name = str((body or {}).get("fileName") or "").strip() or f"{pid}_Proposal.json"

    proposal = get_proposal_by_id(pid)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    # Minimal mode: upload to Drive root (no per-RFP folder automation).
    folder_id: str | None = None

    try:
        payload = json.dumps(proposal, ensure_ascii=False, indent=2)
        upload_file_to_drive = getattr(
            importlib.import_module("app.infrastructure.google_drive"), "upload_file_to_drive"
        )
        res_raw = upload_file_to_drive(
            name=file_name, content=payload, mime_type="application/json", folder_id=folder_id
        )
        res: dict[str, Any] = res_raw if isinstance(res_raw, dict) else {}
        if not res.get("ok"):
            return {"ok": False, "error": str(res.get("error") or "upload_failed")}
        return {
            "ok": True,
            "file": {
                "id": res.get("fileId"),
                "name": res.get("name") or file_name,
                "webViewLink": res.get("webViewLink") or "",
            },
        }
    except Exception as e:
        log.warning("googledrive_upload_failed", proposalId=pid, error=str(e))
        return {"ok": False, "error": str(e) or "upload_failed"}


