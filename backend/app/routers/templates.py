from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..repositories import templates_repo
from ..pipeline.proposal_generation.templates_catalog import (
    get_builtin_template,
    list_builtin_template_summaries,
    to_generator_template,
)

router = APIRouter(tags=["templates"])

def _summary_from_template(t: dict) -> dict:
    """
    Frontend expects Template summary:
      { id, name, projectType, sectionCount }
    """
    tid = str(t.get("id") or t.get("_id") or t.get("templateId") or "").strip()
    name = str(t.get("name") or "").strip()
    project_type = str(t.get("projectType") or t.get("templateType") or "").strip() or "general"
    raw_sections = t.get("sections")
    sections: list[object] = raw_sections if isinstance(raw_sections, list) else []
    return {
        "id": tid,
        "name": name,
        "projectType": project_type,
        "sectionCount": len(sections),
        "isBuiltin": bool(t.get("isBuiltin") is True),
    }


@router.get("/")
def list_templates():
    # Compatibility:
    # - Frontend often reads `response.data.data` (array)
    # - Legacy Node shape sometimes returned multiple fields
    builtin = list_builtin_template_summaries()
    ddb = templates_repo.list_templates(limit=200)

    # Provide a single list the UI can consume.
    data = []
    for t in builtin:
        if isinstance(t, dict):
            data.append(_summary_from_template(t))
    for t in ddb:
        if isinstance(t, dict):
            data.append(_summary_from_template(t))

    return {
        "data": data,
        "builtin": builtin,
        "templates": ddb,
    }


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

    # Frontend sends `templateType` (one of builtin ids) not `projectType`.
    # Normalize inputs and optionally seed sections from the builtin template.
    doc = dict(body or {})
    if not doc.get("projectType") and doc.get("templateType"):
        doc["projectType"] = doc.get("templateType")

    if not doc.get("sections") and doc.get("projectType"):
        # If they chose a builtin type, seed sections so the template is immediately editable.
        builtin = get_builtin_template(str(doc.get("projectType")))
        if builtin:
            seeded = to_generator_template(builtin) or {}
            secs = seeded.get("sections")
            if isinstance(secs, list):
                # Store in the same shape the generator expects (title/name/etc).
                doc["sections"] = secs

    created = templates_repo.create_template(doc)
    # Include a summary-friendly shape for callers that expect it.
    try:
        out = dict(created)
        out["sectionCount"] = len(out.get("sections") or []) if isinstance(out.get("sections"), list) else 0
        return out
    except Exception:
        return created


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
