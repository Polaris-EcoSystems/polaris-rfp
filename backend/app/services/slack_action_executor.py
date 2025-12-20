from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..observability.logging import get_logger
from .rfps_repo import get_rfp_by_id, list_rfp_proposal_summaries
from .user_profiles_repo import get_user_profile_by_slack_user_id, upsert_user_profile
from .workflow_tasks_repo import (
    assign_task,
    complete_task,
    compute_pipeline_stage,
    seed_missing_tasks_for_stage,
)
from .agent_jobs_repo import create_job as create_agent_job
from .slack_reply_tools import post_summary
from .slack_web import chat_post_message_result

log = get_logger("slack_action_executor")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def execute_action(*, action_id: str, kind: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a previously proposed action.
    Returns a structured result dict safe to show in Slack.
    """
    k = str(kind or "").strip()
    a = args if isinstance(args, dict) else {}

    if k == "seed_tasks_for_rfp":
        rfp_id = str(a.get("rfpId") or "").strip()
        if not rfp_id:
            return {"ok": False, "error": "missing_rfpId"}

        rfp = get_rfp_by_id(rfp_id)
        if not rfp:
            return {"ok": False, "error": "rfp_not_found"}
        proposals = list_rfp_proposal_summaries(rfp_id) or []
        stage = compute_pipeline_stage(rfp=rfp, proposals_for_rfp=proposals)
        created = seed_missing_tasks_for_stage(rfp_id=rfp_id, stage=stage, proposal_id=None)
        return {"ok": True, "action": k, "rfpId": rfp_id, "stage": stage, "createdCount": len(created)}

    if k == "assign_task":
        task_id = str(a.get("taskId") or "").strip()
        assignee = str(a.get("assigneeUserSub") or "").strip()
        if not task_id:
            return {"ok": False, "error": "missing_taskId"}
        if not assignee:
            return {"ok": False, "error": "missing_assigneeUserSub"}
        if assignee.lower() == "me":
            # Slack workspace is open; we don't have a stable mapping here yet.
            return {"ok": False, "error": "assignee_me_not_supported_in_slack"}

        updated = assign_task(task_id=task_id, assignee_user_sub=assignee, assignee_display_name=None)
        if not updated:
            return {"ok": False, "error": "task_not_found"}
        return {"ok": True, "action": k, "task": updated}

    if k == "complete_task":
        task_id = str(a.get("taskId") or "").strip()
        if not task_id:
            return {"ok": False, "error": "missing_taskId"}
        updated = complete_task(task_id=task_id, completed_by_user_sub=None)
        if not updated:
            return {"ok": False, "error": "task_not_found"}
        return {"ok": True, "action": k, "task": updated}

    if k == "update_user_profile":
        # Slack-confirmed: persist user prefs/memory.
        actor = str(a.get("_actorSlackUserId") or "").strip()
        requested = str(a.get("_requestedBySlackUserId") or "").strip()
        if not actor:
            return {"ok": False, "error": "missing_actor"}
        if requested and actor != requested:
            return {"ok": False, "error": "not_authorized_for_action"}

        profile = get_user_profile_by_slack_user_id(slack_user_id=actor)
        if not profile:
            return {"ok": False, "error": "slack_user_not_linked"}

        user_sub = str(profile.get("_id") or profile.get("userSub") or "").strip()
        if not user_sub:
            return {"ok": False, "error": "profile_missing_user_sub"}

        updates: dict[str, Any] = {}

        # Preferred name
        if "preferredName" in a:
            pn = str(a.get("preferredName") or "").strip()
            updates["preferredName"] = pn[:120] if pn else None

        # Preferences merge (shallow)
        prefs_merge = a.get("aiPreferencesMerge")
        if isinstance(prefs_merge, dict):
            existing = profile.get("aiPreferences") if isinstance(profile.get("aiPreferences"), dict) else {}
            merged = dict(existing)
            # Bound + shallow merge
            for kk, vv in list(prefs_merge.items())[:50]:
                k2 = str(kk or "").strip()[:60]
                if not k2:
                    continue
                if isinstance(vv, (int, float, bool)) or vv is None:
                    merged[k2] = vv
                else:
                    merged[k2] = str(vv)[:500]
            updates["aiPreferences"] = merged

        # Forget preference keys
        forget_keys = a.get("forgetPreferenceKeys")
        if isinstance(forget_keys, list):
            existing = profile.get("aiPreferences") if isinstance(profile.get("aiPreferences"), dict) else {}
            merged = dict(existing)
            for kk in forget_keys[:50]:
                k2 = str(kk or "").strip()
                if k2 in merged:
                    merged.pop(k2, None)
            updates["aiPreferences"] = merged

        # Memory set / append / clear
        if bool(a.get("clearMemory") is True):
            updates["aiMemorySummary"] = None
        if "aiMemorySummary" in a:
            ms = str(a.get("aiMemorySummary") or "").strip()
            updates["aiMemorySummary"] = ms[:4000] if ms else None
        if "aiMemoryAppend" in a:
            note = str(a.get("aiMemoryAppend") or "").strip()
            if note:
                existing = str(profile.get("aiMemorySummary") or "").strip()
                next_mem = (existing + ("\n" if existing else "") + f"- {note}").strip()
                # Keep last 4000 chars (trim from front).
                if len(next_mem) > 4000:
                    next_mem = next_mem[-4000:]
                    # Trim to line boundary if possible.
                    if "\n" in next_mem:
                        next_mem = next_mem.split("\n", 1)[1].strip()
                updates["aiMemorySummary"] = next_mem

        if not updates:
            return {"ok": True, "action": k, "updated": False, "message": "No changes requested."}

        saved = upsert_user_profile(user_sub=user_sub, email=str(profile.get("email") or "") or None, updates=updates)
        return {
            "ok": True,
            "action": k,
            "updated": True,
            "userSub": user_sub,
            "profile": {
                "preferredName": saved.get("preferredName"),
                "aiPreferences": saved.get("aiPreferences"),
                "aiMemorySummary": saved.get("aiMemorySummary"),
            },
        }

    if k == "self_modify_open_pr":
        # Approval-gated: enqueue a job to open a PR for a stored ChangeProposal.
        proposal_id = str(a.get("proposalId") or "").strip()
        actor = str(a.get("_actorSlackUserId") or "").strip()
        channel = str(a.get("channelId") or "").strip()
        thread_ts = str(a.get("threadTs") or "").strip() or None
        rfp_id = str(a.get("rfpId") or "").strip() or None
        if not proposal_id:
            return {"ok": False, "error": "missing_proposalId"}
        if not actor:
            return {"ok": False, "error": "missing_actor"}

        job = create_agent_job(
            job_type="self_modify_open_pr",
            scope={"rfpId": rfp_id} if rfp_id else {},
            due_at=_now_iso(),
            payload={
                "proposalId": proposal_id,
                "_actorSlackUserId": actor,
                "channelId": channel,
                "threadTs": thread_ts,
                "rfpId": rfp_id,
            },
            requested_by_user_sub=None,
        )
        if channel and thread_ts:
            try:
                txt = f"Queued PR creation for change proposal `{proposal_id}` (job `{job.get('jobId')}`)…"
                if rfp_id:
                    post_summary(rfp_id=rfp_id, channel=channel, thread_ts=thread_ts, text=txt)
                else:
                    chat_post_message_result(text=txt, channel=channel, thread_ts=thread_ts, unfurl_links=False)
            except Exception:
                pass
        return {"ok": True, "action": k, "job": job}

    if k == "self_modify_check_pr":
        # Enqueue a job to check PR status.
        pr = str(a.get("pr") or a.get("prUrl") or a.get("prNumber") or "").strip()
        if not pr:
            return {"ok": False, "error": "missing_pr"}
        channel = str(a.get("channelId") or "").strip()
        thread_ts = str(a.get("threadTs") or "").strip() or None
        rfp_id = str(a.get("rfpId") or "").strip() or None
        job = create_agent_job(
            job_type="self_modify_check_pr",
            scope={"rfpId": rfp_id} if rfp_id else {},
            due_at=_now_iso(),
            payload={"pr": pr, "channelId": channel, "threadTs": thread_ts, "rfpId": rfp_id},
            requested_by_user_sub=None,
        )
        if channel and thread_ts:
            try:
                txt = f"Queued PR checks lookup (job `{job.get('jobId')}`)…"
                if rfp_id:
                    post_summary(rfp_id=rfp_id, channel=channel, thread_ts=thread_ts, text=txt)
                else:
                    chat_post_message_result(text=txt, channel=channel, thread_ts=thread_ts, unfurl_links=False)
            except Exception:
                pass
        return {"ok": True, "action": k, "job": job}

    if k == "self_modify_verify_ecs":
        # Enqueue a job to verify ECS rollout.
        timeout_s = int(a.get("timeoutSeconds") or 600)
        poll_s = int(a.get("pollSeconds") or 10)
        channel = str(a.get("channelId") or "").strip()
        thread_ts = str(a.get("threadTs") or "").strip() or None
        rfp_id = str(a.get("rfpId") or "").strip() or None
        job = create_agent_job(
            job_type="self_modify_verify_ecs",
            scope={"rfpId": rfp_id} if rfp_id else {},
            due_at=_now_iso(),
            payload={"timeoutSeconds": timeout_s, "pollSeconds": poll_s, "channelId": channel, "threadTs": thread_ts, "rfpId": rfp_id},
            requested_by_user_sub=None,
        )
        if channel and thread_ts:
            try:
                txt = f"Queued ECS rollout verification (job `{job.get('jobId')}`)…"
                if rfp_id:
                    post_summary(rfp_id=rfp_id, channel=channel, thread_ts=thread_ts, text=txt)
                else:
                    chat_post_message_result(text=txt, channel=channel, thread_ts=thread_ts, unfurl_links=False)
            except Exception:
                pass
        return {"ok": True, "action": k, "job": job}

    return {"ok": False, "error": "unknown_action", "action": k}

