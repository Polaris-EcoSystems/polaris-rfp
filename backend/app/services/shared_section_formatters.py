from __future__ import annotations

from datetime import datetime
from typing import Any

from openai import OpenAI

from ..settings import settings


def replace_company_name(text: str, target_company_name: str) -> str:
    if not text or not target_company_name:
        return text

    company_names = ["Eighth Generation Consulting", "Polaris EcoSystems"]

    result = text
    for name in company_names:
        if name.lower() != target_company_name.lower():
            result = result.replace(name, target_company_name)
            result = result.replace(name.lower(), target_company_name)
            result = result.replace(name.upper(), target_company_name)

    return result


def replace_website(text: str, target_company_name: str) -> str:
    if not text or not target_company_name:
        return text

    website_map = {
        "Eighth Generation Consulting": "https://eighthgen.com",
        "Polaris EcoSystems": "https://polariseco.com",
    }

    target = website_map.get(target_company_name)
    if not target:
        return text

    websites = list(website_map.values())
    result = text

    for site in websites:
        if site == target:
            continue
        result = result.replace(site, target)
        result = result.replace(site.replace("https://", ""), target.replace("https://", ""))

    return result


def format_title_section(company: dict[str, Any] | None, rfp: dict[str, Any] | None) -> dict[str, str]:
    if not company:
        return {
            "submittedBy": "Not specified",
            "name": "Not specified",
            "email": "Not specified",
            "number": "Not specified",
        }

    submitted_by = str(company.get("name") or "Not specified")

    primary = company.get("primaryContact") if isinstance(company.get("primaryContact"), dict) else {}

    contact_name = primary.get("name") or (
        f"{submitted_by.split(' ')[0]} Representative" if submitted_by != "Not specified" else "Not specified"
    )
    contact_email = primary.get("email") or company.get("email") or "Not specified"
    contact_phone = primary.get("phone") or company.get("phone") or "Not specified"

    return {
        "submittedBy": str(submitted_by),
        "name": str(contact_name),
        "email": str(contact_email),
        "number": str(contact_phone),
    }


def format_cover_letter_section(company: dict[str, Any] | None, rfp: dict[str, Any] | None) -> str:
    if not company:
        return "No company information available in the content library."

    rfp = rfp or {}

    current_date = datetime.now().strftime("%m/%d/%Y")
    client_name = rfp.get("clientName") or rfp.get("title") or "Valued Client"
    salutation = f"Dear {rfp.get('clientName')} Team" if rfp.get("clientName") else "Dear Hiring Manager"

    base = company.get("coverLetter") or (
        "We are pleased to submit our proposal for your consideration. "
        "Our team brings extensive experience and expertise to deliver exceptional results for your project."
    )

    cover_letter_content = replace_website(replace_company_name(str(base), str(company.get("name") or "")), str(company.get("name") or ""))

    contact_name = (
        f"{str(company.get('name')).split(' ')[0]} Representative" if company.get("name") else "Project Manager"
    )

    contact_title = "Project Director"
    contact_email = company.get("email") or "contact@company.com"
    contact_phone = company.get("phone") or "(555) 123-4567"

    return (
        f"**Submitted to:** {client_name}\n"
        f"**Submitted by:** {company.get('name') or 'Our Company'}\n"
        f"**Date:** {current_date}\n\n"
        f"{salutation},\n\n"
        f"{cover_letter_content}\n\n"
        "Sincerely,\n\n"
        f"{contact_name}, {contact_title}\n"
        f"{contact_email}\n"
        f"{contact_phone}"
    )


def format_experience_section(company: dict[str, Any] | None, rfp: dict[str, Any] | None) -> str:
    if not company:
        return "No company information available in the content library."

    rfp = rfp or {}

    base = company.get("firmQualificationsAndExperience") or (
        f"{company.get('name') or 'Our company'} brings extensive experience and proven qualifications to deliver exceptional results for your project."
    )

    base = replace_website(replace_company_name(str(base), str(company.get("name") or "")), str(company.get("name") or ""))

    # Optional AI formatting (matches Node's behavior when OpenAI is configured)
    if settings.openai_api_key and company.get("firmQualificationsAndExperience"):
        try:
            client = OpenAI(api_key=settings.openai_api_key)
            prompt = (
                "Take the following company qualifications and experience content and format it professionally for an RFP proposal. "
                "Keep the formatting simple and clean.\n\n"
                f"Company Experience Content:\n{base}\n\n"
                "RFP Project Context:\n"
                f"- Title: {rfp.get('title') or 'Not specified'}\n"
                f"- Client: {rfp.get('clientName') or 'Not specified'}\n"
                f"- Project Type: {rfp.get('projectType') or 'Not specified'}\n"
                f"- Key Requirements: {', '.join(rfp.get('keyRequirements') or []) or 'Not specified'}\n\n"
                "Format this content following these rules:\n"
                "1. Use the company's content as the primary source - do not add excessive details\n"
                "2. Keep formatting simple - use hyphens (-) for lists, no markdown headings (#)\n"
                "3. Write in paragraph form with bullet points for achievements/awards only\n"
                "4. Make it relevant to the RFP but don't over-elaborate\n"
                "5. Use professional, concise language\n"
                "6. Do not add multiple sections or subheadings\n"
                "7. Keep the same tone and style as the original content\n\n"
                "Return only the clean, simply formatted content without markdown headings or excessive structure."
            )

            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            formatted = (completion.choices[0].message.content or "").strip()
            if formatted:
                return formatted
        except Exception:
            pass

    formatted = base

    stats = company.get("statistics") if isinstance(company.get("statistics"), dict) else {}
    years = stats.get("yearsInBusiness")
    projects = stats.get("projectsCompleted")
    clients = stats.get("clientsSatisfied")

    if years or projects:
        formatted += "\n\n"
        if years:
            formatted += f"Our company has been in business for {years}+ years"
        if projects:
            formatted += (", completing" if years else "We have completed") + f" {projects}+ projects"
        if clients:
            formatted += f" for {clients}+ satisfied clients"
        formatted += "."

    caps = company.get("coreCapabilities") if isinstance(company.get("coreCapabilities"), list) else []
    if caps:
        formatted += f"\n\nOur core services include: {', '.join([str(x) for x in caps if str(x).strip()])}."

    return formatted.strip()
