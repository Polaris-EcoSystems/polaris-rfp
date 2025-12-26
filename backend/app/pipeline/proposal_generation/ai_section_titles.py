from __future__ import annotations

from typing import Any

from ...ai.client import AiError, AiNotConfigured
from ...ai.schemas import SectionTitlesAI
from ...ai.verified_calls import call_json_verified


def generate_section_titles(rfp: dict[str, Any]) -> list[str]:
    def _fallback() -> list[str]:
        # A sensible default list that keeps proposal generation usable.
        return [
            "Executive Summary",
            "Understanding of Requirements",
            "Approach and Methodology",
            "Project Plan and Schedule",
            "Team and Qualifications",
            "Relevant Experience",
            "Pricing and Budget",
            "Risk Management",
            "Deliverables",
            "Appendices",
        ]

    prompt = (
        "Given the following RFP summary, propose a concise list of proposal section titles.\n"
        "Return JSON ONLY: {\"titles\": [\"...\", ...]}.\n\n"
        f"RFP_TITLE: {rfp.get('title') or ''}\n"
        f"CLIENT: {rfp.get('clientName') or ''}\n"
        f"PROJECT_TYPE: {rfp.get('projectType') or ''}\n"
        f"KEY_REQUIREMENTS: {', '.join(rfp.get('keyRequirements') or [])}\n"
        f"DELIVERABLES: {', '.join(rfp.get('deliverables') or [])}\n"
    )

    try:
        def _validate(parsed: SectionTitlesAI) -> str | None:
            titles = [str(t).strip() for t in (parsed.titles or []) if str(t).strip()]
            if len(titles) < 3:
                return "titles must include at least 3 items"
            return None

        parsed, _meta = call_json_verified(
            purpose="section_titles",
            response_model=SectionTitlesAI,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.2,
            retries=2,
            validate_parsed=_validate,
        )
        out = [str(t).strip() for t in (parsed.titles or []) if str(t).strip()]
        return out[:30] if out else _fallback()
    except AiNotConfigured:
        return _fallback()
    except AiError:
        return _fallback()
