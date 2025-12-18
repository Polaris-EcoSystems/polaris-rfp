from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pypdf import PdfReader
import docx2txt

from ..services.attachments_repo import (
    add_attachments,
    delete_attachment,
    get_attachment,
    list_attachments,
)
from ..services.rfps_repo import get_rfp_by_id

router = APIRouter(tags=["attachments"])

_ATTACHMENTS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "attachments"
_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _file_type_category(mime_type: str) -> str:
    mt = (mime_type or "").lower()
    if mt.startswith("image/"):
        return "image"
    if mt == "application/pdf":
        return "pdf"
    if mt in (
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        return "doc"
    if mt in (
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ):
        return "excel"
    if mt == "text/plain":
        return "txt"
    if "zip" in mt:
        return "zip"
    return "other"


def _safe_ext(filename: str) -> str:
    m = re.search(r"(\.[a-zA-Z0-9]{1,10})$", filename or "")
    return m.group(1).lower() if m else ""


def _extract_text_content(file_path: str, mime_type: str) -> str | None:
    mt = (mime_type or "").lower()

    if mt == "application/pdf":
        try:
            reader = PdfReader(file_path)
            parts: list[str] = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    continue
            text = "\n".join([p for p in parts if p]).strip()
            return text or None
        except Exception:
            return None

    if mt == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            text = docx2txt.process(file_path)  # type: ignore[no-untyped-call]
            text = (text or "").strip()
            return text or None
        except Exception:
            return None

    if mt == "text/plain":
        try:
            data = Path(file_path).read_bytes()
            return data.decode("utf-8", errors="ignore").strip() or None
        except Exception:
            return None

    return None


@router.post("/{id}/upload-attachments")
async def upload_attachments(
    id: str,
    files: list[UploadFile] = File(...),
    description: str = Form("") ,
):
    rfp = get_rfp_by_id(id)
    if not rfp:
        # best-effort cleanup is handled below as we write files
        raise HTTPException(status_code=404, detail="RFP not found")

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    allowed = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/zip",
        "application/x-zip-compressed",
    }

    written_paths: list[str] = []

    try:
        payloads: list[dict[str, Any]] = []
        for f in files[:10]:
            mt = (f.content_type or "").lower()
            if mt not in allowed:
                raise HTTPException(status_code=400, detail=f"File type {mt} is not allowed")

            ext = _safe_ext(f.filename or "")
            unique = f"{__import__('time').time_ns()}-{__import__('random').randint(0, 10**9)}{ext}"
            dest = _ATTACHMENTS_DIR / unique

            with dest.open("wb") as out:
                shutil.copyfileobj(f.file, out)

            written_paths.append(str(dest))

            text_content = _extract_text_content(str(dest), mt)
            payloads.append(
                {
                    "fileName": unique,
                    "originalName": f.filename or unique,
                    "fileSize": dest.stat().st_size,
                    "mimeType": mt,
                    "fileType": _file_type_category(mt),
                    "filePath": str(dest),
                    "description": str(description or ""),
                    "textContent": text_content,
                    "textLength": len(text_content) if text_content else 0,
                }
            )

        attachments = add_attachments(id, payloads)

        return {
            "message": f"{len(attachments)} file(s) uploaded successfully",
            "attachments": [
                {
                    "id": att.get("id"),
                    "fileName": att.get("fileName"),
                    "originalName": att.get("originalName"),
                    "fileSize": att.get("fileSize"),
                    "fileType": att.get("fileType"),
                    "uploadedAt": att.get("uploadedAt"),
                    "description": att.get("description"),
                }
                for att in attachments
            ],
        }
    except HTTPException:
        # cleanup
        for p in written_paths:
            try:
                os.unlink(p)
            except Exception:
                pass
        raise
    except Exception:
        for p in written_paths:
            try:
                os.unlink(p)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail="Failed to upload attachments")


@router.get("/{id}/attachments")
def get_attachments(id: str):
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    try:
        attachments = list_attachments(id)
        return {
            "attachments": [
                {
                    "id": att.get("id"),
                    "originalName": att.get("originalName"),
                    "fileSize": att.get("fileSize"),
                    "fileType": att.get("fileType"),
                    "mimeType": att.get("mimeType"),
                    "uploadedAt": att.get("uploadedAt"),
                    "description": att.get("description"),
                }
                for att in attachments
            ]
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch attachments")


@router.get("/{id}/attachments/{attachmentId}")
def download_attachment(id: str, attachmentId: str):
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    attachment = get_attachment(id, attachmentId)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    path = attachment.get("filePath")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="File not found on server")

    return FileResponse(
        path,
        media_type=attachment.get("mimeType") or "application/octet-stream",
        filename=attachment.get("originalName") or attachment.get("fileName") or "attachment",
    )


@router.delete("/{id}/attachments/{attachmentId}")
def delete_one_attachment(id: str, attachmentId: str):
    rfp = get_rfp_by_id(id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    attachment = get_attachment(id, attachmentId)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = attachment.get("filePath")
    try:
        delete_attachment(id, attachmentId)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete attachment")

    if file_path and Path(file_path).exists():
        try:
            os.unlink(file_path)
        except Exception:
            pass

    return {"message": "Attachment deleted successfully"}
