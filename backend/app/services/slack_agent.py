from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..ai.client import AiNotConfigured, AiUpstreamError, _client
from ..ai.context import clip_text, normalize_ws
from ..ai.tuning import tuning_for
from ..observability.logging import get_logger
from ..settings import settings
from .agent_events_repo import append_event
from .agent_tools.read_registry import READ_TOOLS as READ_TOOLS_REGISTRY
from .slack_actions_repo import create_action, get_action, mark_action_done
from .slack_action_executor import execute_action
from .slack_action_risk import classify_action_risk

# Slack bot token scopes - capabilities the agent has
# (Note: This is duplicated in slack_operator_agent.py to avoid circular imports)
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

log = get_logger("slack_agent")


@dataclass(frozen=True)
class SlackAgentAnswer:
    text: str
    blocks: list[dict[str, Any]] | None = None
    meta: dict[str, Any] | None = None


def _is_whats_my_name(q: str) -> bool:
    s = str(q or "").strip().lower()
    if not s:
        return False
    # Keep this conservative to avoid false positives.
    return bool(
        re.search(r"\bwhat('?s| is)\s+my\s+name\b", s)
        or re.search(r"\bwho\s+am\s+i\b", s)
        or re.search(r"\bdo\s+you\s+know\s+my\s+name\b", s)
    )


def _is_whats_my_preferences(q: str) -> bool:
    s = str(q or "").strip().lower()
    if not s:
        return False
    # Keep this conservative to avoid false positives.
    return bool(
        re.search(r"\bwhat('?s| are)\s+my\s+preferences\b", s)
        or re.search(r"\bwhat\s+do\s+you\s+know\s+about\s+my\s+preferences\b", s)
        or re.search(r"\bdo\s+you\s+have\s+.*\s+preferences\b", s)
        or re.search(r"\bshow\s+my\s+preferences\b", s)
        or re.search(r"\blist\s+my\s+preferences\b", s)
    )


def _frontend_url(path: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    p = str(path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    return base + p


def _rfp_url(rfp_id: str) -> str:
    return _frontend_url(f"/rfps/{str(rfp_id or '').strip()}")


def _proposal_url(pid: str) -> str:
    return _frontend_url(f"/proposals/{str(pid or '').strip()}")


def _responses_text(resp: Any) -> str:
    out = getattr(resp, "output_text", None)
    if isinstance(out, str):
        return out
    try:
        output = getattr(resp, "output", None) or []
        chunks: list[str] = []
        for item in output:
            content = getattr(item, "content", None) or []
            for c in content:
                t = getattr(c, "text", None)
                if isinstance(t, str) and t:
                    chunks.append(t)
        return "\n".join(chunks)
    except Exception:
        return ""


def _resp_to_dict(resp: Any) -> dict[str, Any]:
    if hasattr(resp, "model_dump"):
        try:
            out = resp.model_dump()
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}
    if isinstance(resp, dict):
        return resp
    return {}


def _extract_tool_calls(resp: Any) -> list[dict[str, Any]]:
    d = _resp_to_dict(resp)
    out = d.get("output")
    items = out if isinstance(out, list) else []
    calls: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("type") or "") != "tool_call":
            continue
        calls.append(it)
    return calls


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": parameters,
    }


def _tool_choice_allowed(names: list[str]) -> dict[str, Any]:
    # GPT‑5.2 allowed tools subset (per docs)
    return {
        "type": "allowed_tools",
        "mode": "auto",
        "tools": [{"type": "function", "name": n} for n in names],
    }


def _tool_output_item(tool_call_id: str, output: str) -> dict[str, Any]:
    return {"type": "tool_output", "tool_call_id": tool_call_id, "output": output}


def _safe_json(obj: Any, *, max_chars: int = 25_000) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = json.dumps({"ok": False, "error": "serialization_failed"})
    return clip_text(s, max_chars=max_chars)


