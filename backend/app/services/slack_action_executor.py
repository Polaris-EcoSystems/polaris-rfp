from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..observability.logging import get_logger
from .agent_events_repo import append_event
from .agent_tools.aws_cognito import admin_disable_user as cognito_disable_user
from .agent_tools.aws_cognito import admin_enable_user as cognito_enable_user
from .agent_tools.aws_ecs import update_service as ecs_update_service
from .agent_tools.aws_s3 import copy_object as s3_copy_object
from .agent_tools.aws_s3 import delete_object as s3_delete_object
from .agent_tools.aws_s3 import move_object as s3_move_object
from .agent_tools.aws_sqs import redrive_dlq as sqs_redrive_dlq
from .agent_tools.github_api import comment_on_issue_or_pr as github_comment
from .agent_tools.github_api import create_issue as github_create_issue
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
            existing_raw = profile.get("aiPreferences")
            existing_prefs: dict[str, Any] = existing_raw if isinstance(existing_raw, dict) else {}
            merged_prefs: dict[str, Any] = dict(existing_prefs)
            # Bound + shallow merge
            for kk, vv in list(prefs_merge.items())[:50]:
                k2 = str(kk or "").strip()[:60]
                if not k2:
                    continue
                if isinstance(vv, (int, float, bool)) or vv is None:
                    merged_prefs[k2] = vv
                else:
                    merged_prefs[k2] = str(vv)[:500]
            updates["aiPreferences"] = merged_prefs

        # Forget preference keys
        forget_keys = a.get("forgetPreferenceKeys")
        if isinstance(forget_keys, list):
            existing_raw = profile.get("aiPreferences")
            existing_prefs2: dict[str, Any] = existing_raw if isinstance(existing_raw, dict) else {}
            merged_prefs2: dict[str, Any] = dict(existing_prefs2)
            for kk in forget_keys[:50]:
                k2 = str(kk or "").strip()
                if k2 in merged_prefs2:
                    merged_prefs2.pop(k2, None)
            updates["aiPreferences"] = merged_prefs2

        # Memory set / append / clear
        if bool(a.get("clearMemory") is True):
            updates["aiMemorySummary"] = None
        if "aiMemorySummary" in a:
            ms = str(a.get("aiMemorySummary") or "").strip()
            updates["aiMemorySummary"] = ms[:4000] if ms else None
        if "aiMemoryAppend" in a:
            note = str(a.get("aiMemoryAppend") or "").strip()
            if note:
                existing_mem = str(profile.get("aiMemorySummary") or "").strip()
                next_mem = (existing_mem + ("\n" if existing_mem else "") + f"- {note}").strip()
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
        rfp_id = str(a.get("rfpId") or "").strip()
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
                "rfpId": rfp_id or None,
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
        rfp_id = str(a.get("rfpId") or "").strip()
        job = create_agent_job(
            job_type="self_modify_check_pr",
            scope={"rfpId": rfp_id} if rfp_id else {},
            due_at=_now_iso(),
            payload={"pr": pr, "channelId": channel, "threadTs": thread_ts, "rfpId": rfp_id or None},
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
        rfp_id = str(a.get("rfpId") or "").strip()
        job = create_agent_job(
            job_type="self_modify_verify_ecs",
            scope={"rfpId": rfp_id} if rfp_id else {},
            due_at=_now_iso(),
            payload={"timeoutSeconds": timeout_s, "pollSeconds": poll_s, "channelId": channel, "threadTs": thread_ts, "rfpId": rfp_id or None},
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

    if k == "ecs_update_service":
        # Approval-gated: update ECS service (forceNewDeployment and/or desiredCount).
        cluster = str(a.get("cluster") or "").strip() or None
        service = str(a.get("service") or "").strip() or None
        force = bool(a.get("forceNewDeployment") is True)
        desired_raw = a.get("desiredCount")
        desired = int(desired_raw) if desired_raw is not None and str(desired_raw).strip() != "" else None
        try:
            res = ecs_update_service(cluster=cluster, service=service, force_new_deployment=force, desired_count=desired)
        except Exception as e:
            res = {"ok": False, "error": str(e) or "ecs_update_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    if k == "s3_copy_object":
        try:
            res = s3_copy_object(source_key=str(a.get("sourceKey") or ""), dest_key=str(a.get("destKey") or ""))
        except Exception as e:
            res = {"ok": False, "error": str(e) or "s3_copy_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    if k == "s3_move_object":
        try:
            res = s3_move_object(source_key=str(a.get("sourceKey") or ""), dest_key=str(a.get("destKey") or ""))
        except Exception as e:
            res = {"ok": False, "error": str(e) or "s3_move_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    if k == "s3_delete_object":
        try:
            res = s3_delete_object(key=str(a.get("key") or ""))
        except Exception as e:
            res = {"ok": False, "error": str(e) or "s3_delete_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    if k == "cognito_disable_user":
        user_pool_id = str(a.get("userPoolId") or "").strip() or None
        username = str(a.get("username") or "").strip()
        try:
            res = cognito_disable_user(user_pool_id=user_pool_id, username=username)
        except Exception as e:
            res = {"ok": False, "error": str(e) or "cognito_disable_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    if k == "cognito_enable_user":
        user_pool_id = str(a.get("userPoolId") or "").strip() or None
        username = str(a.get("username") or "").strip()
        try:
            res = cognito_enable_user(user_pool_id=user_pool_id, username=username)
        except Exception as e:
            res = {"ok": False, "error": str(e) or "cognito_enable_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    if k == "sqs_redrive_dlq":
        src = str(a.get("sourceQueueUrl") or "").strip()
        dst = str(a.get("destinationQueueUrl") or "").strip()
        mps_raw = a.get("maxPerSecond")
        mps = int(mps_raw) if mps_raw is not None and str(mps_raw).strip() else None
        try:
            res = sqs_redrive_dlq(source_queue_url=src, destination_queue_url=dst, max_per_second=mps)
        except Exception as e:
            res = {"ok": False, "error": str(e) or "sqs_redrive_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    if k == "github_create_issue":
        repo = str(a.get("repo") or "").strip() or None
        title = str(a.get("title") or "").strip()
        body = str(a.get("body") or "").strip() or None
        try:
            res = github_create_issue(repo=repo, title=title, body=body)
        except Exception as e:
            res = {"ok": False, "error": str(e) or "github_create_issue_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    if k == "github_comment":
        repo = str(a.get("repo") or "").strip() or None
        number = int(a.get("number") or 0)
        body = str(a.get("body") or "").strip()
        try:
            res = github_comment(repo=repo, number=number, body=body)
        except Exception as e:
            res = {"ok": False, "error": str(e) or "github_comment_failed"}
        _audit_best_effort(args=a, action=k, ok=bool(res.get("ok")), result=res)
        return {"ok": bool(res.get("ok")), "action": k, "result": res}

    return {"ok": False, "error": "unknown_action", "action": k}


def _audit_best_effort(*, args: dict[str, Any], action: str, ok: bool, result: dict[str, Any]) -> None:
    """
    Append an AgentEvent if an rfpId is available (best-effort).
    """
    try:
        rid = str(args.get("rfpId") or "").strip()
        if not rid:
            return
        append_event(
            rfp_id=rid,
            type="action_execute",
            tool=action,
            payload={"ok": bool(ok)},
            inputs_redacted={"argsKeys": [str(k) for k in list(args.keys())[:60]]},
            outputs_redacted={"resultPreview": {k: result.get(k) for k in list(result.keys())[:30]}},
            created_by="slack_action_executor",
        )
    except Exception:
        return

