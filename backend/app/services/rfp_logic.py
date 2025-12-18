from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def parse_us_date(date_str: Any) -> datetime | None:
    if not isinstance(date_str, str):
        return None
    s = date_str.strip()
    if not s or s.lower() == "not available":
        return None

    try:
        mm, dd, yyyy = s.split("/")
        m = int(mm)
        d = int(dd)
        y = int(yyyy)
    except Exception:
        return None

    if m <= 0 or d <= 0 or y <= 0:
        return None

    try:
        dt = datetime(y, m, d, tzinfo=timezone.utc)
    except Exception:
        return None

    # sanity: ensure components match (e.g. 02/31 invalid)
    if dt.year != y or dt.month != m or dt.day != d:
        return None

    return dt


def days_until(dt: datetime | None, now: datetime | None = None) -> int | None:
    if not dt:
        return None
    now = now or datetime.now(timezone.utc)
    delta = dt - now
    return int((delta.total_seconds() + 86400 - 1) // 86400)


def compute_date_sanity(rfp: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    warnings: list[str] = []
    meta: dict[str, Any] = {"dates": {}}

    fields = [
        ("submissionDeadline", "Submission deadline"),
        ("questionsDeadline", "Questions deadline"),
        ("bidMeetingDate", "Bid meeting date"),
        ("bidRegistrationDate", "Bid registration date"),
        ("projectDeadline", "Project deadline"),
    ]

    for key, label in fields:
        raw = rfp.get(key)
        parsed = parse_us_date(raw)
        if isinstance(raw, str) and raw and raw != "Not available" and not parsed:
            warnings.append(f"{label} looks invalid ({raw}).")
        if parsed:
            du = days_until(parsed, now)
            meta["dates"][key] = {
                "raw": raw,
                "iso": parsed.isoformat().replace("+00:00", "Z"),
                "daysUntil": du,
                "isPast": (du < 0) if du is not None else None,
            }
            if key == "submissionDeadline" and du is not None and du < 0:
                warnings.append(f"{label} appears past ({raw}).")

    return {"warnings": warnings, "meta": meta}


def check_disqualification(rfp: dict[str, Any]) -> bool:
    now = datetime.now(timezone.utc)
    sub = parse_us_date(rfp.get("submissionDeadline"))
    if sub and sub < now:
        return True

    raw = str(rfp.get("rawText") or "").lower()

    is_mandatory_meeting = "mandatory" in raw and any(
        k in raw
        for k in (
            "pre-bid",
            "prebid",
            "pre-proposal",
            "preproposal",
            "site visit",
            "bid conference",
            "pre proposal conference",
        )
    )
    is_mandatory_registration = "mandatory" in raw and any(
        k in raw for k in ("registration", "vendor registration", "bid registration", "register")
    )

    if is_mandatory_meeting:
        meeting = parse_us_date(rfp.get("bidMeetingDate"))
        if meeting and meeting < now:
            return True

    if is_mandatory_registration:
        reg = parse_us_date(rfp.get("bidRegistrationDate"))
        if reg and reg < now:
            return True

    return False


def compute_fit_score(rfp: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    reasons: list[str] = []
    score = 100

    raw = str(rfp.get("rawText") or "").lower()
    sub = parse_us_date(rfp.get("submissionDeadline"))
    q = parse_us_date(rfp.get("questionsDeadline"))
    meeting = parse_us_date(rfp.get("bidMeetingDate"))
    reg = parse_us_date(rfp.get("bidRegistrationDate"))

    if sub and sub < now:
        return {"score": 0, "reasons": ["Submission deadline passed."], "disqualified": True}

    du_sub = days_until(sub, now) if sub else None
    if isinstance(du_sub, int):
        if du_sub <= 7:
            score -= 20
            reasons.append(f"Due soon ({du_sub} days until submission).")
        elif du_sub <= 14:
            score -= 10
            reasons.append(f"Moderately urgent ({du_sub} days until submission).")

    du_q = days_until(q, now) if q else None
    if isinstance(du_q, int) and du_q < 0:
        score -= 10
        reasons.append("Questions deadline appears past.")

    is_mandatory_meeting = "mandatory" in raw and "pre" in raw
    if is_mandatory_meeting:
        if not meeting:
            score -= 10
            reasons.append("Mentions mandatory pre-bid meeting but no meeting date found.")
        else:
            du = days_until(meeting, now)
            if isinstance(du, int) and du < 0:
                return {"score": 0, "reasons": ["Mandatory meeting appears past."], "disqualified": True}
            reasons.append("Mandatory pre-bid meeting detected.")
            score -= 5

    is_mandatory_registration = "mandatory" in raw and "register" in raw
    if is_mandatory_registration:
        if not reg:
            score -= 10
            reasons.append("Mentions mandatory registration but no registration date found.")
        else:
            du = days_until(reg, now)
            if isinstance(du, int) and du < 0:
                return {"score": 0, "reasons": ["Mandatory registration appears past."], "disqualified": True}
            reasons.append("Mandatory registration detected.")
            score -= 5

    if "bid bond" in raw or "performance bond" in raw:
        score -= 10
        reasons.append("Bid/performance bond requirements detected.")

    if any(k in raw for k in ("license", "licensing", "certification")):
        score -= 5
        reasons.append("Licensing/certification requirements detected.")

    score = max(0, min(100, score))
    if not reasons:
        reasons.append("No major risks detected.")

    return {"score": score, "reasons": reasons, "disqualified": False}
