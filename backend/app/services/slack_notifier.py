from __future__ import annotations

from typing import Any

from ..settings import settings
from .rfps_repo import get_rfp_by_id
from .slack_web import post_message


def _rfp_url(rfp_id: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    return f"{base}/rfps/{rfp_id}"

def _proposal_url(proposal_id: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    return f"{base}/proposals/{proposal_id}"

def _present(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if s.lower() in {"not available", "n/a", "na", "none", "null"}:
        return ""
    return s

def _format_rfp_upload_summary(*, rfp_id: str, file_name: str, job_id: str) -> str:
    rid = str(rfp_id or "").strip()
    name = str(file_name or "").strip() or "upload.pdf"
    jid = str(job_id or "").strip() or "unknown"

    # Best-effort: enrich message with RFP fields.
    rfp: dict[str, Any] | None = None
    try:
        rfp = get_rfp_by_id(rid) if rid else None
    except Exception:
        rfp = None

    title = _present(((rfp or {}).get("title") or "RFP") if isinstance(rfp, dict) else "RFP") or "RFP"
    client = _present(((rfp or {}).get("clientName") or "") if isinstance(rfp, dict) else "")
    ptype = _present(((rfp or {}).get("projectType") or "") if isinstance(rfp, dict) else "")
    budget = _present(((rfp or {}).get("budgetRange") or "") if isinstance(rfp, dict) else "")
    location = _present(((rfp or {}).get("location") or "") if isinstance(rfp, dict) else "")
    due = _present(((rfp or {}).get("submissionDeadline") or "") if isinstance(rfp, dict) else "")
    questions_due = _present(((rfp or {}).get("questionsDeadline") or "") if isinstance(rfp, dict) else "")
    meeting = _present(((rfp or {}).get("bidMeetingDate") or "") if isinstance(rfp, dict) else "")
    registration = _present(((rfp or {}).get("bidRegistrationDate") or "") if isinstance(rfp, dict) else "")
    project_deadline = _present(((rfp or {}).get("projectDeadline") or "") if isinstance(rfp, dict) else "")

    link = f"<{_rfp_url(rid)}|{title}>" if rid else "RFP"

    lines: list[str] = []
    header = f"New RFP uploaded: {link} `{rid}`" if rid else f"New RFP uploaded: {link}"
    lines.append(header)

    details: list[tuple[str, str]] = [
        ("Client", client),
        ("Project type", ptype),
        ("Budget", budget),
        ("Submission due", due),
        ("Questions due", questions_due),
        ("Bid meeting", meeting),
        ("Registration", registration),
        ("Project deadline", project_deadline),
        ("Location", location),
    ]
    for label, val in details:
        if val:
            lines.append(f"• *{label}:* {val}")

    lines.append(f"• *File:* `{name}`")
    lines.append(f"• *Job:* `{jid}`")
    return "\n".join(lines)


def notify_rfp_upload_job_completed(
    *,
    job_id: str,
    rfp_id: str,
    file_name: str | None = None,
    channel: str | None = None,
) -> None:
    rid = str(rfp_id or "").strip()
    name = str(file_name or "").strip() or "upload.pdf"
    ch = str(channel or settings.slack_rfp_machine_channel or "").strip() or None
    post_message(
        text=_format_rfp_upload_summary(rfp_id=rid, file_name=name, job_id=job_id),
        channel=ch,
        unfurl_links=False,
    )


def notify_rfp_upload_job_failed(
    *,
    job_id: str,
    error: str,
    file_name: str | None = None,
    channel: str | None = None,
) -> None:
    name = str(file_name or "").strip() or "upload.pdf"
    err = str(error or "").strip() or "Unknown error"
    ch = str(channel or settings.slack_rfp_machine_channel or "").strip() or None
    post_message(
        text=f"RFP upload failed (job `{job_id}`, file `{name}`): {err}",
        channel=ch,
    )


def notify_finder_run_done(
    *,
    run_id: str,
    rfp_id: str,
    company_name: str | None,
    discovered: int,
    saved: int,
) -> None:
    rid = str(rfp_id or "").strip()
    link = f"<{_rfp_url(rid)}|Open RFP>" if rid else "(no rfpId)"
    company = str(company_name or "").strip() or "Unknown company"
    post_message(
        text=f"Finder run completed for *{company}*: {link} (run `{run_id}`, discovered {int(discovered)}, saved {int(saved)})"
    )


def notify_finder_run_error(*, run_id: str, rfp_id: str, error: str) -> None:
    rid = str(rfp_id or "").strip()
    link = f"<{_rfp_url(rid)}|Open RFP>" if rid else "(no rfpId)"
    err = str(error or "").strip() or "Unknown error"
    post_message(text=f"Finder run failed: {link} (run `{run_id}`): {err}")


def notify_proposal_created(*, proposal_id: str, rfp_id: str, title: str) -> None:
    pid = str(proposal_id or "").strip()
    rid = str(rfp_id or "").strip()
    t = str(title or "").strip() or "Proposal"
    plink = f"<{_proposal_url(pid)}|Open proposal>" if pid else "(no proposalId)"
    rlink = f"<{_rfp_url(rid)}|Open RFP>" if rid else "(no rfpId)"
    post_message(text=f"Proposal created: *{t}* — {plink} • {rlink}")

