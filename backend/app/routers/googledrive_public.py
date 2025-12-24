from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from ..observability.logging import get_logger
from ..repositories.rfp.proposals_repo import get_proposal_by_id
from ..tools.categories.google.google_drive import upload_file_to_drive

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

    # Determine a folder based on the RFP (best-effort).
    folder_id: str | None = None
    try:
        rfp_id = str((proposal or {}).get("rfpId") or "").strip()
        if rfp_id:
            from ..infrastructure.integrations.drive.drive_project_setup import setup_project_folders

            setup = setup_project_folders(rfp_id=rfp_id)
            if isinstance(setup, dict) and setup.get("ok"):
                folders = setup.get("folders") if isinstance(setup.get("folders"), dict) else {}
                # Prefer Drafts, then root.
                folder_id = str(folders.get("drafts") or folders.get("root") or "").strip() or None
    except Exception:
        folder_id = None

    try:
        payload = json.dumps(proposal, ensure_ascii=False, indent=2)
        res = upload_file_to_drive(name=file_name, content=payload, mime_type="application/json", folder_id=folder_id)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "upload_failed"}
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


