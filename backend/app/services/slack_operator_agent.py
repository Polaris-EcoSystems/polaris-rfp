from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..ai.client import AiNotConfigured, _client
from ..ai.context import normalize_ws
from ..ai.tuning import tuning_for
from ..observability.logging import get_logger
from ..settings import settings
from .agent_events_repo import append_event, list_recent_events
from .agent_journal_repo import append_entry, list_recent_entries
from .agent_jobs_repo import (
    create_job as create_agent_job,
    get_job as get_agent_job,
    list_recent_jobs,
    list_jobs_by_scope,
    list_jobs_by_type,
    claim_due_jobs,
)
from .agent_policy import sanitize_opportunity_patch
from .change_proposals_repo import create_change_proposal
from .opportunity_state_repo import ensure_state_exists, get_state, patch_state
from .slack_thread_bindings_repo import get_binding as get_thread_binding, set_binding as set_thread_binding
from .slack_reply_tools import ask_clarifying_question, post_summary
from .agent_tools.slack_read import get_thread as slack_get_thread
from .slack_web import get_user_info, slack_user_display_name

# Reuse proven OpenAI tool-call plumbing from slack_agent to avoid divergence.
from . import slack_agent as _sa


log = get_logger("slack_operator_agent")


# Slack bot token scopes - capabilities the agent has
SLACK_BOT_SCOPES = """
You have full org-wide Slack permissions. Key capabilities:
- Read/write messages: Can read and send messages in all channels (public/private/DMs) you're in, including channels you're not a member of (chat:write.public)
- Channel management: Join, create, manage public/private channels; invite members; set topics/descriptions
- Direct messages: Start DMs and group DMs with any user; read/write DM history
- Files: Read, upload, edit, delete files shared in channels/DMs
- User access: Read user profiles, email addresses, workspace info
- Search: Search files, public channels, and users across the workspace
- Other capabilities: Manage bookmarks, pins, reactions, reminders, workflows, triggers, user groups, canvases, lists, calls, etc.

You do NOT need permission to access channels - you have full org-wide access. You can identify channels by name or ID, and can read messages even if you haven't been explicitly invited. You should never claim you lack permissions or need to be invited.
"""


# Agent Jobs System Documentation
AGENT_JOBS_SYSTEM_DOCS = """
Agent Jobs System Architecture:
- Jobs are executed by NorthStar Job Runner, an ECS task that runs every 15 minutes
- Jobs are queued with a `due_at` ISO timestamp (e.g., "2024-01-15T10:30:00Z")
- Jobs execute asynchronously; results are stored in the job record after completion
- Jobs can be scoped to an RFP (via scope.rfpId) or be global (no rfpId in scope)
- Use `agent_job_list` to see scheduled/running/completed jobs, `agent_job_get` to see details by ID
- Jobs run in the background; check status using job query tools
"""


AGENT_JOB_TYPES_DOCS = """
Available Job Types (use with schedule_job tool):

RFP/Opportunity Management:
- `opportunity_maintenance` / `perch_refresh` - Sync RFP state from platform (stage, dueDates, proposalIds, contractingCaseId)
  * Scope: REQUIRED (scope.rfpId)
  * Payload: {} (no payload needed)
  * Behavior: Fetches current state from platform and updates OpportunityState

- `opportunity_compact` / `memory_compact` - Compact journal entries for an RFP to reduce storage
  * Scope: REQUIRED (scope.rfpId)
  * Payload: {"journalLimit": 25} (optional, default 25)
  * Behavior: Keeps only the most recent N journal entries

Agent Operations:
- `agent_daily_digest` - Generate and send daily Slack reports
  * Scope: Global (use {} or {"env": "production"})
  * Payload: {"hours": 24} (optional, default 24)
  * Behavior: Generates digest, sends to configured Slack channel, reschedules itself

- `agent_perch_time` / `telemetry_self_improve` - Run self-improvement/analysis tasks
  * Scope: Global
  * Payload: {"hours": 6, "rescheduleMinutes": 60} (optional)
  * Behavior: Analyzes telemetry/logs, may reschedule itself

Notifications:
- `slack_nudge` - Send a Slack notification message
  * Scope: REQUIRED (scope.rfpId)
  * Payload: {"channel": "C123456", "threadTs": "1234567890.123456", "text": "Message text"}
  * Behavior: Posts message to specified Slack channel/thread

Self-Modification Pipeline (GitHub PR automation):
- `self_modify_open_pr` - Open a GitHub PR for a change proposal
  * Scope: Optional (scope.rfpId)
  * Payload: {"proposalId": "cp_...", "_actorSlackUserId": "U123", "channelId": "C123", "threadTs": "123.456", "rfpId": "rfp_..."}
  * Behavior: Creates GitHub PR from change proposal, posts result to Slack

- `self_modify_check_pr` - Check status of GitHub PR checks
  * Scope: Optional (scope.rfpId)
  * Payload: {"pr": "123" or "https://github.com/.../pull/123", "channelId": "C123", "threadTs": "123.456", "rfpId": "rfp_..."}
  * Behavior: Checks PR status, reports to Slack

- `self_modify_verify_ecs` - Verify ECS service rollout completed successfully
  * Scope: Optional (scope.rfpId)
  * Payload: {"timeoutSeconds": 600, "pollSeconds": 10, "channelId": "C123", "threadTs": "123.456", "rfpId": "rfp_..."}
  * Behavior: Polls ECS service until stable or timeout, reports to Slack

AI Agent Workloads:
- `ai_agent_ask` - Run an AI agent question workload (sandboxed)
  * Scope: Optional
  * Payload: {"question": "...", "userId": "U123", "userDisplayName": "...", "userEmail": "...", "userProfile": {...}, "channelId": "C123", "threadTs": "123.456", "maxSteps": 6}
  * Behavior: Runs agent question processing, stores result in job

- `ai_agent_analyze` - AI analysis workload (placeholder for future expansion)
  * Scope: Optional
  * Payload: {"analysisType": "..."}
  * Behavior: Currently returns "not_implemented"

- `ai_agent_analyze_rfps` - Long-running: Deep analysis across multiple RFPs (supports checkpoint/resume)
  * Scope: Optional (can include rfpId for context)
  * Payload: {"rfpIds": ["rfp_...", "rfp_..."], "analysisType": "..."}
  * Behavior: Analyzes multiple RFPs, checkpoints progress, can resume across job runner cycles
  * Note: Automatically checkpoints before ECS task timeout, resumes on next run

- `ai_agent_monitor_conditions` - Watch for conditions and take action (long-running)
  * Scope: Optional
  * Payload: {"conditions": [...], "actions": [...], "checkIntervalMinutes": 15}
  * Behavior: Monitors conditions, takes action when met, checkpoints state

- `ai_agent_solve_problem` - Multi-step problem resolution (long-running)
  * Scope: Optional
  * Payload: {"problem": "...", "constraints": {...}, "maxSteps": 50}
  * Behavior: Breaks problem into steps, solves iteratively, checkpoints progress

- `ai_agent_maintain_data` - Data cleanup and synchronization (long-running)
  * Scope: Optional
  * Payload: {"operation": "...", "targets": [...]}
  * Behavior: Performs maintenance operations, checkpoints progress
"""


