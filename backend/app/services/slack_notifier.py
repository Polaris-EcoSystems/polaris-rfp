from __future__ import annotations

from ..settings import settings
from .slack_web import post_message


def _rfp_url(rfp_id: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    return f"{base}/rfps/{rfp_id}"

def _proposal_url(proposal_id: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    return f"{base}/proposals/{proposal_id}"


def notify_rfp_upload_job_completed(
    *,
    job_id: str,
    rfp_id: str,
    file_name: str | None = None,
    channel: str | None = None,
) -> None:
    rid = str(rfp_id or "").strip()
    link = f"<{_rfp_url(rid)}|Open RFP>" if rid else "(no rfpId)"
    name = str(file_name or "").strip() or "upload.pdf"
    ch = str(channel or settings.slack_rfp_machine_channel or "").strip() or None
    post_message(
        text=f"RFP upload completed: {link} (job `{job_id}`, file `{name}`)",
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

