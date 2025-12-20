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
from .agent_jobs_repo import create_job as create_agent_job
from .agent_policy import sanitize_opportunity_patch
from .change_proposals_repo import create_change_proposal
from .opportunity_state_repo import ensure_state_exists, get_state, patch_state
from .slack_thread_bindings_repo import get_binding as get_thread_binding, set_binding as set_thread_binding
from .slack_reply_tools import ask_clarifying_question, post_summary

# Reuse proven OpenAI tool-call plumbing from slack_agent to avoid divergence.
from . import slack_agent as _sa


log = get_logger("slack_operator_agent")


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
    job = create_agent_job(job_type=job_type, scope=scope, due_at=due_at, payload=payload, requested_by_user_sub=None)
    return {"ok": True, "job": job}

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
            "Schedule a one-shot agent job for later execution (dueAt ISO time).",
            {
                "type": "object",
                "properties": {
                    "dueAt": {"type": "string", "minLength": 1, "maxLength": 40},
                    "jobType": {"type": "string", "minLength": 1, "maxLength": 120},
                    "scope": {"type": "object"},
                    "payload": {"type": "object"},
                },
                "required": ["dueAt", "jobType", "scope"],
                "additionalProperties": False,
            },
        ),
        _schedule_job_tool,
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

    system = "\n".join(
        [
            "You are Polaris Operator, a Slack-connected agent for an RFP→Proposal→Contracting platform.",
            "You are stateless: you MUST reconstruct context by calling tools every invocation.",
            "",
            "Critical rules:",
            "- Do not treat Slack chat history as truth. Use platform tools + OpportunityState + Journal + Events.",
            "- Default to silence. If you need to communicate, use `slack_post_summary` (or `slack_ask_clarifying_question` only when blocking).",
            "- Before posting, update durable artifacts: call `opportunity_patch` and/or `journal_append` so the system remembers.",
            "- Never invent IDs, dates, or commitments. Cite tool output or ask a single clarifying question.",
            "- For code changes: first call `create_change_proposal` (stores a patch + rationale). Then propose an approval-gated action `self_modify_open_pr` with the `proposalId`.",
            "",
            "Runtime context:",
            f"- channel: {ch}",
            f"- thread_ts: {th}",
            f"- slack_user_id: {str(user_id or '').strip() or '(unknown)'}",
            f"- rfp_id_scope: {rfp_id}",
            f"- correlation_id: {corr or '(none)'}",
        ]
    )

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
                meta = args2.get("meta") if isinstance(args2.get("meta"), dict) else {}
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
                    result = func(args if isinstance(args, dict) else {})
                except Exception as e:
                    result = {"ok": False, "error": str(e) or "tool_failed"}

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
    while True:
        steps += 1
        if steps > max(1, int(max_steps)):
            break

        kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "tool_choice": _sa._tool_choice_allowed(tool_names),
            "reasoning": {"effort": tuning_for(purpose="slack_agent", kind="tools", attempt=steps).reasoning_effort},
            "text": {"verbosity": tuning_for(purpose="slack_agent", kind="tools", attempt=steps).verbosity},
            "max_output_tokens": 1100,
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id
            kwargs["input"] = []
        else:
            kwargs["input"] = input0

        resp = client.responses.create(**kwargs)
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
                result = func(args if isinstance(args, dict) else {})
            except Exception as e:
                result = {"ok": False, "error": str(e) or "tool_failed"}

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
            outputs.append(_sa._tool_output_item(call_id, _sa._safe_json(result)))

        resp2 = client.responses.create(
            model=model,
            previous_response_id=prev_id,
            input=outputs,
            tools=tools,
            tool_choice=_sa._tool_choice_allowed(tool_names),
            reasoning={"effort": tuning_for(purpose="slack_agent", kind="tools", attempt=steps).reasoning_effort},
            text={"verbosity": tuning_for(purpose="slack_agent", kind="tools", attempt=steps).verbosity},
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

    return SlackOperatorResult(
        did_post=did_post,
        text=None,
        meta={"steps": steps, "response_format": "responses_tools", "response_id": prev_id, "scopedRfpId": rfp_id},
    )

