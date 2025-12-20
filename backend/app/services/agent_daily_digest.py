from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from .agent_events_repo import append_event, list_recent_events_global
from .agent_jobs_repo import create_job
from .daily_report_builder import build_northstar_daily_report
from .email_ses import send_text_email
from .slack_web import chat_post_message_result
from ..settings import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _chicago_date_str(now_utc: datetime, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    return now_utc.astimezone(tz).date().isoformat()


def next_daily_digest_due_iso(*, now_utc: datetime | None = None, tz_name: str | None = None) -> str:
    """
    Compute the next 08:00 local-time run in the configured timezone.
    """
    now = now_utc or _utcnow()
    tz = ZoneInfo(str(tz_name or settings.agent_daily_digest_tz or "America/Chicago"))
    local = now.astimezone(tz)
    target = local.replace(hour=8, minute=0, second=0, microsecond=0)
    if local >= target:
        target = target + timedelta(days=1)
    return _iso(target.astimezone(timezone.utc))


def _tool_failure_summary(*, since_iso: str, limit: int = 500) -> list[tuple[str, int]]:
    """
    Summarize tool_call failures from the global AgentEvent log.
    """
    events = list_recent_events_global(since_iso=since_iso, limit=limit)
    counts: dict[str, int] = {}
    for e in events:
        if not isinstance(e, dict):
            continue
        if str(e.get("type") or "") != "tool_call":
            continue
        payload_raw = e.get("payload")
        payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
        ok = bool(payload.get("ok"))
        if ok:
            continue
        tool = str(e.get("tool") or "").strip() or "unknown"
        counts[tool] = counts.get(tool, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]


def build_agent_daily_digest(*, hours: int = 24) -> dict[str, Any]:
    """
    Build the daily digest message (Slack + email text) using durable telemetry.
    """
    h = max(1, min(72, int(hours or 24)))
    end = _utcnow()
    start = end - timedelta(hours=h)
    start_iso = _iso(start)

    base = build_northstar_daily_report(hours=h)
    failures = _tool_failure_summary(since_iso=start_iso, limit=700)

    lines: list[str] = []
    lines.append(f"*Agent daily digest* (last {h}h)")
    lines.append(f"- Window: `{start_iso}` → `{_iso(end)}`")
    lines.append(f"- Events logged: {(base.get('events') or {}).get('count')}")
    if failures:
        lines.append("- Tool failures (non-ok tool_call events):")
        for t, c in failures:
            lines.append(f"  - `{t}`: {c}")
    # Include the existing North Star report as a second section.
    slack_text = str(base.get("slackText") or "").strip()
    if slack_text:
        lines.append("")
        lines.append("*North Star summary*")
        lines.extend(slack_text.splitlines()[1:])  # drop repeated title line

    email_text = "\n".join(lines).strip()
    return {
        "ok": True,
        "window": {"start": start_iso, "end": _iso(end), "hours": h},
        "failures": [{"tool": t, "count": c} for t, c in failures],
        "slackText": "\n".join(lines).strip(),
        "emailText": email_text,
    }


def _already_sent_for_date(*, date_str: str) -> bool:
    # Look back 36h and check for an idempotency marker event.
    since = _iso(_utcnow() - timedelta(hours=36))
    events = list_recent_events_global(since_iso=since, limit=800)
    for e in events:
        if not isinstance(e, dict):
            continue
        if str(e.get("type") or "") != "agent_daily_digest_sent":
            continue
        payload_raw = e.get("payload")
        payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
        if str(payload.get("date") or "").strip() == date_str:
            return True
    return False


@dataclass(frozen=True)
class DigestSendResult:
    ok: bool
    date: str
    slackPosted: bool
    emailSent: bool
    nextDueIso: str


def run_daily_digest_and_reschedule(*, hours: int = 24) -> dict[str, Any]:
    """
    Run the digest now (idempotent per local date), then enqueue the next run.
    """
    tz_name = str(settings.agent_daily_digest_tz or "America/Chicago")
    now = _utcnow()
    date_str = _chicago_date_str(now, tz_name)
    next_due = next_daily_digest_due_iso(now_utc=now, tz_name=tz_name)

    if _already_sent_for_date(date_str=date_str):
        # Still ensure it's scheduled.
        create_job(job_type="agent_daily_digest", scope={"env": settings.normalized_environment}, payload={"hours": hours}, due_at=next_due)
        return DigestSendResult(ok=True, date=date_str, slackPosted=False, emailSent=False, nextDueIso=next_due).__dict__

    digest = build_agent_daily_digest(hours=hours)
    slack_posted = False
    email_sent = False

    channel = (settings.agent_daily_digest_channel or settings.northstar_daily_report_channel or "").strip()
    if channel:
        try:
            chat_post_message_result(channel=channel, text=str(digest.get("slackText") or "").strip() or "Agent daily digest (empty).")
            slack_posted = True
        except Exception:
            slack_posted = False

    to_email = str(settings.agent_daily_digest_email_to or "").strip()
    from_email = str(settings.agent_daily_digest_email_from or "").strip()
    if to_email and from_email:
        try:
            res = send_text_email(
                to_email=to_email,
                from_email=from_email,
                subject=f"Polaris agent daily digest ({date_str})",
                text=str(digest.get("emailText") or "").strip(),
            )
            email_sent = bool(res.get("ok"))
        except Exception:
            email_sent = False

    # Idempotency marker
    try:
        append_event(
            rfp_id="rfp_daily_digest",
            type="agent_daily_digest_sent",
            tool="agent_daily_digest",
            payload={"date": date_str, "slackPosted": slack_posted, "emailSent": email_sent, "window": digest.get("window")},
            created_by="system",
            correlation_id=None,
        )
    except Exception:
        pass

    # Self-reschedule
    create_job(job_type="agent_daily_digest", scope={"env": settings.normalized_environment}, payload={"hours": hours}, due_at=next_due)

    return DigestSendResult(ok=True, date=date_str, slackPosted=slack_posted, emailSent=email_sent, nextDueIso=next_due).__dict__

