from __future__ import annotations

from typing import Any

from ...settings import settings
from ...repositories.rfp.rfps_repo import get_rfp_by_id
from .slack_secrets import get_secret_str
from .sessions_repo import list_sessions_for_user
from .slack_web import (
    chat_post_message_result,
    lookup_user_id_by_email,
    open_dm_channel,
    post_message,
    post_message_result,
)
from ...observability.logging import get_logger


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


def _slack_markdown_table(rows: list[tuple[str, str]]) -> str:
    """
    Render a simple two-column "table" using Slack mrkdwn in a code block.
    Slack does not reliably render GitHub-style tables, but code blocks preserve
    alignment and are readable in-channel.
    """
    clean = [(str(k).strip(), str(v).strip()) for (k, v) in rows if str(v).strip()]
    if not clean:
        return ""

    h1, h2 = "Field", "Value"
    w1 = max(len(h1), *(len(k) for (k, _v) in clean))
    # Keep the value column bounded so the message stays compact.
    def _clip(s: str, n: int = 120) -> str:
        s = str(s or "").strip()
        return s if len(s) <= n else (s[: n - 1] + "…")

    lines: list[str] = []
    lines.append(f"{h1:<{w1}} | {h2}")
    lines.append(f"{'-' * w1}-+-{'-' * max(5, len(h2))}")
    for k, v in clean:
        lines.append(f"{k:<{w1}} | {_clip(v)}")
    return "```\n" + "\n".join(lines) + "\n```"

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
    header = (
        f"New RFP uploaded: {link} `{rid}`" if rid else f"New RFP uploaded: {link}"
    )
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
        ("File", name),
        ("Job", jid),
    ]

    table = _slack_markdown_table(details)
    if table:
        lines.append(table)
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
    ch = (
        str(channel or "").strip()
        or str(settings.slack_rfp_machine_channel or "").strip()
        or str(get_secret_str("SLACK_RFP_MACHINE_CHANNEL") or "").strip()
        or None
    )
    log = get_logger("slack_notifier")
    res = post_message_result(
        text=_format_rfp_upload_summary(rfp_id=rid, file_name=name, job_id=job_id),
        channel=ch,
        unfurl_links=False,
    )
    if not bool(res.get("ok")):
        log.warning(
            "slack_rfp_machine_notify_failed",
            job_id=str(job_id or "") or None,
            rfp_id=rid or None,
            channel=str(res.get("channel") or ch or "") or None,
            error=str(res.get("error") or "") or None,
            status_code=int(res.get("status_code") or 0) or None,
        )
    else:
        log.info(
            "slack_rfp_machine_notify_ok",
            job_id=str(job_id or "") or None,
            rfp_id=rid or None,
            channel=str(res.get("channel") or ch or "") or None,
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
    ch = (
        str(channel or "").strip()
        or str(settings.slack_rfp_machine_channel or "").strip()
        or str(get_secret_str("SLACK_RFP_MACHINE_CHANNEL") or "").strip()
        or None
    )
    log = get_logger("slack_notifier")
    res = post_message_result(
        text=f"RFP upload failed (job `{job_id}`, file `{name}`): {err}",
        channel=ch,
    )
    if not bool(res.get("ok")):
        log.warning(
            "slack_rfp_machine_notify_failed",
            job_id=str(job_id or "") or None,
            rfp_id=None,
            channel=str(res.get("channel") or ch or "") or None,
            error=str(res.get("error") or "") or None,
            status_code=int(res.get("status_code") or 0) or None,
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


def _slack_rfp_machine_channel() -> str | None:
    ch = (
        str(settings.slack_rfp_machine_channel or "").strip()
        or str(get_secret_str("SLACK_RFP_MACHINE_CHANNEL") or "").strip()
        or None
    )
    return ch


def _assignee_email_for_sub(user_sub: str) -> str | None:
    sub = str(user_sub or "").strip()
    if not sub:
        return None
    try:
        sessions = list_sessions_for_user(sub=sub, limit=10)
        for s in sessions or []:
            if not isinstance(s, dict):
                continue
            em = str(s.get("email") or "").strip().lower()
            if em and "@" in em:
                return em
    except Exception:
        return None
    return None


def notify_task_assigned(*, task: dict[str, Any], actor_user_sub: str | None = None) -> None:
    """
    Notify #rfp-machine and DM the assignee (best-effort).
    """
    log = get_logger("slack_notifier")
    ch = _slack_rfp_machine_channel()
    if not ch:
        return

    rfp_id = str(task.get("rfpId") or "").strip()
    task_id = str(task.get("taskId") or task.get("_id") or "").strip()
    title = str(task.get("title") or "Task").strip() or "Task"
    due = str(task.get("dueAt") or "").strip()
    assignee_sub = str(task.get("assigneeUserSub") or "").strip()
    assignee_name = str(task.get("assigneeDisplayName") or "").strip() or assignee_sub or "Unassigned"

    rfp = None
    try:
        rfp = get_rfp_by_id(rfp_id) if rfp_id else None
    except Exception:
        rfp = None
    rfp_title = str((rfp or {}).get("title") or "RFP").strip() if isinstance(rfp, dict) else "RFP"
    rfp_link = f"<{_rfp_url(rfp_id)}|{rfp_title}>" if rfp_id else "RFP"

    due_part = f" (due {due})" if due else ""
    actor_part = f" by `{actor_user_sub}`" if actor_user_sub else ""
    text = f"Task assigned{actor_part}: *{title}* → *{assignee_name}*{due_part}\n{rfp_link} `{rfp_id}`"

    res = post_message_result(text=text, channel=ch, unfurl_links=False)
    if not bool(res.get("ok")):
        log.warning(
            "slack_task_assigned_channel_failed",
            task_id=task_id or None,
            rfp_id=rfp_id or None,
            channel=str(res.get("channel") or ch or "") or None,
            error=str(res.get("error") or "") or None,
        )

    # DM assignee (lookup by email via session table, then Slack users.lookupByEmail)
    if not assignee_sub:
        return
    email = _assignee_email_for_sub(assignee_sub)
    if not email:
        return
    slack_uid = lookup_user_id_by_email(email)
    if not slack_uid:
        return
    dm_channel = open_dm_channel(user_id=slack_uid)
    if not dm_channel:
        return

    dm_text = f"You were assigned: *{title}*{due_part}\n{rfp_link}"
    dm_res = chat_post_message_result(text=dm_text, channel=dm_channel, unfurl_links=False)
    if not bool(dm_res.get("ok")):
        log.warning(
            "slack_task_assigned_dm_failed",
            task_id=task_id or None,
            rfp_id=rfp_id or None,
            assignee_sub=assignee_sub or None,
            error=str(dm_res.get("error") or "") or None,
        )


def notify_review_assigned(*, rfp: dict[str, Any], actor_user_sub: str | None = None) -> None:
    """
    Notify #rfp-machine and DM the assignee when a review is assigned (best-effort).
    """
    log = get_logger("slack_notifier")
    ch = _slack_rfp_machine_channel()
    if not ch:
        return

    rfp_id = str(rfp.get("_id") or rfp.get("rfpId") or "").strip()
    rfp_title = str(rfp.get("title") or "RFP").strip() or "RFP"
    review_raw = rfp.get("review")
    review: dict[str, Any] = review_raw if isinstance(review_raw, dict) else {}
    assignee_sub = str(review.get("assignedReviewerUserSub") or "").strip()
    
    if not assignee_sub:
        return  # No assignee to notify
    
    rfp_link = f"<{_rfp_url(rfp_id)}|{rfp_title}>" if rfp_id else "RFP"
    actor_part = f" by `{actor_user_sub}`" if actor_user_sub else ""
    text = f"Review assigned{actor_part}: *{rfp_title}* → *{assignee_sub}*\n{rfp_link} `{rfp_id}`"

    res = post_message_result(text=text, channel=ch, unfurl_links=False)
    if not bool(res.get("ok")):
        log.warning(
            "slack_review_assigned_channel_failed",
            rfp_id=rfp_id or None,
            channel=str(res.get("channel") or ch or "") or None,
            error=str(res.get("error") or "") or None,
        )

    # DM assignee (lookup by email via session table, then Slack users.lookupByEmail)
    email = _assignee_email_for_sub(assignee_sub)
    if not email:
        return
    slack_uid = lookup_user_id_by_email(email)
    if not slack_uid:
        return
    dm_channel = open_dm_channel(user_id=slack_uid)
    if not dm_channel:
        return

    dm_text = f"You were assigned to review: *{rfp_title}*\n{rfp_link}"
    dm_res = chat_post_message_result(text=dm_text, channel=dm_channel, unfurl_links=False)
    if not bool(dm_res.get("ok")):
        log.warning(
            "slack_review_assigned_dm_failed",
            rfp_id=rfp_id or None,
            assignee_sub=assignee_sub or None,
            error=str(dm_res.get("error") or "") or None,
        )


def notify_task_completed(*, task: dict[str, Any], actor_user_sub: str | None) -> None:
    """
    Notify #rfp-machine when a task is completed (best-effort).
    """
    log = get_logger("slack_notifier")
    ch = _slack_rfp_machine_channel()
    if not ch:
        return

    rfp_id = str(task.get("rfpId") or "").strip()
    task_id = str(task.get("taskId") or task.get("_id") or "").strip()
    title = str(task.get("title") or "Task").strip() or "Task"
    assignee_name = str(task.get("assigneeDisplayName") or "").strip() or str(task.get("assigneeUserSub") or "").strip()
    rfp = None
    try:
        rfp = get_rfp_by_id(rfp_id) if rfp_id else None
    except Exception:
        rfp = None
    rfp_title = str((rfp or {}).get("title") or "RFP").strip() if isinstance(rfp, dict) else "RFP"
    rfp_link = f"<{_rfp_url(rfp_id)}|{rfp_title}>" if rfp_id else "RFP"

    who = f"`{actor_user_sub}`" if actor_user_sub else "Someone"
    assigned_part = f" (assigned to {assignee_name})" if assignee_name else ""
    text = f"Task completed by {who}: *{title}*{assigned_part}\n{rfp_link} `{rfp_id}`"

    res = post_message_result(text=text, channel=ch, unfurl_links=False)
    if not bool(res.get("ok")):
        log.warning(
            "slack_task_completed_channel_failed",
            task_id=task_id or None,
            rfp_id=rfp_id or None,
            channel=str(res.get("channel") or ch or "") or None,
            error=str(res.get("error") or "") or None,
        )