def _slim_value(v: Any, *, depth: int = 0, max_depth: int = 3) -> Any:
    """
    Best-effort payload slimming for tool outputs.
    Prevents huge DynamoDB/S3 blobs from flooding the model context.
    """
    if depth >= max_depth:
        if isinstance(v, str):
            return clip_text(v, max_chars=600)
        if isinstance(v, (int, float, bool)) or v is None:
            return v
        return str(type(v).__name__)
    if isinstance(v, str):
        return clip_text(v, max_chars=1800)
    if isinstance(v, bytes):
        return f"<bytes:{len(v)}>"
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        out: list[Any] = []
        for it in v[:30]:
            out.append(_slim_value(it, depth=depth + 1, max_depth=max_depth))
        if len(v) > 30:
            out.append(f"<truncated:{len(v) - 30}>")
        return out
    if isinstance(v, dict):
        out2: dict[str, Any] = {}
        # Keep stable order-ish: sort keys for determinism.
        keys = list(v.keys())
        try:
            keys = sorted(keys, key=lambda x: str(x))
        except Exception:
            pass
        for k in keys[:60]:
            kk = str(k)
            # Avoid dumping obviously huge fields verbatim.
            if kk in ("rawText", "text", "content", "body", "html"):
                out2[kk] = clip_text(str(v.get(k) or ""), max_chars=1200)
                continue
            out2[kk] = _slim_value(v.get(k), depth=depth + 1, max_depth=max_depth)
        if len(keys) > 60:
            out2["_truncatedKeys"] = len(keys) - 60
        return out2
    return clip_text(str(v), max_chars=600)


def _slim_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    return _slim_value(item, depth=0, max_depth=3)

def _supports_responses_api(client: Any) -> bool:
    try:
        r = getattr(client, "responses", None)
        return bool(r) and callable(getattr(r, "create", None))
    except Exception:
        return False


