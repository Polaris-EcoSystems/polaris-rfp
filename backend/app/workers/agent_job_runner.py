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
from ..services.slack_reply_tools import post_summary
from ..services.self_modify_pipeline import get_pr_checks, open_pr_for_change_proposal, verify_ecs_rollout
from ..services.slack_web import chat_post_message_result


log = get_logger("agent_job_runner")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _job_scope_rfp_id(job: dict[str, Any]) -> str | None:
    scope = job.get("scope") if isinstance(job.get("scope"), dict) else {}
    rid = str(scope.get("rfpId") or "").strip()
    return rid or None


def run_once(*, limit: int = 25) -> dict[str, Any]:
    """
    Execute due agent jobs. Intended to run as a scheduled ECS task.
    """
    started_at = _now_iso()
    lim = max(1, min(100, int(limit or 25)))

    due = claim_due_jobs(now_iso=started_at, limit=lim)
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
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}

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

            if job_type == "self_modify_open_pr":
                proposal_id = str(payload.get("proposalId") or "").strip()
                actor = str(payload.get("_actorSlackUserId") or "").strip()
                channel = str(payload.get("channelId") or "").strip()
                thread_ts = str(payload.get("threadTs") or "").strip() or None
                rfp_id = str(payload.get("rfpId") or "").strip() or rid or None
                if not proposal_id or not actor:
                    raise RuntimeError("missing_proposalId_or_actor")
                res = open_pr_for_change_proposal(proposal_id=proposal_id, actor_slack_user_id=actor, rfp_id=rfp_id)
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
                        summary = res.get("checksSummary") or {}
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

    finished_at = _now_iso()
    out = {
        "ok": True,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "due": len(due),
        "ran": ran,
        "completed": completed,
        "failed": failed,
    }
    try:
        log.info("agent_job_runner_done", **out)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    configure_logging(level="INFO")
    run_once()

