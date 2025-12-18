from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from docx import Document
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..settings import settings
from ..services import content_repo, templates_repo
from ..services.proposals_repo import (
    create_proposal,
    delete_proposal,
    get_proposal_by_id,
    list_proposals,
    update_proposal,
    update_proposal_review,
)
from ..services.rfps_repo import get_rfp_by_id
from ..services.shared_section_formatters import (
    format_cover_letter_section,
    format_experience_section,
    format_title_section,
)
from ..services.team_member_profiles import pick_team_member_bio, pick_team_member_experience
from ..services.templates_catalog import get_builtin_template, to_generator_template
from ..observability.logging import get_logger

router = APIRouter(tags=["proposals"])
log = get_logger("proposals")


def _openai() -> OpenAI | None:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _generate_text_section(
    title: str, rfp: dict[str, Any], company: dict[str, Any] | None
) -> str:
    if not settings.openai_api_key:
        return f"{title}\n\n(This section will be completed in the proposal editor.)"

    client = _openai()
    if not client:
        return f"{title}\n\n(This section will be completed in the proposal editor.)"

    prompt = (
        "Write a high-quality proposal section. Preserve markdown.\n\n"
        f"SECTION_TITLE: {title}\n"
        f"RFP_TITLE: {rfp.get('title') or ''}\n"
        f"CLIENT: {rfp.get('clientName') or ''}\n"
        f"PROJECT_TYPE: {rfp.get('projectType') or ''}\n"
        f"KEY_REQUIREMENTS: {', '.join(rfp.get('keyRequirements') or [])}\n\n"
        "COMPANY_CONTEXT:\n"
        f"- Name: {(company or {}).get('name') or ''}\n"
        f"- Capabilities: {', '.join((company or {}).get('coreCapabilities') or [])}\n\n"
        "Return ONLY the section content."
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    return (completion.choices[0].message.content or "").strip() or ""


def _build_team_section(selected_ids: list[str], rfp: dict[str, Any]) -> str:
    members = content_repo.get_team_members_by_ids(selected_ids)
    members = [
        m for m in members if m and (m.get("isActive") is True or m.get("isActive") is None)
    ]
    project_type = rfp.get("projectType") if isinstance(rfp, dict) else None

    if not members:
        return "No team members selected."

    content = (
        "Our experienced team brings together diverse expertise and proven track record to deliver exceptional results.\n\n"
    )

    for member in members:
        bio = pick_team_member_bio(member, project_type)
        exp = pick_team_member_experience(member, project_type)
        content += (
            f"**{member.get('nameWithCredentials') or member.get('name') or ''}** - {member.get('position') or ''}\n\n"
        )
        if bio:
            content += f"{bio}\n\n"
        if exp:
            content += f"**Relevant experience:**\n\n{exp}\n\n"

    return content.strip()


def _build_references_section(selected_ids: list[str]) -> str:
    refs = content_repo.get_project_references_by_ids(selected_ids)
    refs = [
        r
        for r in refs
        if r
        and (r.get("isActive") is True or r.get("isActive") is None)
        and (r.get("isPublic") is True or r.get("isPublic") is None)
    ]

    if not refs:
        return "No references selected."

    content = (
        "Below are some of our recent project references that demonstrate our capabilities and client satisfaction:\n\n"
    )

    for reference in refs:
        content += f"**{reference.get('organizationName') or ''}**"
        if reference.get("timePeriod"):
            content += f" ({reference.get('timePeriod')})"
        content += "\n\n"

        content += f"**Contact:** {reference.get('contactName') or ''}"
        if reference.get("contactTitle"):
            content += f", {reference.get('contactTitle')}"
        if reference.get("additionalTitle"):
            content += f" - {reference.get('additionalTitle')}"
        content += f" of {reference.get('organizationName') or ''}\n\n"

        if reference.get("contactEmail"):
            content += f"**Email:** {reference.get('contactEmail')}\n\n"
        if reference.get("contactPhone"):
            content += f"**Phone:** {reference.get('contactPhone')}\n\n"

        content += f"**Scope of Work:** {reference.get('scopeOfWork') or ''}\n\n---\n\n"

    return content.strip()


def _section_content_from_title(
    section_title: str, rfp: dict[str, Any], company: dict[str, Any] | None
) -> Any:
    st = (section_title or "").lower().strip()

    if st == "title" or st == "title page" or "title page" in st:
        return format_title_section(company, rfp)

    if "cover letter" in st or "introduction letter" in st or "transmittal letter" in st:
        return format_cover_letter_section(company, rfp)

    if (
        "experience" in st
        or "qualification" in st
        or "capabil" in st
        or "company profile" in st
        or "firm" in st
    ):
        return format_experience_section(company, rfp)

    return _generate_text_section(section_title, rfp, company)


def _render_pdf(proposal: dict[str, Any], company: dict[str, Any] | None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    _, height = letter

    x = 50
    y = height - 50

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, str(proposal.get("title") or "Proposal"))
    y -= 30

    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Company: {(company or {}).get('name') or ''}")
    y -= 20

    sections = proposal.get("sections") or {}
    for name, sec in sections.items():
        if y < 100:
            c.showPage()
            y = height - 50

        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y, str(name))
        y -= 18

        c.setFont("Helvetica", 10)
        content = (sec or {}).get("content") if isinstance(sec, dict) else sec

        if isinstance(content, dict):
            content_str = "\n".join([f"{k}: {v}" for k, v in content.items()])
        else:
            content_str = str(content or "")

        for line in content_str.splitlines()[:2000]:
            if y < 60:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 10)
            c.drawString(x, y, line[:110])
            y -= 12

        y -= 10

    c.save()
    return buf.getvalue()