AGENT_TOOL_CATEGORIES_DOCS = """
Tool Categories Overview:

RFP/Proposal Browsing:
- list_rfps, search_rfps, get_rfp - Browse and search RFPs
- list_proposals, get_proposal - Browse proposals
- list_tasks - View workflow tasks

Opportunity State Management:
- opportunity_load - Load OpportunityState + journal + events for an RFP
- opportunity_patch - Update OpportunityState (durable artifact)
- journal_append - Add journal entry (decision narrative)
- event_append - Add event log entry (tool calls, decisions)

Slack Operations:
- slack_get_thread - Fetch thread conversation history
- slack_list_recent_messages - List recent channel messages
- slack_post_summary - Post summary to Slack thread (use after state updates)
- slack_ask_clarifying_question - Ask blocking clarifying question (rare)

Agent Jobs:
- schedule_job - Schedule a job for later execution (dueAt ISO time)
- agent_job_list - List jobs with filtering (status, jobType, rfpId)
- agent_job_get - Get job details by ID
- agent_job_query_due - Query due/overdue queued jobs

Infrastructure/AWS Tools:
- dynamodb_* - Query/describe DynamoDB tables
- s3_* - S3 operations (head, presign)
- telemetry_* - CloudWatch Logs Insights queries
- browser_* - Browser automation (Playwright)
- github_* - GitHub API operations
- aws_ecs_* - ECS service operations

Action Proposal:
- propose_action - Propose platform action for user confirmation (does not execute)
"""


@dataclass(frozen=True)
class SlackOperatorResult:
    did_post: bool
    text: str | None = None
    meta: dict[str, Any] | None = None


def _extract_rfp_id(text: str) -> str | None:
    t = str(text or "")
    m = re.search(r"\b(rfp_[a-zA-Z0-9-]{6,})\b", t)
    if not m:
        return None
    return str(m.group(1)).strip() or None


