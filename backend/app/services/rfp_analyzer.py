from __future__ import annotations

import io
import json
from typing import Any

import httpx
from openai import OpenAI
from pypdf import PdfReader

from ..settings import settings


def _openai() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=settings.openai_api_key)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join([p for p in parts if p]).strip()


def _extract_text_from_url(url: str) -> tuple[str, str]:
    # returns (content_type, text)
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        r = client.get(url)
        r.raise_for_status()
        ct = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        data = r.content

    if ct == "application/pdf" or url.lower().endswith(".pdf"):
        return ct or "application/pdf", _extract_pdf_text(data)

    # crude HTML -> text fallback
    try:
        html = data.decode("utf-8", errors="ignore")
    except Exception:
        html = str(data)

    # drop tags quickly
    text = (
        html.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("</p>", "\n")
    )
    # remove remaining tags
    import re

    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return ct or "text/html", text


def analyze_rfp(source: Any, source_name: str) -> dict[str, Any]:
    """Analyze an RFP from URL string, raw PDF bytes, or extracted text."""

    raw_text = ""

    if isinstance(source, (bytes, bytearray)):
        # Assume PDF bytes
        raw_text = _extract_pdf_text(bytes(source))
    elif isinstance(source, str) and source.strip().lower().startswith(("http://", "https://")):
        _, raw_text = _extract_text_from_url(source.strip())
    else:
        raw_text = str(source or "")

    raw_text = raw_text.strip()
    if not raw_text:
        raise RuntimeError("No extractable text found")

    prompt = (
        "Extract key information from the following RFP text and return JSON only.\n\n"
        "Return a JSON object with these keys (use empty string, empty list, or 'Not available' if unknown):\n"
        "- title (string)\n"
        "- clientName (string)\n"
        "- submissionDeadline (MM/DD/YYYY or 'Not available')\n"
        "- questionsDeadline (MM/DD/YYYY or 'Not available')\n"
        "- bidMeetingDate (MM/DD/YYYY or 'Not available')\n"
        "- bidRegistrationDate (MM/DD/YYYY or 'Not available')\n"
        "- projectDeadline (MM/DD/YYYY or 'Not available')\n"
        "- budgetRange (string)\n"
        "- projectType (string)\n"
        "- location (string)\n"
        "- keyRequirements (array of strings)\n"
        "- deliverables (array of strings)\n"
        "- criticalInformation (array of strings)\n"
        "- timeline (array of strings)\n"
        "- contactInformation (string)\n"
        "- clarificationQuestions (array of strings)\n\n"
        "Also include rawText as a truncated copy (<= 200000 chars).\n\n"
        f"SOURCE_NAME: {source_name}\n\n"
        f"RFP_TEXT:\n{raw_text[:200000]}"
    )

    completion = _openai().chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    content = (completion.choices[0].message.content or "").strip()

    # best-effort JSON parse
    try:
        data = json.loads(content)
    except Exception:
        # attempt to find first {...}
        import re

        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            raise RuntimeError("AI analysis did not return JSON")
        data = json.loads(m.group(0))

    if not isinstance(data, dict):
        raise RuntimeError("AI analysis JSON was not an object")

    data["rawText"] = str(data.get("rawText") or raw_text[:200000])
    return data
