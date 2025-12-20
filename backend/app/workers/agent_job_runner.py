from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..observability.logging import configure_logging, get_logger
from ..services.agent_events_repo import append_event
from ..services.agent_jobs_repo import (
    claim_due_jobs,
    complete_job,
    fail_job,
    try_mark_running,
)
from ..services.opportunity_state_repo import ensure_state_exists, patch_state, seed_from_platform
from ..services.opportunity_compactor import run_opportunity_compaction
from ..services.agent_daily_digest import run_daily_digest_and_reschedule
from ..services.agent_self_improve import run_perch_time_once
from ..services.slack_reply_tools import post_summary
from ..services.self_modify_pipeline import get_pr_checks, open_pr_for_change_proposal, verify_ecs_rollout
from ..services.slack_web import chat_post_message_result
from ..services.slack_agent import run_slack_agent_question
from ..settings import settings


log = get_logger("agent_job_runner")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _job_scope_rfp_id(job: dict[str, Any]) -> str | None:
    raw_scope = job.get("scope")
    scope: dict[str, Any] = raw_scope if isinstance(raw_scope, dict) else {}
    rid = str(scope.get("rfpId") or "").strip()
    return rid or None


def _report_to_slack(summary: dict[str, Any]) -> None:
    """
    Report job runner execution summary to Slack channel.
    Uses NORTHSTAR_DAILY_REPORT_CHANNEL or SLACK_RFP_MACHINE_CHANNEL as fallback.
    """
    channel = (
        str(settings.northstar_daily_report_channel or "").strip()
        or str(settings.slack_rfp_machine_channel or "").strip()
        or None
    )
    if not channel or not bool(settings.slack_enabled):
        log.info("agent_job_runner_skip_slack_report", reason="no_channel_or_slack_disabled", channel=channel)
        return

    started = summary.get("startedAt", "unknown")
    finished = summary.get("finishedAt", "unknown")
    batches = int(summary.get("batches", 0) or 0)
    ran = int(summary.get("ran", 0) or 0)
    completed = int(summary.get("completed", 0) or 0)
    failed = int(summary.get("failed", 0) or 0)

    text_lines = [
        "*NorthStar Job Runner Summary*",
        f"- Started: {started}",
        f"- Finished: {finished}",
        f"- Batches processed: {batches}",
        f"- Jobs attempted: {ran}",
        f"- Completed: {completed}",
        f"- Failed: {failed}",
    ]
    if ran == 0:
        text_lines.append("_No jobs processed this run._")

    text = "\n".join(text_lines)

    try:
        result = chat_post_message_result(text=text, channel=channel, unfurl_links=False)
        if result.get("ok"):
            log.info("agent_job_runner_slack_report_sent", channel=channel)
        else:
            log.warning("agent_job_runner_slack_report_failed", channel=channel, error=result.get("error"))
    except Exception as e:
        log.warning("agent_job_runner_slack_report_exception", channel=channel, error=str(e))