def _fetch_thread_history(*, channel_id: str, thread_ts: str, limit: int = 50) -> str:
    """
    Fetch thread messages and format them as a readable conversation history.
    Returns a formatted string suitable for inclusion in system prompts.
    """
    try:
        result = slack_get_thread(channel=channel_id, thread_ts=thread_ts, limit=limit)
        if not result.get("ok"):
            return ""
        
        messages = result.get("messages", [])
        if not messages or not isinstance(messages, list):
            return ""
        
        # Format messages in chronological order
        lines: list[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            user_id = str(msg.get("user") or "").strip()
            text = str(msg.get("text") or "").strip()
            
            if not text:
                continue
            
            # Get user display name (cache-friendly, so safe to call)
            user_name = "User"
            if user_id:
                try:
                    user_info = get_user_info(user_id=user_id)
                    user_name = slack_user_display_name(user_info) or user_id
                except Exception:
                    user_name = user_id
            
            # Format: "User: message text"
            lines.append(f"{user_name}: {text}")
        
        if not lines:
            return ""
        
        return "\n".join(lines)
    except Exception:
        # Best-effort: if fetching fails, return empty string (don't break the agent)
        log.warning("thread_history_fetch_failed", channel=channel_id, thread_ts=thread_ts)
        return ""


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return _sa._tool_def(name, description, parameters)


ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


def _opportunity_load_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    ensure_state_exists(rfp_id=rid)
    return {
        "ok": True,
        "rfpId": rid,
        "opportunity": get_state(rfp_id=rid),
        "journal": list_recent_entries(rfp_id=rid, limit=int(args.get("journalLimit") or 10)),
        "events": list_recent_events(rfp_id=rid, limit=int(args.get("eventsLimit") or 10)),
    }


def _opportunity_patch_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    p = args.get("patch")
    patch_obj = p if isinstance(p, dict) else {}
    actor = {
        "kind": "slack_operator_agent",
        "slackUserId": str(args.get("slackUserId") or "").strip() or None,
    }
    patch_obj, policy_checks = sanitize_opportunity_patch(patch=patch_obj, actor=actor)
    updated = patch_state(
        rfp_id=rid,
        patch=patch_obj,
        updated_by_user_sub=None,
        create_snapshot=bool(args.get("createSnapshot") is True),
    )
    if policy_checks:
        try:
            append_event(
                rfp_id=rid,
                type="policy_check",
                payload={"tool": "opportunity_patch"},
                tool="opportunity_patch",
                policy_checks=policy_checks,
                created_by="slack_operator_agent",
                correlation_id=str(args.get("correlationId") or "").strip() or None,
            )
        except Exception:
            pass
    return {"ok": True, "rfpId": rid, "opportunity": updated, "policyChecks": policy_checks}


def _journal_append_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    entry = append_entry(
        rfp_id=rid,
        topics=args.get("topics") if isinstance(args.get("topics"), list) else None,
        user_stated=str(args.get("userStated") or "").strip() or None,
        agent_intent=str(args.get("agentIntent") or "").strip() or None,
        what_changed=str(args.get("whatChanged") or "").strip() or None,
        why=str(args.get("why") or "").strip() or None,
        assumptions=args.get("assumptions") if isinstance(args.get("assumptions"), list) else None,
        sources=args.get("sources") if isinstance(args.get("sources"), list) else None,
        created_by_user_sub=None,
        meta=args.get("meta") if isinstance(args.get("meta"), dict) else None,
    )
    return {"ok": True, "entry": entry}


def _event_append_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    ev = append_event(
        rfp_id=rid,
        type=str(args.get("type") or "").strip() or "event",
        payload=args.get("payload") if isinstance(args.get("payload"), dict) else {},
        tool=str(args.get("tool") or "").strip() or None,
        inputs_redacted=args.get("inputsRedacted") if isinstance(args.get("inputsRedacted"), dict) else None,
        outputs_redacted=args.get("outputsRedacted") if isinstance(args.get("outputsRedacted"), dict) else None,
        policy_checks=args.get("policyChecks") if isinstance(args.get("policyChecks"), list) else None,
        confidence_flags=args.get("confidenceFlags") if isinstance(args.get("confidenceFlags"), list) else None,
        downstream_effects=args.get("downstreamEffects") if isinstance(args.get("downstreamEffects"), list) else None,
        created_by=str(args.get("createdBy") or "").strip() or None,
        correlation_id=str(args.get("correlationId") or "").strip() or None,
    )
    return {"ok": True, "event": ev}


def _schedule_job_tool(args: dict[str, Any]) -> dict[str, Any]:
    due_at = str(args.get("dueAt") or "").strip()
    job_type = str(args.get("jobType") or "").strip() or "unknown"
    raw_scope = args.get("scope")
    scope: dict[str, Any] = raw_scope if isinstance(raw_scope, dict) else {}
    raw_payload = args.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    raw_depends_on = args.get("dependsOn")
    depends_on = [str(d).strip() for d in raw_depends_on] if isinstance(raw_depends_on, list) else None
    job = create_agent_job(
        job_type=job_type,
        scope=scope,
        due_at=due_at,
        payload=payload,
        requested_by_user_sub=None,
        depends_on=depends_on,
    )
    return {"ok": True, "job": job}


def _agent_job_list_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(50, int(args.get("limit") or 25)))
    status = str(args.get("status") or "").strip() or None
    job_type = str(args.get("jobType") or "").strip() or None
    rfp_id = str(args.get("rfpId") or "").strip() or None
    
    jobs: list[dict[str, Any]] = []
    
    try:
        if rfp_id:
            # Filter by scope (rfpId)
            scope_filter = {"rfpId": rfp_id}
            jobs = list_jobs_by_scope(scope=scope_filter, limit=limit, status=status)
        elif job_type:
            # Filter by job type
            jobs = list_jobs_by_type(job_type=job_type, limit=limit, status=status)
        else:
            # List all recent jobs
            jobs = list_recent_jobs(limit=limit, status=status)
    except Exception as e:
        return {"ok": False, "error": str(e) or "job_list_failed"}
    
    # Slim payload for each job to avoid bloating response
    slim_jobs: list[dict[str, Any]] = []
    for job in jobs:
        slim: dict[str, Any] = {
            "jobId": job.get("jobId"),
            "jobType": job.get("jobType"),
            "status": job.get("status"),
            "dueAt": job.get("dueAt"),
            "createdAt": job.get("createdAt"),
            "scope": job.get("scope"),
        }
        # Include payload preview (first few keys)
        payload = job.get("payload")
        if isinstance(payload, dict):
            slim["payloadPreview"] = {k: payload.get(k) for k in list(payload.keys())[:5]}
        if "result" in job:
            slim["result"] = job.get("result")
        if "error" in job:
            slim["error"] = job.get("error")
        slim_jobs.append(slim)
    
    return {"ok": True, "jobs": slim_jobs, "count": len(slim_jobs)}


def _agent_job_get_tool(args: dict[str, Any]) -> dict[str, Any]:
    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        return {"ok": False, "error": "missing_jobId"}
    
    try:
        job = get_agent_job(job_id=job_id)
        if not job:
            return {"ok": False, "error": "job_not_found", "jobId": job_id}
        return {"ok": True, "job": job}
    except Exception as e:
        return {"ok": False, "error": str(e) or "job_get_failed"}


def _agent_job_query_due_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(50, int(args.get("limit") or 25)))
    before_iso = str(args.get("beforeIso") or "").strip() or None
    
    try:
        now_iso = before_iso
        due_jobs = claim_due_jobs(now_iso=now_iso, limit=limit)
        
        # Format results
        slim_jobs: list[dict[str, Any]] = []
        for job in due_jobs:
            slim: dict[str, Any] = {
                "jobId": job.get("jobId"),
                "jobType": job.get("jobType"),
                "status": job.get("status"),
                "dueAt": job.get("dueAt"),
                "createdAt": job.get("createdAt"),
                "scope": job.get("scope"),
            }
            payload = job.get("payload")
            if isinstance(payload, dict):
                slim["payloadPreview"] = {k: payload.get(k) for k in list(payload.keys())[:5]}
            slim_jobs.append(slim)
        
        return {"ok": True, "jobs": slim_jobs, "count": len(slim_jobs)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "job_query_due_failed"}

def _create_change_proposal_tool(args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or "").strip()
    summary = str(args.get("summary") or "").strip()
    patch = str(args.get("patch") or "")
    rfp_id = str(args.get("rfpId") or "").strip() or None
    raw_files = args.get("filesTouched")
    files: list[Any] = raw_files if isinstance(raw_files, list) else []
    cp = create_change_proposal(
        title=title or "Change proposal",
        summary=summary or "",
        patch=patch,
        files_touched=[str(x).strip() for x in files if str(x).strip()],
        rfp_id=rfp_id,
        created_by_slack_user_id=str(args.get("createdBySlackUserId") or "").strip() or None,
        meta=args.get("meta") if isinstance(args.get("meta"), dict) else None,
    )
    return {"ok": True, "proposal": {k: v for k, v in cp.items() if k != "patch"}}


def _slack_post_summary_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    ch = str(args.get("channel") or "").strip()
    thread_ts = str(args.get("threadTs") or "").strip() or None
    text = str(args.get("text") or "").strip()
    blocks = args.get("blocks") if isinstance(args.get("blocks"), list) else None
    corr = str(args.get("correlationId") or "").strip() or None
    if not rid or not ch:
        return {"ok": False, "error": "missing_rfp_or_channel"}
    res = post_summary(rfp_id=rid, channel=ch, thread_ts=thread_ts, text=text, blocks=blocks, correlation_id=corr)
    return {"ok": bool(res.get("ok")), "slack": res}


