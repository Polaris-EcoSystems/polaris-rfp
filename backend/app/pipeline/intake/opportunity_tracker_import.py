from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any


CSV_HEADERS = [
    "Opportunity",
    "Point Person",
    "Support Role",
    "Notes",
    "Date Last Confirmed",
    "Mailing?",
    "Question/Answers",
    "Due Date",
    "Announce Date",
    "Funding Arrives (Assume Win Date+30-45 days)",
    "Value",
    "Entity",
    "Source",
    "Applying Entity",
]


def _truthy(v: str) -> bool:
    s = str(v or "").strip().lower()
    return s in {"y", "yes", "true", "1", "x"}


_MDY_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$")


def _normalize_date(s: str) -> str | None:
    raw = str(s or "").strip()
    if not raw:
        return None
    if raw.lower() in {"tba", "rolling"}:
        return raw
    m = _MDY_RE.match(raw)
    if not m:
        return raw
    mm = int(m.group(1))
    dd = int(m.group(2))
    yy = int(m.group(3))
    if yy < 100:
        yy = 2000 + yy
    try:
        d = date(yy, mm, dd)
        return d.isoformat()
    except Exception:
        return raw


def parse_opportunity_tracker_csv(text: str) -> list[dict[str, Any]]:
    """
    Parse the exported Google Sheets CSV.

    The file has a few “legend” rows at the top, then a header row matching CSV_HEADERS.
    Returns a list of dict rows using those header names.
    """
    s = text or ""
    rdr = csv.reader(io.StringIO(s))
    rows = list(rdr)

    header_idx: int | None = None
    for i, row in enumerate(rows[:50]):
        first = str(row[0] or "").strip() if row else ""
        if first == "Opportunity" and any(str(x or "").strip() == "Due Date" for x in row):
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Could not find Opportunity Tracker header row")

    header = [str(x or "").strip() for x in rows[header_idx]]
    out: list[dict[str, Any]] = []
    for row in rows[header_idx + 1 :]:
        if not row or not any(str(x or "").strip() for x in row):
            continue
        obj = {header[j]: (row[j] if j < len(row) else "") for j in range(len(header))}
        out.append(obj)
    return out


def row_to_rfp_and_tracker(row: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a CSV row to:
    - rfp_analysis (minimal RFP fields to create/update)
    - tracker_patch (OpportunityState.state.tracker patch)
    - due_dates_patch (OpportunityState.state.dueDates patch)
    """
    get = lambda k: str((row or {}).get(k) or "").strip()

    opportunity = get("Opportunity")
    entity = get("Entity")
    applying_entity = get("Applying Entity")

    due_date = _normalize_date(get("Due Date"))
    announce_date = _normalize_date(get("Announce Date"))
    funding_arrives = get("Funding Arrives (Assume Win Date+30-45 days)")
    date_last_confirmed = _normalize_date(get("Date Last Confirmed"))

    rfp_analysis: dict[str, Any] = {
        "title": opportunity or None,
        "clientName": entity or "Unknown Client",
        "submissionDeadline": due_date if isinstance(due_date, str) else None,
        "projectType": "tracker_import",
        # Keep list-y fields present to avoid fit/date computations stumbling on types.
        "keyRequirements": [],
        "deliverables": [],
        "criticalInformation": [],
        "timeline": None,
        "budgetRange": None,
    }

    tracker_patch: dict[str, Any] = {
        "pointPerson": get("Point Person") or None,
        "supportRole": get("Support Role") or None,
        "notes": get("Notes") or None,
        "dateLastConfirmed": date_last_confirmed,
        "mailing": _truthy(get("Mailing?")) if get("Mailing?") else None,
        "qaLink": get("Question/Answers") or None,
        "announceDate": announce_date,
        "fundingArrives": funding_arrives or None,
        "value": get("Value") or None,
        "entity": entity or None,
        "source": get("Source") or None,
        "applyingEntity": applying_entity or None,
    }

    # Remove empty keys.
    tracker_patch = {k: v for k, v in tracker_patch.items() if v is not None and str(v).strip() != ""}

    due_dates_patch: dict[str, Any] = {}
    if isinstance(due_date, str) and due_date.strip():
        due_dates_patch["submissionDeadline"] = due_date

    return {
        "opportunity": opportunity,
        "entity": entity,
        "applyingEntity": applying_entity,
        "dueDate": due_date,
        "rfpAnalysis": rfp_analysis,
        "trackerPatch": tracker_patch,
        "dueDatesPatch": due_dates_patch,
    }


