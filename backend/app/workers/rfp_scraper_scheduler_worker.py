from __future__ import annotations

from typing import Any

from app.observability.logging import configure_logging, get_logger
from app.pipeline.search.rfp_scraper_job_runner import process_scraper_job
from app.repositories.rfp_scraper_jobs_repo import create_job as create_scraper_job
from app.repositories import rfp_scraper_schedules_repo

log = get_logger("rfp_scraper_scheduler_worker")


def run_once(*, limit: int = 10) -> dict[str, Any]:
    """
    Run due scraper schedules.

    Intended to be invoked from an external scheduler (ECS scheduled task / cron / EventBridge).
    """
    lim = max(1, min(50, int(limit or 10)))
    due = rfp_scraper_schedules_repo.claim_due_schedules(limit=lim)
    scanned = len(due)
    started = 0
    failed = 0

    for sched in due:
        try:
            sid = str(sched.get("scheduleId") or "").strip()
            source = str(sched.get("source") or "").strip()
            search_params = sched.get("searchParams") if isinstance(sched.get("searchParams"), dict) else {}
            if not sid or not source:
                continue

            job = create_scraper_job(source=source, search_params=search_params, user_sub=None)
            started += 1
            try:
                process_scraper_job(job.get("id") or job.get("_id") or job.get("jobId") or "")
            finally:
                # Move nextRunAt forward regardless; failures still advance to avoid rapid retry loops.
                rfp_scraper_schedules_repo.mark_ran(schedule_id=sid)
        except Exception as e:
            failed += 1
            try:
                log.exception("scraper_schedule_run_failed", scheduleId=str(sched.get("scheduleId") or ""), error=str(e))
            except Exception:
                pass

    out = {"ok": True, "scanned": scanned, "started": started, "failed": failed}
    try:
        log.info("rfp_scraper_scheduler_run_once_done", **out)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    configure_logging(level="INFO")
    run_once(limit=10)