def _slack_ask_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    ch = str(args.get("channel") or "").strip()
    thread_ts = str(args.get("threadTs") or "").strip() or None
    q = str(args.get("question") or "").strip()
    corr = str(args.get("correlationId") or "").strip() or None
    if not rid or not ch:
        return {"ok": False, "error": "missing_rfp_or_channel"}
    res = ask_clarifying_question(rfp_id=rid, channel=ch, thread_ts=thread_ts, question=q, correlation_id=corr)
    return {"ok": bool(res.get("ok")), "slack": res}


OPERATOR_TOOLS: dict[str, tuple[dict[str, Any], ToolFn]] = {
    # Read tools (existing platform browsing).
    **_sa.READ_TOOLS,
    # State artifacts.
    "opportunity_load": (
        _tool_def(
            "opportunity_load",
            "Load the canonical OpportunityState plus recent journal and event log entries.",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "journalLimit": {"type": "integer", "minimum": 1, "maximum": 30},
                    "eventsLimit": {"type": "integer", "minimum": 1, "maximum": 30},
                },
                "required": ["rfpId"],
                "additionalProperties": False,
            },
        ),
        _opportunity_load_tool,
    ),
    "opportunity_patch": (
        _tool_def(
            "opportunity_patch",
            "Patch OpportunityState (durable artifact). Use *_append keys to append to lists; commitments are add-only and require provenance on appended items.",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "patch": {"type": "object"},
                    "createSnapshot": {"type": "boolean"},
                    "slackUserId": {"type": "string", "maxLength": 40},
                    "correlationId": {"type": "string", "maxLength": 120},
                },
                "required": ["rfpId", "patch"],
                "additionalProperties": False,
            },
        ),
        _opportunity_patch_tool,
    ),
    "journal_append": (
        _tool_def(
            "journal_append",
            "Append a journal entry capturing what changed and why (decision narrative).",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "topics": {"type": "array", "items": {"type": "string"}, "maxItems": 25},
                    "userStated": {"type": "string", "maxLength": 2000},
                    "agentIntent": {"type": "string", "maxLength": 800},
                    "whatChanged": {"type": "string", "maxLength": 2000},
                    "why": {"type": "string", "maxLength": 2000},
                    "assumptions": {"type": "array", "items": {"type": "string"}, "maxItems": 50},
                    "sources": {"type": "array", "items": {"type": "object"}, "maxItems": 50},
                    "meta": {"type": "object"},
                },
                "required": ["rfpId"],
                "additionalProperties": False,
            },
        ),
        _journal_append_tool,
    ),
    "event_append": (
        _tool_def(
            "event_append",
            "Append an explainability event (append-only log of tool calls/decisions).",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "type": {"type": "string", "maxLength": 120},
                    "tool": {"type": "string", "maxLength": 120},
                    "payload": {"type": "object"},
                    "inputsRedacted": {"type": "object"},
                    "outputsRedacted": {"type": "object"},
                    "policyChecks": {"type": "array", "items": {"type": "object"}, "maxItems": 50},
                    "confidenceFlags": {"type": "array", "items": {"type": "string"}, "maxItems": 25},
                    "downstreamEffects": {"type": "array", "items": {"type": "object"}, "maxItems": 50},
                    "createdBy": {"type": "string", "maxLength": 120},
                    "correlationId": {"type": "string", "maxLength": 120},
                },
                "required": ["rfpId", "type"],
                "additionalProperties": False,
            },
        ),
        _event_append_tool,
    ),
    "schedule_job": (
        _tool_def(
            "schedule_job",
            "Schedule a one-shot agent job for later execution (dueAt ISO time). Supports long-running jobs with checkpoint/resume.",
            {
                "type": "object",
                "properties": {
                    "dueAt": {"type": "string", "minLength": 1, "maxLength": 40},
                    "jobType": {"type": "string", "minLength": 1, "maxLength": 120},
                    "scope": {"type": "object"},
                    "payload": {"type": "object"},
                    "dependsOn": {"type": "array", "items": {"type": "string"}, "maxItems": 20, "description": "List of job IDs this job depends on (must complete first)"},
                },
                "required": ["dueAt", "jobType", "scope"],
                "additionalProperties": False,
            },
        ),
        _schedule_job_tool,
    ),
    "agent_job_list": (
        _tool_def(
            "agent_job_list",
            "List recent agent jobs with optional filtering by status, jobType, or rfpId scope.",
            {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "status": {"type": "string", "enum": ["queued", "running", "completed", "failed", "cancelled"]},
                    "jobType": {"type": "string", "maxLength": 120},
                    "rfpId": {"type": "string", "maxLength": 120},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _agent_job_list_tool,
    ),
    "agent_job_get": (
        _tool_def(
            "agent_job_get",
            "Get full details of a specific agent job by ID, including result (if completed) or error (if failed).",
            {
                "type": "object",
                "properties": {
                    "jobId": {"type": "string", "minLength": 1, "maxLength": 60},
                },
                "required": ["jobId"],
                "additionalProperties": False,
            },
        ),
        _agent_job_get_tool,
    ),
    "agent_job_query_due": (
        _tool_def(
            "agent_job_query_due",
            "Query jobs that are due or overdue (queued and should have run by now). Useful for checking job backlog.",
            {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "beforeIso": {"type": "string", "maxLength": 40},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _agent_job_query_due_tool,
    ),
    "create_change_proposal": (
        _tool_def(
            "create_change_proposal",
            "Create a ChangeProposal artifact (patch + rationale) for a future PR. Does not change code.",
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1, "maxLength": 180},
                    "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "patch": {"type": "string", "minLength": 1, "maxLength": 120000},
                    "filesTouched": {"type": "array", "items": {"type": "string"}, "maxItems": 50},
                    "rfpId": {"type": "string", "maxLength": 120},
                    "createdBySlackUserId": {"type": "string", "maxLength": 60},
                    "meta": {"type": "object"},
                },
                "required": ["title", "summary", "patch"],
                "additionalProperties": False,
            },
        ),
        _create_change_proposal_tool,
    ),
    # Slack reply tools.
    "slack_post_summary": (
        _tool_def(
            "slack_post_summary",
            "Post a summary to Slack (threaded) after updating state and logging.",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "channel": {"type": "string", "minLength": 1, "maxLength": 50},
                    "threadTs": {"type": "string", "maxLength": 40},
                    "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "blocks": {"type": "array", "items": {"type": "object"}, "maxItems": 40},
                    "correlationId": {"type": "string", "maxLength": 120},
                },
                "required": ["rfpId", "channel", "text"],
                "additionalProperties": False,
            },
        ),
        _slack_post_summary_tool,
    ),
    "slack_ask_clarifying_question": (
        _tool_def(
            "slack_ask_clarifying_question",
            "Ask a single blocking clarifying question in Slack thread (rare).",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "channel": {"type": "string", "minLength": 1, "maxLength": 50},
                    "threadTs": {"type": "string", "maxLength": 40},
                    "question": {"type": "string", "minLength": 1, "maxLength": 1200},
                    "correlationId": {"type": "string", "maxLength": 120},
                },
                "required": ["rfpId", "channel", "question"],
                "additionalProperties": False,
            },
        ),
        _slack_ask_tool,
    ),
}


