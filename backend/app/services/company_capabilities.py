from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from ..ai.verified_calls import call_json_verified
from ..ai.schemas import CapabilitiesStatementAI

from ..settings import settings
from . import content_repo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_list(values: Any, max_items: int = 50) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for v in values:
        s = str(v or "").strip()
        if not s:
            continue
        if s in out:
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


_RX_PROJ = re.compile(r"\[\[project:([^\]]+)\]\]")
_RX_REF = re.compile(r"\[\[reference:([^\]]+)\]\]")


def _extract_evidence_tokens(md: str) -> tuple[list[str], list[str]]:
    s = str(md or "")
    proj = [m.group(1).strip() for m in _RX_PROJ.finditer(s) if m.group(1).strip()]
    ref = [m.group(1).strip() for m in _RX_REF.finditer(s) if m.group(1).strip()]
    return proj, ref


def _fallback_statement(
    company: dict[str, Any],
    projects: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    name = str(company.get("name") or "").strip() or "Company"
    core = _clean_list(company.get("coreCapabilities"), max_items=25)

    # Infer some capability tags from projects (very lightweight, deterministic)
    inferred: list[str] = []
    for p in projects[:50]:
        for k in ("projectType", "industry"):
            v = str(p.get(k) or "").strip()
            if v and v not in inferred:
                inferred.append(v)
        for t in _clean_list(p.get("technologies"), max_items=10):
            if t not in inferred:
                inferred.append(t)
        if len(inferred) >= 25:
            break

    capabilities = core or inferred
    limitations = [
        "Capabilities reflect the information currently stored in the Content Library (team, past projects, and references).",
        "Work that is not evidenced by a stored past project or reference may not be represented.",
        "Client-specific constraints, regulatory requirements, and specialized certifications may limit applicability on a per-opportunity basis.",
    ]

    # Include light evidence pointers
    proj_ids = [str(p.get("_id") or p.get("projectId") or "").strip() for p in projects]
    proj_ids = [x for x in proj_ids if x][:25]
    ref_ids = [str(r.get("_id") or r.get("referenceId") or "").strip() for r in references]
    ref_ids = [x for x in ref_ids if x][:25]

    bullets = "\n".join([f"- {c}" for c in capabilities[:15]]) or "- (Add past projects and references to generate a richer capabilities list.)"
    limits = "\n".join([f"- {x}" for x in limitations])

    evidence_lines: list[str] = []
    for p in projects[:10]:
        pid = str(p.get("_id") or p.get("projectId") or "").strip()
        if not pid:
            continue
        title = str(p.get("title") or "").strip()
        evidence_lines.append(f"- {title or 'Past project'} [[project:{pid}]]")
    for r in references[:10]:
        rid = str(r.get("_id") or r.get("referenceId") or "").strip()
        if not rid:
            continue
        org = str(r.get("organizationName") or "").strip()
        evidence_lines.append(f"- {org or 'Client reference'} [[reference:{rid}]]")

    statement = (
        f"## {name} Capabilities Statement\n\n"
        f"### Core capabilities\n{bullets}\n\n"
        f"### Known exclusions / limitations\n{limits}\n\n"
        f"### Evidence\n"
        f"{chr(10).join(evidence_lines) if evidence_lines else '- (Add past projects and references to generate evidence.)'}\n"
    )

    evidence_items: list[dict[str, str]] = []
    for p in projects[:50]:
        pid = str(p.get("_id") or p.get("projectId") or "").strip()
        if not pid:
            continue
        title = str(p.get("title") or "").strip()
        evidence_items.append(
            {
                "type": "project",
                "id": pid,
                "label": title or f"Project {pid}",
            }
        )
    for r in references[:50]:
        rid = str(r.get("_id") or r.get("referenceId") or "").strip()
        if not rid:
            continue
        org = str(r.get("organizationName") or "").strip()
        evidence_items.append(
            {
                "type": "reference",
                "id": rid,
                "label": org or f"Reference {rid}",
            }
        )

    meta = {
        "generatedAt": _now_iso(),
        "generator": "fallback",
        "projectIds": proj_ids,
        "referenceIds": ref_ids,
        "capabilities": capabilities[:25],
        "limitations": limitations,
        "evidenceItems": evidence_items[:100],
    }
    return statement, meta


def _generate_with_openai(
    company: dict[str, Any],
    projects: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """
    Returns (statement_markdown, meta).

    The model is instructed to return JSON only so we can safely store both the
    human-friendly statement and structured evidence references.
    """
    company_payload = {
        "companyId": company.get("companyId"),
        "name": company.get("name"),
        "tagline": company.get("tagline"),
        "description": company.get("description"),
        "location": company.get("location"),
        "website": company.get("website"),
        "coreCapabilities": _clean_list(company.get("coreCapabilities"), max_items=50),
        "industryFocus": _clean_list(company.get("industryFocus"), max_items=50),
        "certifications": _clean_list(company.get("certifications"), max_items=50),
        "missionStatement": company.get("missionStatement"),
        "visionStatement": company.get("visionStatement"),
        "values": _clean_list(company.get("values"), max_items=50),
    }

    def proj_min(p: dict[str, Any]) -> dict[str, Any]:
        return {
            "projectId": p.get("_id") or p.get("projectId"),
            "title": p.get("title"),
            "clientName": p.get("clientName"),
            "industry": p.get("industry"),
            "projectType": p.get("projectType"),
            "duration": p.get("duration"),
            "keyOutcomes": _clean_list(p.get("keyOutcomes"), max_items=10),
            "technologies": _clean_list(p.get("technologies"), max_items=15),
            "challenges": _clean_list(p.get("challenges"), max_items=5),
            "solutions": _clean_list(p.get("solutions"), max_items=5),
        }

    def ref_min(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "referenceId": r.get("_id") or r.get("referenceId"),
            "organizationName": r.get("organizationName"),
            "contactName": r.get("contactName"),
            "contactTitle": r.get("contactTitle"),
            "timePeriod": r.get("timePeriod"),
            "projectType": r.get("projectType"),
            "scopeOfWork": r.get("scopeOfWork"),
        }

    projects_payload = [proj_min(p) for p in projects[:30]]
    refs_payload = [ref_min(r) for r in references[:30]]
    allowed_project_ids = {str(p.get("id") or "").strip() for p in projects_payload if str(p.get("id") or "").strip()}
    allowed_ref_ids = {str(r.get("id") or "").strip() for r in refs_payload if str(r.get("id") or "").strip()}
    company_name = str(company_payload.get("name") or "").strip() or "Company"

    system_prompt = (
        "You are an expert proposal writer. Generate a company capabilities statement that is grounded "
        "ONLY in the provided company, past projects, and references.\n\n"
        "Output MUST be valid JSON (no markdown fences, no commentary)."
    )

    user_prompt = {
        "task": "Generate a capabilities statement with evidence links and limitations.",
        "instructions": [
            "Create a concise markdown statement with these sections:",
            "1) '## <Company Name> Capabilities Statement'",
            "2) '### Core capabilities' (bullets)",
            "3) '### Known exclusions / limitations' (bullets) - be specific and avoid overclaiming",
            "4) '### Evidence' - include a short list of evidence items with human labels and citations",
            "Citations MUST use tokens exactly like [[project:<id>]] and [[reference:<id>]].",
            "Use only the IDs that appear in the input payload.",
            "Do not invent projects/references or capabilities that are not supported by the input.",
            "In the '### Evidence' section, include the human label near the token, e.g. '- City Website Redesign [[project:...]]'.",
        ],
        "output_schema": {
            "statementMarkdown": "string",
            "capabilities": ["string"],
            "limitations": ["string"],
            "projectIds": ["string"],
            "referenceIds": ["string"],
            "evidenceItems": [
                {"type": "project|reference", "id": "string", "label": "string"}
            ],
        },
        "input": {
            "company": company_payload,
            "pastProjects": projects_payload,
            "references": refs_payload,
        },
    }

    def _validate(parsed: CapabilitiesStatementAI) -> str | None:
        md = str(parsed.statementMarkdown or "").strip()
        if not md:
            return "statementMarkdown must be non-empty"
        if "### Evidence" not in md:
            return "statementMarkdown must include an '### Evidence' section"
        if "### Core capabilities" not in md:
            return "statementMarkdown must include a '### Core capabilities' section"
        if "Capabilities Statement" not in md:
            return "statementMarkdown must include a capabilities statement heading"

        proj_tokens, ref_tokens = _extract_evidence_tokens(md)
        bad_proj = [t for t in proj_tokens if t not in allowed_project_ids]
        bad_ref = [t for t in ref_tokens if t not in allowed_ref_ids]
        if bad_proj:
            return f"unknown projectIds referenced: {bad_proj[:5]}"
        if bad_ref:
            return f"unknown referenceIds referenced: {bad_ref[:5]}"

        # Keep structured ids consistent with tokens.
        proj_ids = [str(x or "").strip() for x in (parsed.projectIds or []) if str(x or "").strip()]
        ref_ids = [str(x or "").strip() for x in (parsed.referenceIds or []) if str(x or "").strip()]
        if any(pid not in allowed_project_ids for pid in proj_ids):
            return "projectIds must only include input pastProjects ids"
        if any(rid not in allowed_ref_ids for rid in ref_ids):
            return "referenceIds must only include input references ids"

        # Evidence items must reference allowed ids and correct types.
        for it in (parsed.evidenceItems or [])[:200]:
            t = str(it.type or "").strip()
            i = str(it.id or "").strip()
            if t == "project":
                if i not in allowed_project_ids:
                    return "evidenceItems contain unknown project id"
            elif t == "reference":
                if i not in allowed_ref_ids:
                    return "evidenceItems contain unknown reference id"
            else:
                return "evidenceItems.type must be 'project' or 'reference'"
        # Bonus: ensure statement headings mention company name when possible.
        if company_name and company_name.lower() not in md.lower():
            return "statementMarkdown must mention the company name"
        return None

    parsed, meta = call_json_verified(
        purpose="generate_content",
        response_model=CapabilitiesStatementAI,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt)},
        ],
        max_tokens=2000,
        temperature=0.3,
        retries=2,
        validate_parsed=_validate,
        # If AI fails, let caller fall back to deterministic statement.
        fallback=None,
    )

    statement = str(parsed.statementMarkdown or "").strip()
    meta_out = {
        "generatedAt": _now_iso(),
        "generator": "openai",
        "model": meta.model,
        "projectIds": _clean_list(parsed.projectIds, max_items=50),
        "referenceIds": _clean_list(parsed.referenceIds, max_items=50),
        "capabilities": _clean_list(parsed.capabilities, max_items=50),
        "limitations": _clean_list(parsed.limitations, max_items=50),
        "evidenceItems": [it.model_dump() for it in (parsed.evidenceItems or [])][:200],
    }
    return statement, meta_out


def regenerate_company_capabilities(company_id: str) -> dict[str, Any] | None:
    """
    Regenerates and persists Company.capabilitiesStatement (+meta) based on current
    company + its projects/references.
    """
    company = content_repo.get_company_by_company_id(company_id)
    if not company or company.get("isActive") is False:
        return None

    # Filter content tied to this company
    projects = [
        p
        for p in content_repo.list_past_projects(limit=500)
        if p.get("isActive", True) is True and str(p.get("companyId") or "") == str(company_id)
    ]
    references = [
        r
        for r in content_repo.list_project_references(limit=500)
        if r.get("isActive", True) is True and str(r.get("companyId") or "") == str(company_id)
    ]

    if settings.openai_api_key:
        statement, meta = _generate_with_openai(company, projects, references)
    else:
        statement, meta = _fallback_statement(company, projects, references)

    next_version = int(company.get("version") or 0) + 1
    updated = content_repo.upsert_company(
        {
            **company,
            "companyId": company_id,
            "version": next_version,
            "capabilitiesStatement": statement,
            "capabilitiesStatementMeta": meta,
        }
    )
    return updated



