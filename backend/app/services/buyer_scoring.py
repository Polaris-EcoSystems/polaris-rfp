from __future__ import annotations

import re
from typing import Any

from openai import OpenAI

from ..settings import settings


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def score_buyer_likelihood(
    *,
    title: str | None,
    target_titles: list[str] | None = None,
) -> tuple[int, list[str]]:
    t = _norm(title)
    reasons: list[str] = []

    if not t:
        return 10, ["Missing job title"]

    score = 20

    senior = [
        ("chief", 30),
        ("cfo", 30),
        ("coo", 30),
        ("ceo", 25),
        ("svp", 25),
        ("evp", 25),
        ("vp", 22),
        ("vice president", 22),
        ("head", 18),
        ("director", 16),
        ("principal", 14),
        ("manager", 10),
        ("lead", 8),
    ]
    for kw, pts in senior:
        if kw in t:
            score += pts
            reasons.append(f"Seniority keyword: {kw}")
            break

    buying_functions = [
        ("procurement", 22),
        ("purchasing", 18),
        ("sourcing", 16),
        ("supply chain", 14),
        ("operations", 12),
        ("finance", 12),
        ("facilities", 10),
        ("it", 10),
        ("technology", 10),
        ("security", 10),
        ("sustainability", 10),
        ("environment", 8),
        ("energy", 8),
        ("program", 8),
        ("project", 8),
    ]
    for kw, pts in buying_functions:
        if kw in t:
            score += pts
            reasons.append(f"Buying function keyword: {kw}")
            break

    non_buyer = [
        "intern",
        "student",
        "recruiter",
        "talent",
        "hr",
        "human resources",
        "assistant",
    ]
    for kw in non_buyer:
        if kw in t:
            score -= 20
            reasons.append(f"Non-buyer keyword: {kw}")
            break

    targets = [tt.strip().lower() for tt in (target_titles or []) if str(tt).strip()]
    for tt in targets:
        if tt and tt in t:
            score += 15
            reasons.append(f"Matched target title: {tt}")
            break

    score = max(0, min(100, int(score)))
    if not reasons:
        reasons.append("No strong signals; default heuristic score")
    return score, reasons


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=settings.openai_api_key)


def enrich_buyer_profile_with_ai(
    *,
    person: dict[str, Any],
    company_name: str | None,
    rfp: dict[str, Any] | None,
) -> dict[str, Any]:
    if not settings.openai_api_key:
        return person

    title = str(person.get("title") or "")
    name = str(person.get("name") or "")
    location = str(person.get("location") or "")
    profile_url = str(person.get("profileUrl") or "")

    rfp_title = str((rfp or {}).get("title") or "")
    project_type = str((rfp or {}).get("projectType") or "")
    key_reqs = (rfp or {}).get("keyRequirements") or []
    if not isinstance(key_reqs, list):
        key_reqs = []

    prompt = (
        "You are helping write a proposal response. Given a potential buyer at a target organization, "
        "produce a concise buyer profile that helps tailor messaging.\n\n"
        "Return JSON ONLY with keys:\n"
        "- personaSummary (string, 2-4 sentences)\n"
        "- likelyGoals (array of 3-6 strings)\n"
        "- likelyConcerns (array of 3-6 strings)\n"
        "- bestAngles (array of 3-6 strings)\n\n"
        f"Company: {company_name or ''}\n"
        f"RFP Title: {rfp_title}\n"
        f"Project Type: {project_type}\n"
        f"Key Requirements: {key_reqs[:10]}\n\n"
        f"Person:\n- name: {name}\n- title: {title}\n- location: {location}\n- profileUrl: {profile_url}\n"
    )

    completion = _client().chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )
    content = (completion.choices[0].message.content or "").strip()

    import json

    try:
        data = json.loads(content)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            return person
        data = json.loads(m.group(0))

    if isinstance(data, dict):
        person = dict(person)
        person["ai"] = data
    return person


