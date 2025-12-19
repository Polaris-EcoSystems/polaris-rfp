from __future__ import annotations

import io
import json
import re
import time
from typing import Any

import httpx
from openai import OpenAI
from pypdf import PdfReader

from ..observability.logging import get_logger
from ..settings import settings

log = get_logger("rfp_analyzer")


def _openai() -> OpenAI | None:
    # Allow the system to run in a degraded mode (no AI analysis) if OpenAI
    # isn't configured. This is especially useful in initial deployments where
    # secrets may not yet be wired in.
    if not settings.openai_api_key:
        return None
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

    # Many “scanned PDFs” yield a tiny amount of garbage text. Treat that as non-extractable.
    if len(raw_text) < 80:
        raise RuntimeError("No extractable text found")

    def _normalize_analysis(
        *,
        data: dict[str, Any] | None,
        used_ai: bool,
        model: str | None,
        ai_error: str | None = None,
    ) -> dict[str, Any]:
        """
        Ensure a stable schema regardless of model output.
        We do not trust the model to return all keys or correct types.
        """
        d = dict(data or {})

        def _s(v: Any, max_len: int = 5000) -> str:
            s = str(v or "").strip()
            if len(s) > max_len:
                s = s[:max_len]
            return s

        def _arr(v: Any, max_items: int = 50, max_len: int = 300) -> list[str]:
            xs = v if isinstance(v, list) else []
            out: list[str] = []
            for x in xs:
                s = _s(x, max_len=max_len)
                if not s:
                    continue
                if s not in out:
                    out.append(s)
                if len(out) >= max_items:
                    break
            return out

        # Always prefer extracted raw_text over any model-provided rawText.
        d["rawText"] = raw_text[:200000]

        # Required-ish fields (keep conservative defaults).
        d["title"] = _s(d.get("title") or source_name, max_len=300) or "RFP"
        d["clientName"] = _s(d.get("clientName"), max_len=300)
        d["submissionDeadline"] = _s(d.get("submissionDeadline"), max_len=120) or "Not available"
        d["questionsDeadline"] = _s(d.get("questionsDeadline"), max_len=120) or "Not available"
        d["bidMeetingDate"] = _s(d.get("bidMeetingDate"), max_len=120) or "Not available"
        d["bidRegistrationDate"] = _s(d.get("bidRegistrationDate"), max_len=120) or "Not available"
        d["projectDeadline"] = _s(d.get("projectDeadline"), max_len=120) or "Not available"
        d["budgetRange"] = _s(d.get("budgetRange"), max_len=300)
        d["projectType"] = _s(d.get("projectType"), max_len=120)
        d["location"] = _s(d.get("location"), max_len=300)
        d["contactInformation"] = _s(d.get("contactInformation"), max_len=2000)
        d["timeline"] = _arr(d.get("timeline"), max_items=30, max_len=400)
        d["keyRequirements"] = _arr(d.get("keyRequirements"), max_items=40, max_len=400)
        d["deliverables"] = _arr(d.get("deliverables"), max_items=30, max_len=400)
        d["criticalInformation"] = _arr(d.get("criticalInformation"), max_items=30, max_len=500)
        d["clarificationQuestions"] = _arr(d.get("clarificationQuestions"), max_items=30, max_len=400)

        d["_analysis"] = {
            "version": 1,
            "usedAi": bool(used_ai),
            "model": str(model) if model else None,
            "sourceName": str(source_name or ""),
            "extractedChars": len(raw_text),
            "ts": int(time.time()),
        }
        if ai_error:
            d["_analysis"]["aiError"] = str(ai_error)
        return d

    def _fallback_analysis() -> dict[str, Any]:
        """
        Heuristic-only analysis used when AI isn't configured or fails.
        Keeps the upload flow functional and stores rawText for later use.
        """
        import re

        def _clean_title(name: str) -> str:
            nm = (name or "").strip()
            nm = re.sub(r"\.[a-zA-Z0-9]{1,5}$", "", nm)
            nm = nm.replace("_", " ").replace("-", " ").strip()
            nm = re.sub(r"\s+", " ", nm)
            return nm or "RFP"

        # Very small "requirements" extraction: lines containing must/shall/required.
        lines = [ln.strip() for ln in raw_text.splitlines()]
        reqs: list[str] = []
        seen: set[str] = set()
        for ln in lines:
            if not ln or len(ln) > 220:
                continue
            low = ln.lower()
            if any(k in low for k in (" must ", " shall ", " required", " requirement", " requirements")):
                key = low
                if key in seen:
                    continue
                seen.add(key)
                reqs.append(ln)
            if len(reqs) >= 20:
                break

        # Best-effort deadline extraction (MM/DD/YYYY or Month DD, YYYY).
        mmddyyyy = re.compile(r"\b(0?[1-9]|1[0-2])[/-](0?[1-9]|[12][0-9]|3[01])[/-]((?:19|20)?\d{2})\b")
        monthname = re.compile(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"([0-3]?\d)(?:st|nd|rd|th)?(?:,)?\s+((?:19|20)\d{2})\b",
            re.IGNORECASE,
        )

        candidates: list[tuple[int, str]] = []
        for m in mmddyyyy.finditer(raw_text):
            candidates.append((m.start(), f"{m.group(1)}/{m.group(2)}/{m.group(3)}"))
        for m in monthname.finditer(raw_text):
            candidates.append((m.start(), f"{m.group(1)} {m.group(2)}, {m.group(3)}"))
        candidates.sort(key=lambda t: t[0])

        submission_deadline = "Not available"
        questions_deadline = "Not available"
        # Context-based pick: look around each date for keywords.
        for idx, date_str in candidates:
            window = raw_text[max(0, idx - 80) : idx + 80].lower()
            if submission_deadline == "Not available" and any(
                k in window for k in ("submission", "proposal due", "response due", "due date", "bid due")
            ):
                submission_deadline = date_str
            if questions_deadline == "Not available" and any(k in window for k in ("questions due", "questions deadline", "clarification", "inquiries due")):
                questions_deadline = date_str
            if submission_deadline != "Not available" and questions_deadline != "Not available":
                break

        return _normalize_analysis(
            data={
            "title": _clean_title(source_name),
            "clientName": "",
            "submissionDeadline": submission_deadline,
            "questionsDeadline": questions_deadline,
            "bidMeetingDate": "Not available",
            "bidRegistrationDate": "Not available",
            "projectDeadline": "Not available",
            "budgetRange": "",
            "projectType": "",
            "location": "",
            "keyRequirements": reqs,
            "deliverables": [],
            "criticalInformation": [],
            "timeline": [],
            "contactInformation": "",
            "clarificationQuestions": [],
            },
            used_ai=False,
            model=None,
        )

    prompt = (
        "Extract key information from the following RFP text.\n"
        "Return ONLY a single JSON object. No markdown. No prose. No code fences.\n\n"
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

    client = _openai()
    if not client:
        return _fallback_analysis()

    chosen_model = settings.openai_model_for("rfp_analysis")

    def _call_openai(*, model: str, prompt_text: str, force_json: bool) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": 0.0 if force_json else 0.2,
            "max_tokens": 3000,
            "messages": [{"role": "user", "content": prompt_text}],
        }
        if force_json:
            # Prefer models that support JSON-only response enforcement.
            # If unsupported, we'll catch and fall back to best-effort parsing below.
            kwargs["response_format"] = {"type": "json_object"}
        completion = client.chat.completions.create(**kwargs)
        return (completion.choices[0].message.content or "").strip()

    last_content_preview: str | None = None
    last_err: Exception | None = None

    # Try a few times:
    # 1) response_format enforced JSON (best when supported)
    # 2) stricter prompt retry
    # 3) fallback parsing/extraction
    for attempt in range(1, 4):
        try:
            force_json = attempt <= 2
            attempt_prompt = prompt
            if attempt >= 2:
                attempt_prompt = (
                    prompt
                    + "\n\nIMPORTANT: Output must be valid JSON starting with '{' and ending with '}'."
                )

            try:
                content = _call_openai(model=chosen_model, prompt_text=attempt_prompt, force_json=force_json)
            except Exception:
                # If a newer model name is misconfigured/not available, fall back once.
                content = _call_openai(model="gpt-4o-mini", prompt_text=attempt_prompt, force_json=force_json)
                chosen_model = "gpt-4o-mini"

            if not content:
                raise RuntimeError("empty_model_response")

            # Parse JSON. If model returned extra text, extract the first object block.
            try:
                data = json.loads(content)
            except Exception:
                m = re.search(r"\{[\s\S]*\}", content)
                if not m:
                    raise RuntimeError("non_json_model_response")
                data = json.loads(m.group(0))

            if not isinstance(data, dict):
                raise RuntimeError("json_not_object")

            return _normalize_analysis(data=data, used_ai=True, model=chosen_model)
        except Exception as e:
            last_err = e
            last_content_preview = (locals().get("content") or "")[:240]
            log.warning(
                "rfp_ai_json_parse_failed",
                attempt=attempt,
                model=chosen_model,
                error=str(e),
                content_preview=last_content_preview,
            )

    # If AI is flaky/non-JSON, do not fail the upload/job; fall back to heuristic analysis.
    return _normalize_analysis(
        data=_fallback_analysis(),
        used_ai=False,
        model=None,
        ai_error=str(last_err) if last_err else "ai_json_parse_failed",
    )