def run_once(*, limit: int = 25) -> dict[str, Any]:
    """
    Execute due agent jobs. Intended to run as a scheduled ECS task.
    Keeps processing jobs until there are no more due jobs remaining.
    """
    started_at = _now_iso()
    lim = max(1, min(100, int(limit or 25)))
    
    # Track totals across all batches
    total_ran = 0
    total_completed = 0
    total_failed = 0
    batches_processed = 0

    # Loop until no more jobs are found
    while True:
        batch_start = _now_iso()
        due = claim_due_jobs(now_iso=batch_start, limit=lim)
        
        if not due or len(due) == 0:
            # No more jobs, exit the loop
            break
        
        batches_processed += 1
        ran = 0
        completed = 0
        failed = 0

        for job in due:
            if not isinstance(job, dict):
                continue
            jid = str(job.get("jobId") or job.get("_id") or "").strip()
            if not jid:
                continue
            locked = try_mark_running(job_id=jid)
            if not locked:
                continue
            ran += 1

            job_type = str(job.get("jobType") or "").strip()
            rid = _job_scope_rfp_id(job) or ""
            raw_payload = job.get("payload")
            payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}

            try:
                if rid:
                    ensure_state_exists(rfp_id=rid)

                # Minimal initial job types. More can be added as playbooks evolve.
                if job_type in ("opportunity_maintenance", "perch_refresh"):
                    if not rid:
                        raise RuntimeError("missing_scope_rfpId")
                    seed = seed_from_platform(rfp_id=rid)
                    patch_state(
                        rfp_id=rid,
                        patch={
                            "stage": seed.get("stage"),
                            "dueDates": seed.get("dueDates") if isinstance(seed.get("dueDates"), dict) else {},
                            "proposalIds": seed.get("proposalIds") if isinstance(seed.get("proposalIds"), list) else [],
                            "contractingCaseId": seed.get("contractingCaseId"),
                        },
                        updated_by_user_sub=None,
                        create_snapshot=False,
                    )
                    complete_job(job_id=jid, result={"ok": True, "refreshed": True})
                    completed += 1
                    continue

                if job_type == "agent_daily_digest":
                    # Global, not tied to an RFP.
                    hours = int(payload.get("hours") or 24)
                    res = run_daily_digest_and_reschedule(hours=hours)
                    complete_job(job_id=jid, result=res)
                    completed += 1
                    continue

                if job_type in ("agent_perch_time", "telemetry_self_improve"):
                    hours = int(payload.get("hours") or 6)
                    resched = payload.get("rescheduleMinutes")
                    res = run_perch_time_once(hours=hours, reschedule_minutes=int(resched) if resched is not None else 60)
                    complete_job(job_id=jid, result=res)
                    completed += 1
                    continue

                if job_type == "slack_nudge":
                    if not rid:
                        raise RuntimeError("missing_scope_rfpId")
                    channel = str(payload.get("channel") or "").strip()
                    thread_ts = str(payload.get("threadTs") or "").strip() or None
                    text = str(payload.get("text") or "").strip()
                    if not channel or not text:
                        raise RuntimeError("missing_channel_or_text")
                    post_summary(rfp_id=rid, channel=channel, thread_ts=thread_ts, text=text)
                    complete_job(job_id=jid, result={"ok": True, "posted": True})
                    completed += 1
                    continue

                if job_type in ("opportunity_compact", "memory_compact"):
                    if not rid:
                        raise RuntimeError("missing_scope_rfpId")
                    res = run_opportunity_compaction(rfp_id=rid, journal_limit=int(payload.get("journalLimit") or 25))
                    complete_job(job_id=jid, result=res)
                    completed += 1
                    continue

                if job_type == "self_modify_open_pr":
                    proposal_id = str(payload.get("proposalId") or "").strip()
                    actor = str(payload.get("_actorSlackUserId") or "").strip()
                    channel = str(payload.get("channelId") or "").strip()
                    thread_ts = str(payload.get("threadTs") or "").strip() or None
                    rfp_id = str(payload.get("rfpId") or "").strip() or rid or None
                    if not proposal_id or not actor:
                        raise RuntimeError("missing_proposalId_or_actor")
                    res = open_pr_for_change_proposal(
                        proposal_id=proposal_id,
                        actor_slack_user_id=actor,
                        rfp_id=rfp_id,
                    )
                    if channel and thread_ts:
                        try:
                            if res.get("ok"):
                                txt = f"Opened PR for change proposal `{proposal_id}`:\n- {res.get('prUrl')}"
                            else:
                                txt = f"PR creation failed for `{proposal_id}`: `{res.get('error')}`"
                            if rfp_id:
                                post_summary(rfp_id=rfp_id, channel=channel, thread_ts=thread_ts, text=txt)
                            else:
                                chat_post_message_result(text=txt, channel=channel, thread_ts=thread_ts, unfurl_links=False)
                        except Exception:
                            pass
                    complete_job(job_id=jid, result=res)
                    completed += 1
                    continue

                if job_type == "self_modify_check_pr":
                    pr = str(payload.get("pr") or payload.get("prUrl") or payload.get("prNumber") or "").strip()
                    channel = str(payload.get("channelId") or "").strip()
                    thread_ts = str(payload.get("threadTs") or "").strip() or None
                    rfp_id = str(payload.get("rfpId") or "").strip() or rid or None
                    if not pr:
                        raise RuntimeError("missing_pr")
                    res = get_pr_checks(pr_url_or_number=pr)
                    if channel and thread_ts and res.get("ok"):
                        try:
                            summary_raw = res.get("checksSummary")
                            summary: dict[str, Any] = summary_raw if isinstance(summary_raw, dict) else {}
                            txt = (
                                f"PR checks status:\n"
                                f"- total: {summary.get('total')}\n"
                                f"- pass: {summary.get('pass')}\n"
                                f"- fail: {summary.get('fail')}\n"
                                f"- pending: {summary.get('pending')}\n"
                                f"- pr: {((res.get('pr') or {}) if isinstance(res.get('pr'), dict) else {}).get('url')}"
                            )
                            if rfp_id:
                                post_summary(rfp_id=rfp_id, channel=channel, thread_ts=thread_ts, text=txt)
                            else:
                                chat_post_message_result(text=txt, channel=channel, thread_ts=thread_ts, unfurl_links=False)
                        except Exception:
                            pass
                    complete_job(job_id=jid, result=res)
                    completed += 1
                    continue

                if job_type == "self_modify_verify_ecs":
                    timeout_s = int(payload.get("timeoutSeconds") or 600)
                    poll_s = int(payload.get("pollSeconds") or 10)
                    channel = str(payload.get("channelId") or "").strip()
                    thread_ts = str(payload.get("threadTs") or "").strip() or None
                    rfp_id = str(payload.get("rfpId") or "").strip() or rid or None
                    res = verify_ecs_rollout(timeout_s=timeout_s, poll_s=poll_s)
                    if channel and thread_ts:
                        try:
                            if res.get("ok"):
                                txt = (
                                    "ECS rollout looks stable:\n"
                                    f"- cluster: `{res.get('cluster')}`\n"
                                    f"- service: `{res.get('service')}`\n"
                                    f"- desired: {res.get('desiredCount')}\n"
                                    f"- running: {res.get('runningCount')}"
                                )
                            else:
                                txt = f"ECS rollout verification failed: `{res.get('error')}`"
                            if rfp_id:
                                post_summary(rfp_id=rfp_id, channel=channel, thread_ts=thread_ts, text=txt)
                            else:
                                chat_post_message_result(text=txt, channel=channel, thread_ts=thread_ts, unfurl_links=False)
                        except Exception:
                            pass
                    complete_job(job_id=jid, result=res)
                    completed += 1
                    continue

                if job_type == "ai_agent_ask":
                    # AI agent question/answer workload (sandboxed execution)
                    question = str(payload.get("question") or "").strip()
                    user_id = str(payload.get("userId") or payload.get("slackUserId") or "").strip() or None
                    user_display_name = str(payload.get("userDisplayName") or "").strip() or None
                    user_email = str(payload.get("userEmail") or "").strip() or None
                    user_profile = payload.get("userProfile") if isinstance(payload.get("userProfile"), dict) else None
                    channel_id = str(payload.get("channelId") or "").strip() or None
                    thread_ts = str(payload.get("threadTs") or "").strip() or None
                    max_steps = max(1, min(20, int(payload.get("maxSteps") or 6)))

                    if not question:
                        raise RuntimeError("missing_question_in_payload")

                    ans = run_slack_agent_question(
                        question=question,
                        user_id=user_id,
                        user_display_name=user_display_name,
                        user_email=user_email,
                        user_profile=user_profile,
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        max_steps=max_steps,
                    )
                    complete_job(job_id=jid, result={"ok": True, "text": ans.text, "blocks": ans.blocks, "meta": ans.meta})
                    completed += 1
                    continue

                if job_type == "ai_agent_analyze":
                    # AI agent analysis workload (for future expansion)
                    # For now, this is a placeholder - can be extended based on specific analysis needs
                    analysis_type = str(payload.get("analysisType") or "").strip()
                    if not analysis_type:
                        raise RuntimeError("missing_analysisType_in_payload")
                    # TODO: Implement specific analysis types as needed
                    complete_job(job_id=jid, result={"ok": True, "analysisType": analysis_type, "status": "not_implemented"})
                    completed += 1
                    continue

                raise RuntimeError(f"unknown_job_type:{job_type or 'unknown'}")
            except Exception as e:
                failed += 1
                try:
                    fail_job(job_id=jid, error=str(e) or "job_failed")
                except Exception:
                    pass
                if rid:
                    try:
                        append_event(
                            rfp_id=rid,
                            type="agent_job_failed",
                            tool="agent_job_runner",
                            payload={"jobId": jid, "jobType": job_type, "error": str(e) or "job_failed"},
                        )
                    except Exception:
                        pass
                continue
        
        # Accumulate batch totals
        total_ran += ran
        total_completed += completed
        total_failed += failed
        
        # Log batch completion
        log.info(
            "agent_job_runner_batch_done",
            batch=batches_processed,
            batch_ran=ran,
            batch_completed=completed,
            batch_failed=failed,
        )
        
        # Check for new jobs before finishing - if we processed a full batch, there might be more
        # The loop will continue if more jobs are found

    finished_at = _now_iso()
    out = {
        "ok": True,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "batches": batches_processed,
        "ran": total_ran,
        "completed": total_completed,
        "failed": total_failed,
    }
    try:
        log.info("agent_job_runner_done", **out)
    except Exception:
        pass

    # Report summary to Slack before task exits
    try:
        _report_to_slack(out)
    except Exception as e:
        # Never fail the task on Slack reporting errors
        log.warning("agent_job_runner_slack_report_error", error=str(e) or "unknown")

    return out


if __name__ == "__main__":
    configure_logging(level="INFO")
    run_once()

