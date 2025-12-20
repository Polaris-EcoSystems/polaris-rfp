from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..observability.logging import configure_logging, get_logger
from ..services.agent_events_repo import append_event
from ..services.daily_report_builder import build_northstar_daily_report
from ..services.slack_web import chat_post_message_result
from ..settings import settings


log = get_logger("northstar_daily_report")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_once(*, hours: int = 24) -> dict[str, Any]:
    started_at = _now_iso()
    report = build_northstar_daily_report(hours=hours)

    ch = (settings.northstar_daily_report_channel or "").strip()
    if not ch:
        out = {"ok": False, "startedAt": started_at, "finishedAt": _now_iso(), "error": "NORTHSTAR_DAILY_REPORT_CHANNEL not set"}
        try:
            log.warning("daily_report_skipped", **out)
        except Exception:
            pass
        return out

    # Post to Slack (best-effort) and emit an AgentEvent for auditing.
    txt = str(report.get("slackText") or "").strip()
    try:
        chat_post_message_result(channel=ch, text=txt or "North Star daily report (empty).", blocks=None)
    except Exception as e:
        out = {"ok": False, "startedAt": started_at, "finishedAt": _now_iso(), "error": f"slack_post_failed: {e}"}
        try:
            log.exception("daily_report_failed", **out)
        except Exception:
            pass
        return out

    # Record the fact we posted (not tied to a single rfpId).
    try:
        append_event(
            rfp_id="rfp_daily_report",
            type="northstar_daily_report_posted",
            payload={"channel": ch, "window": report.get("window"), "eventsCount": (report.get("events") or {}).get("count")},
            tool="daily_report_worker",
            policy_checks=[],
            confidence_flags=[],
            downstream_effects=[],
            created_by="system",
            correlation_id=None,
        )
    except Exception:
        pass

    finished_at = _now_iso()
    out = {"ok": True, "startedAt": started_at, "finishedAt": finished_at, "channel": ch, "window": report.get("window")}
    try:
        log.info("daily_report_done", **out)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    configure_logging(level="INFO")
    run_once()