def _render_docx(proposal: dict[str, Any], company: dict[str, Any] | None) -> bytes:
    doc = Document()
    doc.add_heading(str(proposal.get("title") or "Proposal"), level=0)
    if company and company.get("name"):
        doc.add_paragraph(f"Company: {company.get('name')}")

    sections = proposal.get("sections") or {}
    for name, sec in sections.items():
        doc.add_heading(str(name), level=1)
        content = (sec or {}).get("content") if isinstance(sec, dict) else sec
        if isinstance(content, dict):
            for k, v in content.items():
                doc.add_paragraph(f"{k}: {v}")
        else:
            for line in str(content or "").splitlines():
                doc.add_paragraph(line)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@router.post("/generate", status_code=201)
def generate(body: dict):
    rfp_id = (body or {}).get("rfpId")
    template_id = (body or {}).get("templateId")
    title = (body or {}).get("title")
    company_id = (body or {}).get("companyId")
    custom_content = (body or {}).get("customContent") or {}

    if not rfp_id or not template_id or not title:
        raise HTTPException(
            status_code=400, detail="Missing required fields: rfpId, templateId, title"
        )

    rfp = get_rfp_by_id(str(rfp_id))
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    effective_custom = dict(custom_content) if isinstance(custom_content, dict) else {}
    if company_id:
        effective_custom["companyId"] = company_id

    company = None
    if company_id:
        company = content_repo.get_company_by_company_id(str(company_id))
    if not company:
        comps = content_repo.list_companies(limit=1)
        company = comps[0] if comps else None

    sections: dict[str, Any] = {}

    if str(template_id) == "ai-template":
        titles = rfp.get("sectionTitles") if isinstance(rfp.get("sectionTitles"), list) else []
        if not titles:
            titles = [
                "Title",
                "Cover Letter",
                "Firm Qualifications and Experience",
                "Technical Approach",
                "Key Personnel",
                "References",
            ]
        for t in titles:
            name = str(t)
            sections[name] = {
                "content": _section_content_from_title(name, rfp, company),
                "type": "ai",
                "lastModified": _now_iso(),
            }
    else:
        builtin = get_builtin_template(str(template_id))
        template = (
            {**builtin, "isBuiltin": True}
            if builtin
            else templates_repo.get_template_by_id(str(template_id))
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        gen_template = to_generator_template(template)
        sec_defs = (gen_template or {}).get("sections") if isinstance(gen_template, dict) else []
        for s in sec_defs or []:
            name = str(s.get("title") or s.get("name") or "").strip() or "Section"
            sections[name] = {
                "content": _section_content_from_title(name, rfp, company),
                "type": "ai",
                "lastModified": _now_iso(),
            }

    proposal = create_proposal(
        rfp_id=str(rfp_id),
        company_id=str(company_id) if company_id else None,
        template_id=str(template_id),
        title=str(title),
        sections=sections,
        custom_content=effective_custom,
        rfp_summary={
            "title": rfp.get("title"),
            "clientName": rfp.get("clientName"),
            "projectType": rfp.get("projectType"),
        },
    )

    return proposal


@router.post("/{id}/generate-sections")
def generate_sections(id: str):
    proposal = get_proposal_by_id(id, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    rfp = get_rfp_by_id(str(proposal.get("rfpId")))
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    company = None
    if proposal.get("companyId"):
        company = content_repo.get_company_by_company_id(str(proposal.get("companyId")))
    if not company:
        comps = content_repo.list_companies(limit=1)
        company = comps[0] if comps else None

    sections = proposal.get("sections") or {}
    next_sections: dict[str, Any] = {}

    for name in sections.keys():
        nm = str(name)
        next_sections[nm] = {
            "content": _section_content_from_title(nm, rfp, company),
            "type": "ai",
            "lastModified": _now_iso(),
        }

    updated = update_proposal(
        id, {"sections": next_sections, "lastModifiedBy": "ai-generation"}
    )

    return {"message": "Sections generated successfully", "sections": next_sections, "proposal": updated}


@router.get("/")
def list_all(request: Request, page: int = 1, limit: int = 20):
    try:
        return list_proposals(page=page, limit=limit)
    except Exception as e:
        rid = getattr(getattr(request, "state", None), "request_id", None)
        user = getattr(getattr(request, "state", None), "user", None)
        user_sub = getattr(user, "sub", None) if user else None
        log.exception(
            "proposal_list_failed",
            request_id=str(rid) if rid else None,
            user_sub=str(user_sub) if user_sub else None,
        )
        raise HTTPException(status_code=500, detail="Failed to fetch proposals") from e


@router.get("/{id}")
def get_one(id: str):
    proposal = get_proposal_by_id(id, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


@router.put("/{id}")
def update_one(id: str, body: dict):
    updated = update_proposal(id, {**(body or {}), "lastModifiedBy": "system"})
    if not updated:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return updated


@router.delete("/{id}")
def delete_one(id: str):
    try:
        delete_proposal(id)
        return {"message": "Proposal deleted successfully"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete proposal")


@router.get("/{id}/export-pdf")
@router.get("/{id}/export/pdf")
def export_pdf(id: str):
    proposal = get_proposal_by_id(id, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    company = None
    if proposal.get("companyId"):
        company = content_repo.get_company_by_company_id(str(proposal.get("companyId")))
    if not company:
        comps = content_repo.list_companies(limit=1)
        company = comps[0] if comps else None

    pdf_bytes = _render_pdf(proposal, company)
    filename = re.sub(r"\s+", "_", str(proposal.get("title") or "proposal")) + ".pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@router.get("/{id}/export-docx")
def export_docx(id: str):
    proposal = get_proposal_by_id(id, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    company = None
    if proposal.get("companyId"):
        company = content_repo.get_company_by_company_id(str(proposal.get("companyId")))
    if not company:
        comps = content_repo.list_companies(limit=1)
        company = comps[0] if comps else None

    docx_bytes = _render_docx(proposal, company)

    filename = re.sub(r"\s+", "_", str(proposal.get("title") or "proposal"))
    filename = re.sub(r"[^a-zA-Z0-9_-]", "", filename) + ".docx"

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@router.put("/{id}/content-library/{sectionName}")
def update_content_library_section(id: str, sectionName: str, body: dict):
    selected_ids = (body or {}).get("selectedIds")
    sel = [str(x) for x in (selected_ids if isinstance(selected_ids, list) else [])]
    typ = str((body or {}).get("type") or "").strip().lower()

    proposal = get_proposal_by_id(id, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    content: Any = ""

    if typ == "company":
        if sel:
            company = content_repo.get_company_by_company_id(sel[0])
            if not company:
                content = "Selected company not found."
            else:
                rfp = get_rfp_by_id(str(proposal.get("rfpId"))) or {}
                st = sectionName.lower()
                if st == "title":
                    content = format_title_section(company, rfp)
                elif "cover letter" in st or "introduction letter" in st or "transmittal letter" in st:
                    content = format_cover_letter_section(company, rfp)
                else:
                    content = format_experience_section(company, rfp)
        else:
            content = "No company selected."
    elif typ == "team":
        rfp = get_rfp_by_id(str(proposal.get("rfpId"))) or {}
        content = _build_team_section(sel, rfp)
    elif typ == "references":
        content = _build_references_section(sel)

    updated_sections = dict(proposal.get("sections") or {})
    existing_section = (
        updated_sections.get(sectionName)
        if isinstance(updated_sections.get(sectionName), dict)
        else {}
    )
    updated_sections[sectionName] = {
        **(existing_section or {}),
        "content": content.strip() if isinstance(content, str) else content,
        "type": "content-library",
        "lastModified": _now_iso(),
        "selectedIds": sel,
    }

    updated = update_proposal(id, {"sections": updated_sections})
    return updated


@router.put("/{id}/company")
def switch_company(id: str, body: dict):
    company_id = (body or {}).get("companyId")
    if not company_id or not isinstance(company_id, str):
        raise HTTPException(status_code=400, detail="companyId is required")

    proposal = get_proposal_by_id(id, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    company = content_repo.get_company_by_company_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    rfp = get_rfp_by_id(str(proposal.get("rfpId"))) or {}

    updated_sections = dict(proposal.get("sections") or {})

    updated_sections["Title"] = {
        **(updated_sections.get("Title") or {}),
        "content": format_title_section(company, rfp),
        "type": "content-library",
        "lastModified": _now_iso(),
        "selectedIds": [company_id],
    }

    updated_sections["Cover Letter"] = {
        **(updated_sections.get("Cover Letter") or {}),
        "content": format_cover_letter_section(company, rfp),
        "type": "content-library",
        "lastModified": _now_iso(),
        "selectedIds": [company_id],
    }

    for name in list(updated_sections.keys()):
        n = str(name).lower()
        if any(k in n for k in ("experience", "qualifications", "firm", "capabilities", "company profile")):
            updated_sections[name] = {
                **(updated_sections.get(name) or {}),
                "content": format_experience_section(company, rfp),
                "type": "content-library",
                "lastModified": _now_iso(),
                "selectedIds": [company_id],
            }
            break

    updated = update_proposal(
        id,
        {
            "companyId": company_id,
            "customContent": {**(proposal.get("customContent") or {}), "companyId": company_id},
            "sections": updated_sections,
            "lastModifiedBy": "system",
        },
    )
    return updated


@router.put("/{id}/review")
def update_review(id: str, body: dict):
    proposal = get_proposal_by_id(id, include_sections=True)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    score = (body or {}).get("score")
    notes = (body or {}).get("notes")
    rubric = (body or {}).get("rubric")
    decision = (body or {}).get("decision")

    next_score = None
    if score not in (None, ""):
        try:
            n = float(score)
            next_score = max(0, min(100, n))
        except Exception:
            next_score = None

    next_decision = ((proposal.get("review") or {}).get("decision") or "")
    if decision is None:
        next_decision = ""
    if isinstance(decision, str):
        d = decision.strip().lower()
        if d in ("", "shortlist", "reject"):
            next_decision = d

    next_review = {
        **(proposal.get("review") or {}),
        "score": next_score,
        "decision": next_decision,
        "notes": notes if isinstance(notes, str) else (proposal.get("review") or {}).get("notes") or "",
        "rubric": rubric if isinstance(rubric, dict) else (proposal.get("review") or {}).get("rubric") or {},
        "updatedAt": _now_iso(),
    }

    updated = update_proposal_review(id, next_review)
    return updated