def run_slack_operator_for_mention(
    *,
    question: str,
    channel_id: str,
    thread_ts: str,
    user_id: str | None,
    correlation_id: str | None = None,
    max_steps: int = 8,
) -> SlackOperatorResult:
    """
    Operator-style Slack agent:
    - reconstructs context from durable artifacts
    - updates state/journal/events
    - replies via Slack tools (not by returning chat text)
    """
    q = normalize_ws(question or "", max_chars=5000)
    ch = str(channel_id or "").strip()
    th = str(thread_ts or "").strip()
    corr = str(correlation_id or "").strip() or None
    if not q or not ch or not th:
        return SlackOperatorResult(did_post=False, text=None, meta={"error": "missing_params"})

    # Best-effort identity resolution for safer write actions (and future "me" support).
    actor_ctx = None
    actor_user_sub = None
    try:
        from .slack_actor_context import resolve_actor_context

        actor_ctx = resolve_actor_context(slack_user_id=user_id, slack_team_id=None, slack_enterprise_id=None)
        actor_user_sub = actor_ctx.user_sub
    except Exception:
        actor_user_sub = None

    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")

    # Thread utilities: remove rfpId friction via thread→rfp binding.
    # - In-thread: "@polaris link rfp_..." binds the thread.
    # - In-thread: "@polaris where" shows current binding.
    try:
        from .slack_web import chat_post_message_result

        m_link = re.match(r"^\s*(link|bind)\s+(rfp_[a-zA-Z0-9-]{6,})\b", q, flags=re.IGNORECASE)
        if m_link:
            rid = str(m_link.group(2) or "").strip()
            set_thread_binding(channel_id=ch, thread_ts=th, rfp_id=rid, bound_by_slack_user_id=user_id)
            chat_post_message_result(
                text=f"Bound this thread to `{rid}`. Future mentions will use that as context.",
                channel=ch,
                thread_ts=th,
                unfurl_links=False,
            )
            return SlackOperatorResult(did_post=True, text=None, meta={"boundRfpId": rid})

        if q.strip().lower() in ("where", "where?"):
            b = get_thread_binding(channel_id=ch, thread_ts=th)
            bound_rid = str((b or {}).get("rfpId") or "").strip() or None
            if bound_rid:
                msg = f"This thread is bound to `{bound_rid}`."
            else:
                msg = "No RFP is bound to this thread yet. Bind it once with: `@polaris link rfp_...`"
            chat_post_message_result(text=msg, channel=ch, thread_ts=th, unfurl_links=False)
            return SlackOperatorResult(did_post=True, text=msg, meta={"boundRfpId": bound_rid})
    except Exception:
        # Never block the operator on thread-binding helpers.
        pass

    # Attempt to scope to an RFP for durable state.
    rfp_id = _extract_rfp_id(q)
    if not rfp_id:
        # Fall back to thread binding.
        try:
            b = get_thread_binding(channel_id=ch, thread_ts=th)
            rfp_id = str((b or {}).get("rfpId") or "").strip() or None
        except Exception:
            rfp_id = None

    if not rfp_id:
        # No RFP scope: delegate to the conversational read-only Slack agent.
        # This keeps @mentions responsive without requiring thread binding.
        try:
            from .slack_web import chat_post_message_result
            from .slack_actor_context import resolve_actor_context

            ctx = resolve_actor_context(slack_user_id=user_id, slack_team_id=None, slack_enterprise_id=None)
            display_name = ctx.display_name
            email = ctx.email
            user_profile = ctx.user_profile

            ans = _sa.run_slack_agent_question(
                question=q,
                user_id=user_id,
                user_display_name=display_name,
                user_email=email,
                user_profile=user_profile,
                channel_id=ch,
                thread_ts=th,
            )
            txt = str(ans.text or "").strip() or "No answer."
            chat_post_message_result(
                text=txt,
                channel=ch,
                thread_ts=th,
                blocks=ans.blocks,
                unfurl_links=False,
            )
            return SlackOperatorResult(did_post=True, text=txt, meta={"scoped": False, "delegated": "slack_agent"})
        except Exception:
            # Fall through to the binding prompt if anything goes wrong.
            pass

        # Ask to include an explicit id or bind the thread; keep it short.
        msg = (
            "Which RFP is this about?\n"
            "- include an id like `rfp_...` in your message, or\n"
            "- bind this thread once with: `@polaris link rfp_...`"
            "\n\nIf this isn’t about a specific RFP, use `/polaris ask <question>`."
        )
        try:
            from .slack_web import chat_post_message_result

            chat_post_message_result(text=msg, channel=ch, thread_ts=th, unfurl_links=False)
        except Exception:
            pass
        return SlackOperatorResult(did_post=True, text=msg, meta={"scoped": False})

    ensure_state_exists(rfp_id=rfp_id)

    model = settings.openai_model_for("slack_agent")
    client = _client(timeout_s=75)

    tools = [tpl for (tpl, _fn) in OPERATOR_TOOLS.values()]
    # Allow proposing platform actions with human confirmation (existing pattern).
    if bool(settings.slack_agent_actions_enabled):
        tools.append(_sa._propose_action_tool_def())
    tool_names = [tpl["name"] for tpl in tools if isinstance(tpl, dict) and tpl.get("name")]
    chat_tools = [_sa._to_chat_tool(tpl) for tpl in tools if isinstance(tpl, dict)]

    # Use enhanced context builder for comprehensive context
    from .agent_context_builder import (
        build_rfp_state_context,
        build_related_rfps_context,
        build_cross_thread_context,
        build_comprehensive_context,
    )
    
    # Build comprehensive context
    comprehensive_ctx = build_comprehensive_context(
        user_profile=actor_ctx.user_profile if actor_ctx else None,
        user_display_name=actor_ctx.display_name if actor_ctx else None,
        user_email=actor_ctx.email if actor_ctx else None,
        user_id=user_id,
        channel_id=ch,
        thread_ts=th,
        rfp_id=rfp_id,
        max_total_chars=50000,
    )
    
    # Also build individual components for context complexity estimation
    rfp_state_context = build_rfp_state_context(rfp_id=rfp_id, journal_limit=10, events_limit=10) if rfp_id else ""
    related_rfps_context = build_related_rfps_context(rfp_id=rfp_id, limit=5) if rfp_id else ""
    cross_thread_context = build_cross_thread_context(
        rfp_id=rfp_id,
        current_channel_id=ch,
        current_thread_ts=th,
        limit=5,
    ) if rfp_id else ""

    system = "\n".join(
        [
            "You are Polaris Operator, a Slack-connected agent for an RFP→Proposal→Contracting platform.",
            "You are stateless: you MUST reconstruct context by calling tools every invocation.",
            "",
            "Slack Permissions:",
            SLACK_BOT_SCOPES.strip(),
            "",
            "Agent Jobs System:",
            AGENT_JOBS_SYSTEM_DOCS.strip(),
            "",
            "Available Job Types:",
            AGENT_JOB_TYPES_DOCS.strip(),
            "",
            "Tool Categories:",
            AGENT_TOOL_CATEGORIES_DOCS.strip(),
            "",
            "Critical rules:",
            "- Do not treat Slack chat history as truth. Use platform tools + OpportunityState + Journal + Events.",
            "- However, use the thread conversation history below to remember previous context in this thread (channel names, permissions, user preferences, etc.).",
            "- Default to silence. If you need to communicate, use `slack_post_summary` (or `slack_ask_clarifying_question` only when blocking).",
            "- Before posting, update durable artifacts: call `opportunity_patch` and/or `journal_append` so the system remembers.",
            "- Never invent IDs, dates, or commitments. Cite tool output or ask a single clarifying question.",
            "- For code changes: first call `create_change_proposal` (stores a patch + rationale). Then propose an approval-gated action `self_modify_open_pr` with the `proposalId`.",
            "- Use `agent_job_list` to check job status when users ask about scheduled/running jobs.",
            "- When users ask about their resume, check the user context for resume S3 keys. For PDF or DOCX files, use `extract_resume_text` to extract text content. For plain text files, use `s3_get_object_text`. For binary files that need downloading, use `s3_presign_get` to get a download URL.",
            "- When users ask about their professional background, check both user context (job titles, certifications) and linked team member information (biography, bioProfiles) if available. Use `get_team_member` tool to fetch full team member details if needed.",
            "",
            "Runtime context:",
            f"- channel: {ch}",
            f"- thread_ts: {th}",
            f"- slack_user_id: {str(user_id or '').strip() or '(unknown)'}",
            f"- rfp_id_scope: {rfp_id}",
            f"- correlation_id: {corr or '(none)'}",
        ]
    )
    
    # Add comprehensive context (includes all context layers)
    if comprehensive_ctx:
        system += "\n\n" + comprehensive_ctx + "\n"

    input0 = f"{system}\n\nUSER_MESSAGE:\n{q}"

    did_post = False
    steps = 0
    did_load = False
    did_patch = False
    did_journal = False

    def _inject_and_enforce(*, tool_name: str, tool_args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """
        Enforce the operator run protocol:
          - First: opportunity_load
          - Before speaking (slack_post_summary / slack_ask_clarifying_question): write durable artifacts

        Also inject correlationId into relevant tool args for traceability.
        """
        nonlocal did_load, did_patch, did_journal
        name = str(tool_name or "").strip()
        args2 = tool_args if isinstance(tool_args, dict) else {}

        # Correlation id propagation (best-effort)
        if corr and isinstance(args2, dict):
            if name in ("event_append", "opportunity_patch", "slack_post_summary", "slack_ask_clarifying_question"):
                if "correlationId" not in args2:
                    args2["correlationId"] = corr
            if name == "journal_append":
                meta_raw = args2.get("meta")
                meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
                if "correlationId" not in meta:
                    meta["correlationId"] = corr
                args2["meta"] = meta

        # Load-first protocol (do not allow tool usage without state reconstruction).
        if name not in ("opportunity_load", _sa.ACTION_TOOL_NAME) and not did_load:
            return args2, {
                "ok": False,
                "error": "protocol_missing_opportunity_load",
                "hint": "Call opportunity_load first to reconstruct context before using other tools.",
            }

        # Write-it-down protocol: before posting/asking, ensure we wrote durable artifacts.
        if name in ("slack_post_summary", "slack_ask_clarifying_question") and not (did_patch or did_journal):
            return args2, {
                "ok": False,
                "error": "protocol_missing_state_write",
                "hint": "Before posting, call opportunity_patch and/or journal_append so the system remembers next invocation.",
            }

        return args2, None

    # Prefer Responses API; fall back to chat tools if needed.
    if not _sa._supports_responses_api(client):
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": q},
        ]
        while True:
            steps += 1
            if steps > max(1, int(max_steps)):
                break
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=chat_tools,
                tool_choice="auto",
                temperature=0.2,
                max_completion_tokens=1100,
            )
            calls = _sa._chat_tool_calls(completion)
            if not calls:
                text = (completion.choices[0].message.content or "").strip()
                break

            # Add assistant tool-call message.
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c.get("id"),
                            "type": "function",
                            "function": {
                                "name": (c.get("function") or {}).get("name"),
                                "arguments": (c.get("function") or {}).get("arguments"),
                            },
                        }
                        for c in calls
                    ],
                }
            )

            for c in calls:
                call_id = str(c.get("id") or "").strip()
                fn = c.get("function") if isinstance(c.get("function"), dict) else {}
                name = str((fn or {}).get("name") or "").strip()
                raw_args = (fn or {}).get("arguments")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else {}
                except Exception:
                    args = {}

                args, proto_err = _inject_and_enforce(tool_name=name, tool_args=args if isinstance(args, dict) else {})
                if proto_err is not None:
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": _sa._safe_json(proto_err)})
                    continue

                if name == "slack_post_summary" or name == "slack_ask_clarifying_question":
                    did_post = True

                if name == _sa.ACTION_TOOL_NAME:
                    # Use shared risk model: auto-execute low-risk, confirm risky.
                    ans = _sa._handle_proposed_action(
                        tool_args=args if isinstance(args, dict) else {},
                        slack_user_id=user_id,
                        user_sub=actor_user_sub,
                        channel_id=ch,
                        thread_ts=th,
                        question=q,
                        model=model,
                        steps=steps,
                        response_format="chat_tools",
                    )
                    try:
                        post_summary(
                            rfp_id=rfp_id,
                            channel=ch,
                            thread_ts=th,
                            text=str(ans.text or "").strip() or "Done.",
                            blocks=ans.blocks,
                            correlation_id=corr,
                        )
                        did_post = True
                    except Exception:
                        pass
                    return SlackOperatorResult(did_post=did_post, text=None, meta={"steps": steps, "meta": ans.meta})

                tool = OPERATOR_TOOLS.get(name)
                if not tool:
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": _sa._safe_json({"ok": False, "error": "unknown_tool"})})
                    continue
                _tpl, func = tool
                started = time.time()
                try:
                    # Use resilience module for retry and error handling
                    from .agent_resilience import retry_with_classification, classify_error
                    
                    def _execute_tool():
                        return func(args if isinstance(args, dict) else {})
                    
                    result = retry_with_classification(
                        _execute_tool,
                        max_retries=2,
                        base_delay=0.5,
                        max_delay=5.0,
                    )
                except Exception as e:
                    classification = classify_error(e)
                    result = {
                        "ok": False,
                        "error": str(e) or "tool_failed",
                        "errorCategory": classification.category.value,
                        "retryable": classification.retryable,
                    }

                # Update protocol flags on success.
                if bool(result.get("ok")):
                    if name == "opportunity_load":
                        did_load = True
                    elif name == "opportunity_patch":
                        did_patch = True
                    elif name == "journal_append":
                        did_journal = True
                dur_ms = int((time.time() - started) * 1000)
                try:
                    append_event(
                        rfp_id=rfp_id,
                        type="tool_call",
                        tool=name,
                        payload={"ok": bool(result.get("ok")), "durationMs": dur_ms},
                        inputs_redacted={
                            "argsKeys": [str(k) for k in list((args or {}).keys())[:60]] if isinstance(args, dict) else [],
                        },
                        outputs_redacted={
                            "resultPreview": {k: result.get(k) for k in list(result.keys())[:30]} if isinstance(result, dict) else {},
                        },
                        correlation_id=corr,
                    )
                except Exception:
                    pass
                messages.append({"role": "tool", "tool_call_id": call_id, "content": _sa._safe_json(result)})

        # Fallback: if the model returned plain text, post it.
        if not did_post and text:
            try:
                post_summary(rfp_id=rfp_id, channel=ch, thread_ts=th, text=text, correlation_id=corr)
                did_post = True
            except Exception:
                pass
        return SlackOperatorResult(did_post=did_post, text=None, meta={"steps": steps, "response_format": "chat_tools"})

    prev_id: str | None = None
    recent_tools: list[str] = []  # Track recent tool calls for complexity detection
    start_time = time.time()
    while True:
        steps += 1
        if steps > max(1, int(max_steps)):
            break

        # Get tuning with complexity awareness (including context complexity)
        # Estimate context complexity
        context_len = len(input0) if not prev_id else 0  # Approximate context length
        tuning = tuning_for(
            purpose="slack_agent",
            kind="tools",
            attempt=steps,
            recent_tools=recent_tools[-5:] if recent_tools else None,  # Last 5 tools for context
            context_length=context_len,
            has_rfp_state=bool(rfp_id and rfp_state_context),
            has_related_rfps=bool(related_rfps_context),
            has_cross_thread=bool(cross_thread_context),
            is_long_running=False,
        )

        # Use adaptive timeout based on complexity
        from .agent_resilience import adaptive_timeout
        timeout_seconds = adaptive_timeout(
            base_timeout=75.0,
            complexity_score=1.0 + (len(recent_tools) * 0.1) if recent_tools else 1.0,
            previous_failures=0,
        )
        
        kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "tool_choice": _sa._tool_choice_allowed(tool_names),
            "reasoning": {"effort": tuning.reasoning_effort},
            "text": {"verbosity": tuning.verbosity},
            "max_output_tokens": 1100,
            "timeout": timeout_seconds,
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id
            kwargs["input"] = []
        else:
            kwargs["input"] = input0

        # Wrap API call with resilience
        from .agent_resilience import retry_with_classification, should_retry_with_adjusted_params
        
        def _call_api():
            return client.responses.create(**kwargs)
        
        try:
            resp = retry_with_classification(
                _call_api,
                max_retries=2,
                base_delay=1.0,
                max_delay=10.0,
            )
        except Exception as e:
            # If API call fails, try with reduced reasoning (graceful degradation)
            should_retry, adjusted = should_retry_with_adjusted_params(e, attempt=1)
            if should_retry and adjusted:
                kwargs["reasoning"] = {"effort": adjusted.get("reasoning_effort", "medium")}
                kwargs["max_output_tokens"] = adjusted.get("max_tokens", 1100)
                resp = client.responses.create(**kwargs)
            else:
                raise
        prev_id = str(getattr(resp, "id", "") or "") or prev_id

        tool_calls = _sa._extract_tool_calls(resp)
        if not tool_calls:
            text = _sa._responses_text(resp).strip()
            break

        outputs: list[dict[str, Any]] = []
        for call in tool_calls:
            call_id = str(call.get("id") or "").strip()
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str((fn or {}).get("name") or "").strip()
            raw_args = (fn or {}).get("arguments")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else {}
            except Exception:
                args = {}

            # Track tool for complexity detection
            if name:
                recent_tools.append(name)
                # Keep only last 10 tools to avoid unbounded growth
                if len(recent_tools) > 10:
                    recent_tools = recent_tools[-10:]

            args, proto_err = _inject_and_enforce(tool_name=name, tool_args=args if isinstance(args, dict) else {})
            if proto_err is not None:
                outputs.append(_sa._tool_output_item(call_id, _sa._safe_json(proto_err)))
                continue

            if name in ("slack_post_summary", "slack_ask_clarifying_question"):
                did_post = True

            if name == _sa.ACTION_TOOL_NAME:
                ans = _sa._handle_proposed_action(
                    tool_args=args if isinstance(args, dict) else {},
                    slack_user_id=user_id,
                    user_sub=actor_user_sub,
                    channel_id=ch,
                    thread_ts=th,
                    question=q,
                    model=model,
                    steps=steps,
                    response_format="responses_tools",
                )
                try:
                    post_summary(
                        rfp_id=rfp_id,
                        channel=ch,
                        thread_ts=th,
                        text=str(ans.text or "").strip() or "Done.",
                        blocks=ans.blocks,
                        correlation_id=corr,
                    )
                    did_post = True
                except Exception:
                    pass
                return SlackOperatorResult(did_post=did_post, text=None, meta={"steps": steps, "response_format": "responses_tools", "meta": ans.meta})

            tool = OPERATOR_TOOLS.get(name)
            if not tool:
                outputs.append(_sa._tool_output_item(call_id, _sa._safe_json({"ok": False, "error": "unknown_tool"})))
                continue
            _tpl, func = tool
            started = time.time()
            try:
                # Use resilience module for retry and error handling
                from .agent_resilience import retry_with_classification, classify_error
                
                def _execute_tool():
                    return func(args if isinstance(args, dict) else {})
                
                result = retry_with_classification(
                    _execute_tool,
                    max_retries=2,
                    base_delay=0.5,
                    max_delay=5.0,
                    on_retry=lambda exc, attempt: log.warning(
                        "slack_operator_tool_retry",
                        tool=name,
                        attempt=attempt,
                        error=str(exc)[:200],
                    ),
                )
            except Exception as e:
                classification = classify_error(e)
                result = {
                    "ok": False,
                    "error": str(e) or "tool_failed",
                    "errorCategory": classification.category.value,
                    "retryable": classification.retryable,
                }

            # Update protocol flags on success.
            if bool(result.get("ok")):
                if name == "opportunity_load":
                    did_load = True
                elif name == "opportunity_patch":
                    did_patch = True
                elif name == "journal_append":
                    did_journal = True
            dur_ms = int((time.time() - started) * 1000)
            try:
                # Enhanced telemetry with performance metrics
                telemetry_payload = {
                    "ok": bool(result.get("ok")),
                    "durationMs": dur_ms,
                    "step": steps,
                    "errorCategory": result.get("errorCategory"),
                    "retryable": result.get("retryable"),
                }
                append_event(
                    rfp_id=rfp_id,
                    type="tool_call",
                    tool=name,
                    payload=telemetry_payload,
                    inputs_redacted={
                        "argsKeys": [str(k) for k in list((args or {}).keys())[:60]] if isinstance(args, dict) else [],
                    },
                    outputs_redacted={
                        "resultPreview": {k: result.get(k) for k in list(result.keys())[:30]} if isinstance(result, dict) else {},
                    },
                    correlation_id=corr,
                )
                # Also log performance metrics
                log.info(
                    "agent_tool_call",
                    tool=name,
                    ok=bool(result.get("ok")),
                    duration_ms=dur_ms,
                    step=steps,
                    rfp_id=rfp_id,
                    error_category=result.get("errorCategory"),
                )
            except Exception:
                pass
            outputs.append(_sa._tool_output_item(call_id, _sa._safe_json(result)))

        # Get updated tuning with latest tool complexity
        tuning2 = tuning_for(
            purpose="slack_agent",
            kind="tools",
            attempt=steps,
            recent_tools=recent_tools[-5:] if recent_tools else None,
        )
        resp2 = client.responses.create(
            model=model,
            previous_response_id=prev_id,
            input=outputs,
            tools=tools,
            tool_choice=_sa._tool_choice_allowed(tool_names),
            reasoning={"effort": tuning2.reasoning_effort},
            text={"verbosity": tuning2.verbosity},
            max_output_tokens=1100,
        )
        prev_id = str(getattr(resp2, "id", "") or "") or prev_id
        tool_calls2 = _sa._extract_tool_calls(resp2)
        if tool_calls2:
            continue
        text = _sa._responses_text(resp2).strip()
        break

    # Fallback: if the model returned plain text and did not post, post it.
    if not did_post and text:
        try:
            post_summary(rfp_id=rfp_id, channel=ch, thread_ts=th, text=text, correlation_id=corr)
            did_post = True
        except Exception:
            pass

    # Log completion telemetry
    try:
        from .agent_telemetry import track_agent_operation
        
        total_duration = int((time.time() - start_time) * 1000)
        track_agent_operation(
            operation_type="slack_operator_agent",
            purpose="slack_agent",
            duration_ms=total_duration,
            steps=steps,
            success=True,
            tool_count=len(recent_tools),
            metadata={"rfp_id": rfp_id, "did_post": did_post},
        )
        if rfp_id:
            append_event(
                rfp_id=rfp_id,
                type="agent_completion",
                tool="slack_operator_agent",
                payload={
                    "steps": steps,
                    "durationMs": total_duration,
                    "didPost": did_post,
                    "success": True,
                    "toolCount": len(recent_tools),
                },
                correlation_id=corr,
            )
    except Exception:
        pass
    
    return SlackOperatorResult(
        did_post=did_post,
        text=None,
        meta={"steps": steps, "response_format": "responses_tools", "response_id": prev_id, "scopedRfpId": rfp_id},
    )

