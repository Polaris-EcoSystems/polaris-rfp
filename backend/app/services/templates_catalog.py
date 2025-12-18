from __future__ import annotations

from typing import Any


builtin_templates: dict[str, dict[str, Any]] = {
    "software_development": {
        "id": "software_development",
        "name": "Software Development Proposal",
        "projectType": "software_development",
        "sections": [
            {"title": "Title", "contentType": "title", "required": True},
            {"title": "Cover Letter", "contentType": "cover_letter", "required": True},
            {
                "title": "Firm Qualifications and Experience",
                "contentType": "Firm Qualifications and Experience",
                "required": True,
            },
            {
                "title": "Technical Approach & Methodology",
                "contentType": "Technical Approach & Methodology",
                "required": True,
                "subsections": [
                    "Project Initiation & Planning",
                    "Technical Architecture",
                    "Development Phases",
                    "Testing & Quality Assurance",
                    "Deployment & Launch",
                    "Maintenance & Support",
                ],
            },
            {
                "title": "Key Personnel and Experience",
                "contentType": "Key Personnel and Experience",
                "required": True,
                "includeRoles": [
                    "project_lead",
                    "technical_lead",
                    "senior_architect",
                    "qa_lead",
                ],
            },
            {
                "title": "Budget Estimate",
                "contentType": "Budget Estimate",
                "required": True,
                "format": "detailed_table",
            },
            {"title": "Project Timeline", "contentType": "Project Timeline", "required": True},
            {
                "title": "References",
                "contentType": "References",
                "required": True,
                "minimumCount": 3,
                "filterByType": "software_development",
            },
        ],
    },
    "strategic_communications": {
        "id": "strategic_communications",
        "name": "Strategic Communications Proposal",
        "projectType": "strategic_communications",
        "sections": [
            {"title": "Title", "contentType": "Title", "required": True},
            {"title": "Cover Letter", "contentType": "Cover Letter", "required": True},
            {
                "title": "Experience & Qualifications",
                "contentType": "Experience & Qualifications",
                "required": True,
            },
            {
                "title": "Project Understanding & Workplan",
                "contentType": "Project Understanding & Workplan",
                "required": True,
            },
            {"title": "Benefits to Client", "contentType": "Benefits to Client", "required": True},
            {
                "title": "Key Team Members",
                "contentType": "Key Team Members",
                "required": True,
                "includeRoles": ["project_manager", "communications_lead", "content_strategist"],
            },
            {"title": "Budget", "contentType": "Budget", "required": True},
            {
                "title": "Compliance & Quality Assurance",
                "contentType": "Compliance & Quality Assurance",
                "required": True,
            },
            {
                "title": "References",
                "contentType": "client_references",
                "required": True,
                "minimumCount": 3,
                "filterByType": "strategic_communications",
            },
        ],
    },
    "financial_modeling": {
        "id": "financial_modeling",
        "name": "Financial Modeling & Analysis Proposal",
        "projectType": "financial_modeling",
        "sections": [
            {"title": "Title", "contentType": "title", "required": True},
            {"title": "Cover Letter", "contentType": "cover_letter", "required": True},
            {
                "title": "Firm Qualifications and Experience",
                "contentType": "Firm Qualifications and Experience",
                "required": True,
            },
            {"title": "Methodology & Approach", "contentType": "Methodology & Approach", "required": True},
            {
                "title": "Team Expertise",
                "contentType": "Key Team Members",
                "required": True,
                "includeRoles": ["financial_analyst", "senior_modeler", "project_manager"],
            },
            {
                "title": "Deliverables & Timeline",
                "contentType": "Deliverables & Timeline",
                "required": True,
            },
            {"title": "Investment & Budget", "contentType": "Budget", "required": True},
            {
                "title": "References",
                "contentType": "client_references",
                "required": True,
                "filterByType": "financial_modeling",
            },
        ],
    },
}


def get_builtin_template(template_id: str) -> dict[str, Any] | None:
    return builtin_templates.get(str(template_id))


def list_builtin_template_summaries() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in builtin_templates.values():
        out.append(
            {
                "id": t["id"],
                "name": t["name"],
                "projectType": t["projectType"],
                "sectionCount": len(t.get("sections") or []),
                "isBuiltin": True,
            }
        )
    return out


def to_generator_template(template: dict[str, Any] | None) -> dict[str, Any] | None:
    if not template:
        return None

    tid = str(template.get("id") or template.get("_id") or template.get("templateId") or "")
    if tid and tid in builtin_templates:
        t = builtin_templates[tid]
        return {
            "_id": t["id"],
            "name": t["name"],
            "projectType": t["projectType"],
            "sections": [
                {
                    "name": s.get("title"),
                    "title": s.get("title"),
                    "contentType": s.get("contentType") or "static",
                    "isRequired": s.get("required") is not False,
                    "order": idx + 1,
                    "subsections": s.get("subsections") or [],
                    "includeRoles": s.get("includeRoles") or [],
                    "minimumCount": s.get("minimumCount"),
                    "filterByType": s.get("filterByType"),
                    "format": s.get("format"),
                }
                for idx, s in enumerate(t.get("sections") or [])
            ],
        }

    # DDB template already matches expected shape
    return template
