from __future__ import annotations

from typing import Any

from ..observability.logging import configure_logging, get_logger
from ..repositories.outbox_repo import claim_event, list_pending, mark_done, mark_retry

log = get_logger("outbox_worker")


def dispatch_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch a single outbox event.

    This is intentionally small and explicit (no magic registry yet).
    """
    et = str(event.get("eventType") or "").strip()
    payload_raw = event.get("payload")
    payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}

    if et == "slack.task_assigned":
        from ..infrastructure.integrations.slack.slack_notifier import notify_task_assigned

        notify_task_assigned(task=payload.get("task") or {}, actor_user_sub=payload.get("actorUserSub"))
        return {"ok": True}

    if et == "slack.task_completed":
        from ..infrastructure.integrations.slack.slack_notifier import notify_task_completed

        notify_task_completed(task=payload.get("task") or {}, actor_user_sub=payload.get("actorUserSub"))
        return {"ok": True}

    if et == "slack.proposal_created":
        from ..infrastructure.integrations.slack.slack_notifier import notify_proposal_created

        notify_proposal_created(
            proposal_id=str(payload.get("proposalId") or ""),
            rfp_id=str(payload.get("rfpId") or ""),
            title=str(payload.get("title") or ""),
        )
        return {"ok": True}

    if et == "slack.rfp_upload_completed":
        from ..infrastructure.integrations.slack.slack_notifier import notify_rfp_upload_job_completed

        notify_rfp_upload_job_completed(
            job_id=str(payload.get("jobId") or ""),
            rfp_id=str(payload.get("rfpId") or ""),
            file_name=str(payload.get("fileName") or "") or None,
            channel=str(payload.get("channel") or "") or None,
        )
        return {"ok": True}

    if et == "slack.rfp_upload_failed":
        from ..infrastructure.integrations.slack.slack_notifier import notify_rfp_upload_job_failed

        notify_rfp_upload_job_failed(
            job_id=str(payload.get("jobId") or ""),
            error=str(payload.get("error") or "upload_failed"),
            file_name=str(payload.get("fileName") or "") or None,
            channel=str(payload.get("channel") or "") or None,
        )
        return {"ok": True}

    return {"ok": False, "error": "unknown_event_type", "eventType": et}


def run_once(*, limit: int = 30) -> dict[str, Any]:
    """
    Best-effort outbox dispatcher. Safe to run from cron/ECS scheduled task.
    """
    lim = max(1, min(100, int(limit or 30)))
    scanned = 0
    processed = 0
    failed = 0

    pg = list_pending(limit=lim, next_token=None)
    items = pg.get("items") or []
    for it in items:
        scanned += 1
        if not isinstance(it, dict):
            continue
        eid = str(it.get("eventId") or "").strip()
        if not eid:
            continue
        try:
            claimed = claim_event(event_id=eid)
        except Exception:
            claimed = None
        if not claimed:
            continue
        try:
            res = dispatch_event(claimed)
            if res.get("ok"):
                processed += 1
                mark_done(event_id=eid, result=res if isinstance(res, dict) else None)
            else:
                failed += 1
                mark_retry(event_id=eid, error=str(res.get("error") or "dispatch_failed"))
        except Exception as e:
            failed += 1
            try:
                mark_retry(event_id=eid, error=str(e) or "dispatch_failed")
            except Exception:
                pass

    out = {"ok": True, "scanned": scanned, "processed": processed, "failed": failed}
    try:
        log.info("outbox_run_once_done", **out)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    configure_logging(level="INFO")
    run_once(limit=30)