def _to_chat_tool(t: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a Responses-style function tool spec into a Chat Completions tool spec.
    """
    return {
        "type": "function",
        "function": {
            "name": str(t.get("name") or ""),
            "description": str(t.get("description") or ""),
            "parameters": t.get("parameters") or {"type": "object", "properties": {}},
        },
    }


def _chat_tool_calls(completion: Any) -> list[dict[str, Any]]:
    try:
        msg = completion.choices[0].message
        calls = getattr(msg, "tool_calls", None)
        if calls:
            # Convert SDK objects to dict-ish shape.
            out: list[dict[str, Any]] = []
            for c in calls:
                fn = getattr(c, "function", None)
                out.append(
                    {
                        "id": getattr(c, "id", None),
                        "function": {
                            "name": getattr(fn, "name", None),
                            "arguments": getattr(fn, "arguments", None),
                        },
                    }
                )
            return out
    except Exception:
        return []
    return []


ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


READ_TOOLS: dict[str, tuple[dict[str, Any], ToolFn]] = READ_TOOLS_REGISTRY


ACTION_TOOL_NAME = "propose_action"


def _propose_action_tool_def() -> dict[str, Any]:
    return _tool_def(
        ACTION_TOOL_NAME,
        "Propose a safe platform action for Slack confirmation (does not execute).",
        {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "seed_tasks_for_rfp",
                        "assign_task",
                        "complete_task",
                        "update_user_profile",
                        "update_rfp_review",
                        # Self-modifying pipeline (approval-gated)
                        "self_modify_open_pr",
                        "self_modify_check_pr",
                        "self_modify_verify_ecs",
                        # Infra operations (approval-gated)
                        "ecs_update_service",
                        "s3_copy_object",
                        "s3_move_object",
                        "s3_delete_object",
                        "cognito_disable_user",
                        "cognito_enable_user",
                        "sqs_redrive_dlq",
                        "github_create_issue",
                        "github_comment",
                        "github_add_labels",
                        "github_rerun_workflow_run",
                        "github_dispatch_workflow",
                    ],
                },
                "args": {"type": "object"},
                "summary": {"type": "string", "maxLength": 400},
                "risk": {"type": "string", "enum": ["low", "medium", "high", "destructive"]},
                "requiresConfirmation": {"type": "boolean"},
                "idempotencyKey": {"type": "string", "maxLength": 120},
            },
            "required": ["action", "args", "summary"],
            "additionalProperties": False,
        },
    )


def _blocks_for_proposed_action(*, action_id: str, summary: str) -> list[dict[str, Any]]:
    aid = str(action_id or "").strip()
    s = str(summary or "").strip() or "Proposed action"
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Proposed action*\n{s}\n\nConfirm?"}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Confirm"},
                    "style": "primary",
                    "action_id": "polaris_confirm_action",
                    "value": aid,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "action_id": "polaris_cancel_action",
                    "value": aid,
                },
            ],
        },
    ]


def _handle_proposed_action(
    *,
    tool_args: dict[str, Any],
    slack_user_id: str | None,
    user_sub: str | None,
    channel_id: str | None,
    thread_ts: str | None,
    question: str,
    model: str,
    steps: int,
    response_format: str,
) -> SlackAgentAnswer:
    action = str((tool_args or {}).get("action") or "").strip()
    aargs = (tool_args or {}).get("args") if isinstance(tool_args, dict) else {}
    aargs = aargs if isinstance(aargs, dict) else {}
    summary = str((tool_args or {}).get("summary") or "").strip()
    risk = str((tool_args or {}).get("risk") or "").strip().lower() or None
    req_conf = (tool_args or {}).get("requiresConfirmation")
    idem = str((tool_args or {}).get("idempotencyKey") or "").strip() or None

    decision = classify_action_risk(action=action, args=aargs)
    if risk not in ("low", "medium", "high", "destructive"):
        risk = decision.risk
    if not isinstance(req_conf, bool):
        req_conf = bool(decision.requires_confirmation)

    # Best-effort idempotency for Slack retries: keep a short-lived in-process cache.
    cache_key = f"{str(slack_user_id or '').strip()}::{idem}" if idem else None
    saved: dict[str, Any] | None = None
    if cache_key:
        try:
            _ts, _aid = _IDEMPOTENCY_CACHE.get(cache_key, (0.0, None))
            if _aid and (time.time() - float(_ts)) < 10 * 60:
                existing = get_action(str(_aid))
                if isinstance(existing, dict) and str(existing.get("status") or "") == "proposed":
                    saved = existing
        except Exception:
            saved = None

    if not saved:
        saved = create_action(
            kind=action or "unknown",
            payload={
                "action": action,
                "args": aargs,
                "summary": summary,
                "risk": risk,
                "requiresConfirmation": bool(req_conf),
                "idempotencyKey": idem,
                "requestedBySlackUserId": slack_user_id,
                "channelId": channel_id,
                "threadTs": thread_ts,
                "question": question,
            },
            ttl_seconds=900,
        )
        if cache_key:
            try:
                _IDEMPOTENCY_CACHE[cache_key] = (time.time(), str(saved.get("actionId") or "").strip() or None)
            except Exception:
                pass
    aid = str(saved.get("actionId") or "").strip()

    # Confirm path (default for anything non-low-risk)
    if bool(req_conf):
        blocks = _blocks_for_proposed_action(action_id=aid, summary=summary or action)
        return SlackAgentAnswer(
            text=f"{summary}\n\nAction id: `{aid}`",
            blocks=blocks,
            meta={"model": model, "steps": steps, "response_format": response_format, "proposedAction": saved},
        )

    # Auto-execute low-risk actions immediately.
    exec_args = dict(aargs)
    if slack_user_id:
        exec_args.setdefault("_actorSlackUserId", slack_user_id)
        exec_args.setdefault("_requestedBySlackUserId", slack_user_id)
    if user_sub:
        exec_args.setdefault("_actorUserSub", user_sub)
        exec_args.setdefault("_requestedByUserSub", user_sub)
    if channel_id:
        exec_args.setdefault("channelId", channel_id)
    if thread_ts:
        exec_args.setdefault("threadTs", thread_ts)
    if question:
        exec_args.setdefault("question", question)
    try:
        result = execute_action(action_id=aid, kind=action, args=exec_args)
    except Exception as e:
        result = {"ok": False, "error": str(e) or "execution_failed"}

    try:
        mark_action_done(action_id=aid, status="done" if result.get("ok") else "failed", result=result)
    except Exception:
        pass

    # Best-effort audit (non-RFP-scoped, so we use a stable pseudo RFP id)
    try:
        append_event(
            rfp_id="rfp_slack_agent",
            type="action_auto_execute",
            tool=action,
            payload={"ok": bool(result.get("ok")), "risk": risk},
            inputs_redacted={"argsKeys": [str(k) for k in list(exec_args.keys())[:60]]},
            outputs_redacted={"resultPreview": {k: result.get(k) for k in list(result.keys())[:30]} if isinstance(result, dict) else {}},
            created_by="slack_agent",
        )
    except Exception:
        pass

    if result.get("ok"):
        msg = "Done."
    else:
        msg = f"Failed: `{result.get('error')}`"
    return SlackAgentAnswer(
        text="\n".join([summary or action or "Action", msg, f"Action id: `{aid}`"]).strip(),
        blocks=None,
        meta={"model": model, "steps": steps, "response_format": response_format, "autoExecuted": True, "result": result},
    )


# (ts, actionId)
_IDEMPOTENCY_CACHE: dict[str, tuple[float, str | None]] = {}


def run_slack_agent_question(
    *,
    question: str,
    user_id: str | None,
    user_display_name: str | None = None,
    user_email: str | None = None,
    user_profile: dict[str, Any] | None = None,
    channel_id: str | None,
    thread_ts: str | None = None,
    max_steps: int = 6,
) -> SlackAgentAnswer:
    """
    Read-only Slack Q&A agent using GPT‑5.2 + tool calling.
    """
    q = normalize_ws(question, max_chars=4000)
    if not q:
        return SlackAgentAnswer(
            text="Ask a question like: `What RFPs are due this week?` or `Summarize the latest RFP.`"
        )

    # Deterministic personalization for common identity questions.
    if _is_whats_my_name(q):
        prof = user_profile if isinstance(user_profile, dict) else {}
        preferred = str(prof.get("preferredName") or "").strip() if isinstance(prof, dict) else ""
        full = str(prof.get("fullName") or "").strip() if isinstance(prof, dict) else ""
        name = preferred or full or str(user_display_name or "").strip()
        if name:
            src = "profile" if (preferred or full) else "Slack"
            return SlackAgentAnswer(text=f"Your name is *{name}* (from {src}).")
        return SlackAgentAnswer(text="I don’t know your name yet. Set it in your profile and I’ll remember it.")

    # Deterministic handler for preference questions.
    if _is_whats_my_preferences(q):
        prof = user_profile if isinstance(user_profile, dict) else {}
        prefs = prof.get("aiPreferences") if isinstance(prof.get("aiPreferences"), dict) else {}
        user_sub = str(prof.get("_id") or prof.get("userSub") or "").strip()
        
        if isinstance(prefs, dict) and prefs:
            try:
                # Format preferences nicely for display
                prefs_str = json.dumps(prefs, ensure_ascii=False, indent=2)
                return SlackAgentAnswer(
                    text=f"Here are your saved preferences:\n\n```\n{prefs_str}\n```"
                )
            except Exception:
                # Fallback to simple format if JSON serialization fails
                pref_lines = []
                for k, v in prefs.items():
                    if isinstance(v, str):
                        pref_lines.append(f"• {k}: {v}")
                    else:
                        pref_lines.append(f"• {k}: {json.dumps(v, ensure_ascii=False)}")
                return SlackAgentAnswer(
                    text="Here are your saved preferences:\n\n" + "\n".join(pref_lines) if pref_lines else "No preferences found."
                )
        
        # No preferences found
        if user_sub:
            return SlackAgentAnswer(
                text=f"I don't currently have any saved preferences for you (user_sub: `{user_sub}`).\n\nIf you tell me what you want saved (e.g., default proposal tone, preferred section owners, turnaround times, notification cadence, naming conventions), I can store it for next time."
            )
        return SlackAgentAnswer(
            text="I don't currently have any saved preferences for you.\n\nIf you tell me what you want saved (e.g., default proposal tone, preferred section owners, turnaround times, notification cadence, naming conventions), I can store it for next time."
        )


    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")

    model = settings.openai_model_for("slack_agent")
    client = _client(timeout_s=60)

    tools = [tpl for (tpl, _fn) in READ_TOOLS.values()]
    if bool(settings.slack_agent_actions_enabled):
        tools.append(_propose_action_tool_def())
    tool_names = [tpl["name"] for tpl in tools if isinstance(tpl, dict) and tpl.get("name")]
    chat_tools = [_to_chat_tool(tpl) for tpl in tools if isinstance(tpl, dict)]

    # Use enhanced context builder for comprehensive context
    from .agent_context_builder import (
        build_user_context,
        build_thread_context,
        build_comprehensive_context,
    )
    
    # Build comprehensive context
    comprehensive_ctx = build_comprehensive_context(
        user_profile=user_profile,
        user_display_name=user_display_name,
        user_email=user_email,
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        rfp_id=None,  # slack_agent is read-only, no RFP scope
        max_total_chars=50000,
    )
    
    # Extract user context and thread context for backward compatibility
    user_ctx = build_user_context(
        user_profile=user_profile,
        user_display_name=user_display_name,
        user_email=user_email,
        user_id=user_id,
    )
    thread_context = build_thread_context(
        channel_id=channel_id,
        thread_ts=thread_ts,
        limit=100,
    )

    system = "\n".join(
        [
            "You are Polaris, a Slack assistant for an RFP/proposal workflow platform.",
            "You can answer questions by calling tools to fetch current platform data.",
            "",
            "Slack Permissions:",
            SLACK_BOT_SCOPES.strip(),
            "",
            "You may also inspect raw platform storage *read-only* using tools:",
            "- DynamoDB main table uses keys like pk/sk and GSI1 (gsi1pk/gsi1sk). Prefer querying by pk or gsi1pk; avoid broad scans.",
            "- S3 assets bucket stores artifacts under prefixes like `rfp/` and `team/`.",
            "If the user asks you to perform an action (seed tasks, assign/complete a task, or update their saved preferences/memory), call `propose_action` with a concise summary and the minimal args needed.",
            "Never execute actions yourself; always propose then wait for confirmation.",
            "",
            "User context (authoritative; do not guess beyond this):",
            user_ctx or "- (none provided)",
            "",
            "Enhanced context (for deeper awareness):",
            comprehensive_ctx or "- (none provided)",
            "",
            "Output rules:",
            "- Be concise. Prefer 1–2 short paragraphs, OR a short list when listing items.",
            "- Include deep links when referencing an item (use tool-provided `url` fields).",
            "- If you are uncertain, call a tool or ask a single clarifying question.",
            "- Do NOT invent IDs, dates, or numbers. Use tool results only.",
            "- Use the thread conversation history below to remember previous context (channel names, permissions, user preferences, etc.).",
            "- When users ask about their resume, check the user context for resume S3 keys. For PDF or DOCX files, use `extract_resume_text` to extract text content. For plain text files, use `s3_get_object_text`. For binary files that need downloading, use `s3_presign_get` to get a download URL.",
            "- When users ask about their professional background, check both user context (job titles, certifications) and linked team member information (biography, bioProfiles) if available. Use `get_team_member` tool to fetch full team member details if needed.",
            "",
            "Slack formatting:",
            "- Use bullets only when presenting a list (do not force bullets for single sentences).",
            "- Put IDs in backticks.",
        ]
    )
    if thread_context:
        system += thread_context

    # First call: provide combined instruction + question as plain input text.
    input0 = f"{system}\n\nUSER_QUESTION:\n{q}"

    # If the runtime SDK does not support Responses API, fall back to Chat Completions tool calling.
    if not _supports_responses_api(client):
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": q},
        ]
        steps = 0
        while True:
            steps += 1
            if steps > max(1, int(max_steps)):
                raise AiUpstreamError("slack_agent_max_steps_exceeded")

            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=chat_tools,
                tool_choice="auto",
                temperature=0.2,
                max_completion_tokens=900,
            )

            calls = _chat_tool_calls(completion)
            if not calls:
                out = (completion.choices[0].message.content or "").strip()
                if not out:
                    raise AiUpstreamError("empty_model_response")
                answer = SlackAgentAnswer(
                    text=out,
                    meta={"model": model, "steps": steps, "response_format": "chat_tools"},
                )
                
                # Store episodic memory for this interaction (best-effort, non-blocking)
                user_sub_from_profile = str(user_profile.get("_id") or user_profile.get("userSub") or "").strip() if user_profile else None
                if user_sub_from_profile:
                    try:
                        from .agent_memory_hooks import store_episodic_memory_from_agent_interaction
                        # Resolve full actor context for provenance
                        slack_user_id_for_memory = user_id
                        cognito_user_id_for_memory = user_sub_from_profile  # user_sub should be cognito sub
                        try:
                            from .slack_actor_context import resolve_actor_context
                            actor_ctx = resolve_actor_context(slack_user_id=user_id, force_refresh=False)
                            if actor_ctx.user_sub:
                                cognito_user_id_for_memory = actor_ctx.user_sub
                            if actor_ctx.slack_user_id:
                                slack_user_id_for_memory = actor_ctx.slack_user_id
                        except Exception:
                            pass  # Use defaults if resolution fails
                        
                        store_episodic_memory_from_agent_interaction(
                            user_sub=user_sub_from_profile,
                            user_message=q,
                            agent_response=out,
                            context={
                                "channelId": channel_id,
                                "threadTs": thread_ts,
                                "steps": steps,
                                "model": model,
                            },
                            cognito_user_id=cognito_user_id_for_memory,
                            slack_user_id=slack_user_id_for_memory,
                            slack_channel_id=channel_id,
                            slack_thread_ts=thread_ts,
                            source="slack_agent",
                        )
                    except Exception:
                        pass  # Non-critical
                
                return answer

            # Add the assistant tool call message (required by tool protocol)
            try:
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
            except Exception:
                # If formatting fails, just break.
                raise AiUpstreamError("tool_call_format_failed")

            # Execute each tool call and append tool outputs
            for c in calls:
                call_id = str(c.get("id") or "").strip()
                fn = c.get("function") if isinstance(c.get("function"), dict) else {}
                name = str((fn or {}).get("name") or "").strip()
                raw_args = (fn or {}).get("arguments")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else {}
                except Exception:
                    args = {}

                if name == ACTION_TOOL_NAME:
                    return _handle_proposed_action(
                        tool_args=args if isinstance(args, dict) else {},
                        slack_user_id=user_id,
                        user_sub=user_sub or None,
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        question=q,
                        model=model,
                        steps=steps,
                        response_format="chat_tools",
                    )

                tool = READ_TOOLS.get(name)
                if not tool:
                    messages.append(
                        {"role": "tool", "tool_call_id": call_id, "content": _safe_json({"ok": False, "error": "unknown_tool"})}
                    )
                    continue
                _tpl, func = tool
                try:
                    # Use resilience module for retry and error handling
                    from .agent_resilience import retry_with_classification
                    
                    def _execute_tool():
                        return func(args if isinstance(args, dict) else {})
                    
                    result = retry_with_classification(
                        _execute_tool,
                        max_retries=2,
                        base_delay=0.5,
                        max_delay=5.0,
                    )
                except Exception as e:
                    from .agent_resilience import classify_error
                    classification = classify_error(e)
                    result = {
                        "ok": False,
                        "error": str(e) or "tool_failed",
                        "errorCategory": classification.category.value,
                        "retryable": classification.retryable,
                    }
                try:
                    append_event(
                        rfp_id="rfp_slack_agent",
                        type="tool_call",
                        tool=name,
                        payload={"ok": bool(result.get("ok"))},
                        inputs_redacted={
                            "argsKeys": [str(k) for k in list((args or {}).keys())[:60]] if isinstance(args, dict) else [],
                            "channelId": channel_id,
                            "threadTs": thread_ts,
                        },
                        outputs_redacted={
                            "resultPreview": {k: result.get(k) for k in list(result.keys())[:30]} if isinstance(result, dict) else {}
                        },
                        created_by="slack_agent",
                        correlation_id=None,
                    )
                except Exception:
                    pass
                messages.append(
                    {"role": "tool", "tool_call_id": call_id, "content": _safe_json(result)}
                )

    prev_id: str | None = None
    steps = 0
    start_time = time.time()
    meta: dict[str, Any] = {"model": model, "steps": 0, "started_at": start_time}
    recent_tools: list[str] = []  # Track recent tool calls for complexity detection

    while True:
        steps += 1
        if steps > max(1, int(max_steps)):
            raise AiUpstreamError("slack_agent_max_steps_exceeded")

        # Get tuning with complexity awareness (including context complexity)
        # Estimate context complexity
        context_len = len(input0) if not prev_id else 0  # Approximate context length
        tuning = tuning_for(
            purpose="slack_agent",
            kind="tools",
            attempt=steps,
            recent_tools=recent_tools[-5:] if recent_tools else None,  # Last 5 tools for context
            context_length=context_len,
            has_rfp_state=False,  # slack_agent is read-only, no RFP scope
            has_related_rfps=False,
            has_cross_thread=bool(thread_context),
            is_long_running=False,
        )

        # Use adaptive timeout based on complexity
        from .agent_resilience import adaptive_timeout
        timeout_seconds = adaptive_timeout(
            base_timeout=60.0,
            complexity_score=1.0 + (len(recent_tools) * 0.1),  # Slightly increase for more tools
            previous_failures=0,  # Could track this in future
        )
        
        kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "tool_choice": _tool_choice_allowed(tool_names),
            "reasoning": {"effort": tuning.reasoning_effort},
            "text": {"verbosity": tuning.verbosity},
            "max_output_tokens": 900,
            "timeout": timeout_seconds,
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id
            # For follow-up turns, the input will be provided as tool_output items only.
            kwargs["input"] = []  # required by SDK even if empty
        else:
            kwargs["input"] = input0

        # Wrap API call with resilience
        from .agent_resilience import retry_with_classification
        
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
            from .agent_resilience import should_retry_with_adjusted_params
            should_retry, adjusted = should_retry_with_adjusted_params(e, attempt=1)
            if should_retry and adjusted:
                kwargs["reasoning"] = {"effort": adjusted.get("reasoning_effort", "medium")}
                kwargs["max_output_tokens"] = adjusted.get("max_tokens", 900)
                resp = client.responses.create(**kwargs)
            else:
                raise
        prev_id = str(getattr(resp, "id", "") or "") or prev_id

        tool_calls = _extract_tool_calls(resp)
        if not tool_calls:
            text = _responses_text(resp).strip()
            if not text:
                raise AiUpstreamError("empty_model_response")
            meta["steps"] = steps
            meta["response_id"] = prev_id
            return SlackAgentAnswer(text=text, meta=meta)

        # Execute tool calls and send results back.
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

            # Terminal: model proposed an action.
            if name == ACTION_TOOL_NAME:
                return _handle_proposed_action(
                    tool_args=args if isinstance(args, dict) else {},
                    slack_user_id=user_id,
                    user_sub=user_sub or None,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    question=q,
                    model=model,
                    steps=steps,
                    response_format="responses_tools",
                )

            tool = READ_TOOLS.get(name)
            if not tool:
                outputs.append(_tool_output_item(call_id, _safe_json({"ok": False, "error": "unknown_tool"})))
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
                    max_retries=2,  # Quick retry for tool failures
                    base_delay=0.5,
                    max_delay=5.0,
                    on_retry=lambda exc, attempt: log.warning(
                        "slack_agent_tool_retry",
                        tool=name,
                        attempt=attempt,
                        error=str(exc)[:200],
                    ),
                )
            except Exception as e:
                # Classify error for better reporting
                from .agent_resilience import classify_error
                classification = classify_error(e)
                result = {
                    "ok": False,
                    "error": str(e) or "tool_failed",
                    "errorCategory": classification.category.value,
                    "retryable": classification.retryable,
                }
            dur_ms = int((time.time() - started) * 1000)
            try:
                log.info("slack_agent_tool", tool=name, ok=bool(result.get("ok")), duration_ms=dur_ms)
            except Exception:
                pass
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
                    rfp_id="rfp_slack_agent",
                    type="tool_call",
                    tool=name,
                    payload=telemetry_payload,
                    inputs_redacted={
                        "argsKeys": [str(k) for k in list((args or {}).keys())[:60]] if isinstance(args, dict) else [],
                        "channelId": channel_id,
                        "threadTs": thread_ts,
                    },
                    outputs_redacted={
                        "resultPreview": {k: result.get(k) for k in list(result.keys())[:30]} if isinstance(result, dict) else {}
                    },
                    created_by="slack_agent",
                    correlation_id=None,
                )
                # Also log performance metrics
                log.info(
                    "agent_tool_call",
                    tool=name,
                    ok=bool(result.get("ok")),
                    duration_ms=dur_ms,
                    step=steps,
                    error_category=result.get("errorCategory"),
                )
            except Exception:
                pass
            outputs.append(_tool_output_item(call_id, _safe_json(result)))

        # Continue the loop with tool outputs as the next input items.
        # Responses API: feed tool outputs via previous_response_id.
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
            tool_choice=_tool_choice_allowed(tool_names),
            reasoning={"effort": tuning2.reasoning_effort},
            text={"verbosity": tuning2.verbosity},
            max_output_tokens=900,
        )
        prev_id = str(getattr(resp2, "id", "") or "") or prev_id

        tool_calls2 = _extract_tool_calls(resp2)
        if tool_calls2:
            # Loop again (model needs more tools).
            continue

        text = _responses_text(resp2).strip()
        if not text:
            raise AiUpstreamError("empty_model_response")
        meta["steps"] = steps
        meta["response_id"] = prev_id
        
        # Log completion telemetry
        try:
            from .agent_telemetry import track_agent_operation
            
            total_duration = int((time.time() - (meta.get("started_at") or time.time())) * 1000)
            track_agent_operation(
                operation_type="slack_agent",
                purpose="slack_agent",
                duration_ms=total_duration,
                steps=steps,
                success=True,
                reasoning_effort=tuning.reasoning_effort,
                context_length=len(input0) if not prev_id else 0,
                tool_count=len(recent_tools),
            )
            append_event(
                rfp_id="rfp_slack_agent",
                type="agent_completion",
                tool="slack_agent",
                payload={
                    "steps": steps,
                    "durationMs": total_duration,
                    "reasoningEffort": tuning.reasoning_effort,
                    "success": True,
                    "toolCount": len(recent_tools),
                },
                created_by="slack_agent",
            )
        except Exception:
            pass
        
        return SlackAgentAnswer(text=text, meta=meta)

