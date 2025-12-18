from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from ..settings import settings


def generate_section_titles(rfp: dict[str, Any]) -> list[str]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    client = OpenAI(api_key=settings.openai_api_key)

    prompt = (
        "Given the following RFP summary, propose a concise list of proposal section titles.\n"
        "Return JSON ONLY: {\"titles\": [\"...\", ...]}.\n\n"
        f"RFP_TITLE: {rfp.get('title') or ''}\n"
        f"CLIENT: {rfp.get('clientName') or ''}\n"
        f"PROJECT_TYPE: {rfp.get('projectType') or ''}\n"
        f"KEY_REQUIREMENTS: {', '.join(rfp.get('keyRequirements') or [])}\n"
        f"DELIVERABLES: {', '.join(rfp.get('deliverables') or [])}\n"
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    content = (completion.choices[0].message.content or "").strip()

    try:
        data = json.loads(content)
        titles = data.get("titles")
        if isinstance(titles, list):
            out = [str(t).strip() for t in titles if str(t).strip()]
            return out[:30]
    except Exception:
        pass

    # fallback: split lines
    lines = [ln.strip("-•* \t") for ln in content.splitlines()]
    lines = [ln for ln in lines if ln]
    return lines[:30]
