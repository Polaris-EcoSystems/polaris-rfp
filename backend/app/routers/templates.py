from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import templates_repo
from ..services.templates_catalog import get_builtin_template, list_builtin_template_summaries

router = APIRouter(tags=["templates"])


@router.get("/")
def list_templates():
    # match Node behavior: include builtin summaries and DDB templates
    return {"builtin": list_builtin_template_summaries(), "templates": templates_repo.list_templates(limit=200)}


@router.get("/{templateId}")
def get_template(templateId: str):
    builtin = get_builtin_template(templateId)
    if builtin:
        return builtin

    t = templates_repo.get_template_by_id(templateId)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.post("/", status_code=201)
def create_template(body: dict):
    name = str((body or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    return templates_repo.create_template(body or {})


@router.put("/{templateId}")
def update_template(templateId: str, body: dict):
    t = templates_repo.update_template(templateId, body or {})
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.delete("/{templateId}")
def delete_template(templateId: str):
    templates_repo.delete_template(templateId)
    return {"success": True}


@router.get("/{templateId}/preview")
@router.post("/{templateId}/preview")
def preview_template(templateId: str):
    # frontend currently calls GET, node implemented POST; we accept both and return a basic preview envelope.
    builtin = get_builtin_template(templateId)
    if not builtin and not templates_repo.get_template_by_id(templateId):
        raise HTTPException(status_code=404, detail="Template not found")

    return {"ok": True, "templateId": templateId}
