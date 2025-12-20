from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..ai.client import AiNotConfigured, AiUpstreamError, _client
from ..ai.context import clip_text, normalize_ws
from ..observability.logging import get_logger
from ..settings import settings
from . import content_repo
from .proposals_repo import get_proposal_by_id, list_proposals
from .rfps_repo import get_rfp_by_id, list_rfps
from .slack_actions_repo import create_action
from .workflow_tasks_repo import list_tasks_for_rfp

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


def _list_rfps_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 10)
    limit = max(1, min(25, limit))
    resp = list_rfps(page=1, limit=limit, next_token=None)
    data = resp.get("data") if isinstance(resp, dict) else None
    rows = data if isinstance(data, list) else []
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("_id") or r.get("rfpId") or "").strip()
        out.append(
            {
                "rfpId": rid,
                "title": str(r.get("title") or "RFP").strip(),
                "clientName": str(r.get("clientName") or "").strip(),
                "projectType": str(r.get("projectType") or "").strip(),
                "submissionDeadline": str(r.get("submissionDeadline") or "").strip(),
                "fitScore": r.get("fitScore"),
                "url": _rfp_url(rid) if rid else None,
            }
        )
    return {"ok": True, "data": out}


def _search_rfps_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = normalize_ws(str(args.get("query") or ""), max_chars=400)
    if not q:
        return {"ok": False, "error": "missing_query"}
    limit = int(args.get("limit") or 10)
    limit = max(1, min(15, limit))
    resp = list_rfps(page=1, limit=200, next_token=None)
    rows = (resp or {}).get("data") if isinstance(resp, dict) else None
    data = rows if isinstance(rows, list) else []
    hits: list[dict[str, Any]] = []
    ql = q.lower()
    for r in data:
        if not isinstance(r, dict):
            continue
        hay = f"{r.get('title') or ''} {r.get('clientName') or ''} {r.get('projectType') or ''}".lower()
        if ql in hay:
            rid = str(r.get("_id") or r.get("rfpId") or "").strip()
            hits.append(
                {
                    "rfpId": rid,
                    "title": str(r.get("title") or "RFP").strip(),
                    "clientName": str(r.get("clientName") or "").strip(),
                    "projectType": str(r.get("projectType") or "").strip(),
                    "submissionDeadline": str(r.get("submissionDeadline") or "").strip(),
                    "url": _rfp_url(rid) if rid else None,
                }
            )
        if len(hits) >= limit:
            break
    return {"ok": True, "query": q, "data": hits}


def _get_rfp_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    r = get_rfp_by_id(rid)
    if not r:
        return {"ok": False, "error": "not_found"}
    # Keep response bounded.
    raw = str(r.get("rawText") or "")
    r2 = dict(r)
    r2["rawText"] = clip_text(raw, max_chars=9000)
    r2["url"] = _rfp_url(rid)
    return {"ok": True, "rfp": r2}


def _list_proposals_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 10)
    limit = max(1, min(25, limit))
    resp = list_proposals(page=1, limit=limit, next_token=None)
    rows = (resp or {}).get("data") if isinstance(resp, dict) else None
    data = rows if isinstance(rows, list) else []
    out: list[dict[str, Any]] = []
    for p in data[:limit]:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("_id") or p.get("proposalId") or "").strip()
        out.append(
            {
                "proposalId": pid,
                "title": str(p.get("title") or "Proposal").strip(),
                "status": str(p.get("status") or "").strip(),
                "rfpId": str(p.get("rfpId") or "").strip(),
                "url": _proposal_url(pid) if pid else None,
            }
        )
    return {"ok": True, "data": out}


def _search_proposals_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = normalize_ws(str(args.get("query") or ""), max_chars=400)
    if not q:
        return {"ok": False, "error": "missing_query"}
    limit = int(args.get("limit") or 10)
    limit = max(1, min(15, limit))
    resp = list_proposals(page=1, limit=200, next_token=None)
    rows = (resp or {}).get("data") if isinstance(resp, dict) else None
    data = rows if isinstance(rows, list) else []
    hits: list[dict[str, Any]] = []
    ql = q.lower()
    for p in data:
        if not isinstance(p, dict):
            continue
        hay = f"{p.get('title') or ''} {p.get('status') or ''} {p.get('rfpId') or ''}".lower()
        if ql in hay:
            pid = str(p.get("_id") or p.get("proposalId") or "").strip()
            hits.append(
                {
                    "proposalId": pid,
                    "title": str(p.get("title") or "Proposal").strip(),
                    "status": str(p.get("status") or "").strip(),
                    "rfpId": str(p.get("rfpId") or "").strip(),
                    "url": _proposal_url(pid) if pid else None,
                }
            )
        if len(hits) >= limit:
            break
    return {"ok": True, "query": q, "data": hits}


def _get_proposal_tool(args: dict[str, Any]) -> dict[str, Any]:
    pid = str(args.get("proposalId") or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_proposalId"}
    p = get_proposal_by_id(pid, include_sections=True)
    if not p:
        return {"ok": False, "error": "not_found"}
    p2 = dict(p)
    # Bound sections payload (often large).
    secs = p2.get("sections")
    if isinstance(secs, dict):
        # Keep only keys + content length
        slim: dict[str, Any] = {}
        for k, v in list(secs.items())[:80]:
            if isinstance(v, dict):
                c = v.get("content")
                slim[str(k)] = {
                    **{kk: vv for kk, vv in v.items() if kk != "content"},
                    "contentPreview": clip_text(str(c or ""), max_chars=700),
                }
            else:
                slim[str(k)] = {"contentPreview": clip_text(str(v or ""), max_chars=700)}
        p2["sections"] = slim
    p2["url"] = _proposal_url(pid)
    return {"ok": True, "proposal": p2}


def _list_tasks_for_rfp_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    resp = list_tasks_for_rfp(rfp_id=rid, limit=200, next_token=None)
    return {"ok": True, **(resp if isinstance(resp, dict) else {"data": []})}


def _get_company_tool(args: dict[str, Any]) -> dict[str, Any]:
    cid = str(args.get("companyId") or "").strip()
    if not cid:
        return {"ok": False, "error": "missing_companyId"}
    c = content_repo.get_company_by_company_id(cid)
    if not c:
        return {"ok": False, "error": "not_found"}
    # Keep response bounded.
    c2 = dict(c)
    for k in ("description", "coverLetter", "firmQualificationsAndExperience"):
        if k in c2:
            c2[k] = clip_text(str(c2.get(k) or ""), max_chars=2500)
    return {"ok": True, "company": c2}


ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


READ_TOOLS: dict[str, tuple[dict[str, Any], ToolFn]] = {
    "list_rfps": (
        _tool_def(
            "list_rfps",
            "List recent RFPs (returns compact fields + links).",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 25}},
                "required": [],
                "additionalProperties": False,
            },
        ),
        _list_rfps_tool,
    ),
    "search_rfps": (
        _tool_def(
            "search_rfps",
            "Search RFPs by keywords over title/client/type (returns compact fields + links).",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 400},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 15},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        _search_rfps_tool,
    ),
    "get_rfp": (
        _tool_def(
            "get_rfp",
            "Fetch one RFP by ID (includes clipped rawText).",
            {
                "type": "object",
                "properties": {"rfpId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["rfpId"],
                "additionalProperties": False,
            },
        ),
        _get_rfp_tool,
    ),
    "list_proposals": (
        _tool_def(
            "list_proposals",
            "List recent proposals (compact fields + links).",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 25}},
                "required": [],
                "additionalProperties": False,
            },
        ),
        _list_proposals_tool,
    ),
    "search_proposals": (
        _tool_def(
            "search_proposals",
            "Search proposals by keywords over title/status/rfpId (compact fields + links).",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 400},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 15},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        _search_proposals_tool,
    ),
    "get_proposal": (
        _tool_def(
            "get_proposal",
            "Fetch one proposal by ID (includes clipped section previews).",
            {
                "type": "object",
                "properties": {"proposalId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["proposalId"],
                "additionalProperties": False,
            },
        ),
        _get_proposal_tool,
    ),
    "list_tasks_for_rfp": (
        _tool_def(
            "list_tasks_for_rfp",
            "List workflow tasks for a given RFP.",
            {
                "type": "object",
                "properties": {"rfpId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["rfpId"],
                "additionalProperties": False,
            },
        ),
        _list_tasks_for_rfp_tool,
    ),
    "get_company": (
        _tool_def(
            "get_company",
            "Fetch a company from the content library by companyId.",
            {
                "type": "object",
                "properties": {"companyId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["companyId"],
                "additionalProperties": False,
            },
        ),
        _get_company_tool,
    ),
}


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
                        # Self-modifying pipeline (approval-gated)
                        "self_modify_open_pr",
                        "self_modify_check_pr",
                        "self_modify_verify_ecs",
                    ],
                },
                "args": {"type": "object"},
                "summary": {"type": "string", "maxLength": 400},
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
            return SlackAgentAnswer(text=f"- Your name is *{name}* (from {src}).")
        return SlackAgentAnswer(text="- I don’t know your name yet. Set it in your profile and I’ll remember it.")

    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")

    model = settings.openai_model_for("slack_agent")
    client = _client(timeout_s=60)

    tools = [tpl for (tpl, _fn) in READ_TOOLS.values()]
    if bool(settings.slack_agent_actions_enabled):
        tools.append(_propose_action_tool_def())
    tool_names = [tpl["name"] for tpl in tools if isinstance(tpl, dict) and tpl.get("name")]
    chat_tools = [_to_chat_tool(tpl) for tpl in tools if isinstance(tpl, dict)]

    # User memory/preferences injected into system prompt (bounded).
    prof = user_profile if isinstance(user_profile, dict) else {}
    preferred = str(prof.get("preferredName") or "").strip()
    full = str(prof.get("fullName") or "").strip()
    effective_name = preferred or full or (str(user_display_name or "").strip() if user_display_name else "")
    prefs = prof.get("aiPreferences") if isinstance(prof.get("aiPreferences"), dict) else {}
    mem = str(prof.get("aiMemorySummary") or "").strip()
    user_ctx_lines: list[str] = []
    if effective_name:
        user_ctx_lines.append(f"- name: {effective_name}")
    if user_email:
        user_ctx_lines.append(f"- email: {str(user_email).strip().lower()}")
    if user_id:
        user_ctx_lines.append(f"- slack_user_id: {str(user_id).strip()}")
    if isinstance(prefs, dict) and prefs:
        # Keep this compact.
        try:
            user_ctx_lines.append(f"- preferences_json: {clip_text(json.dumps(prefs, ensure_ascii=False), max_chars=1200)}")
        except Exception:
            pass
    if mem:
        user_ctx_lines.append(f"- memory_summary: {clip_text(mem, max_chars=1200)}")
    user_ctx = "\n".join(user_ctx_lines).strip()

    system = "\n".join(
        [
            "You are Polaris, a Slack assistant for an RFP/proposal workflow platform.",
            "You can answer questions by calling tools to fetch current platform data.",
            "If the user asks you to perform an action (seed tasks, assign/complete a task, or update their saved preferences/memory), call `propose_action` with a concise summary and the minimal args needed.",
            "Never execute actions yourself; always propose then wait for confirmation.",
            "",
            "User context (authoritative; do not guess beyond this):",
            user_ctx or "- (none provided)",
            "",
            "Output rules:",
            "- Be concise: 3–7 bullets maximum.",
            "- Include deep links when referencing an item (use tool-provided `url` fields).",
            "- If you are uncertain, call a tool or ask a single clarifying question.",
            "- Do NOT invent IDs, dates, or numbers. Use tool results only.",
            "",
            "Slack formatting:",
            "- Use mrkdwn bullets (`- ...`).",
            "- Put IDs in backticks.",
        ]
    )

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
                return SlackAgentAnswer(
                    text=out,
                    meta={"model": model, "steps": steps, "response_format": "chat_tools"},
                )

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
                    action = str((args or {}).get("action") or "").strip()
                    aargs = (args or {}).get("args") if isinstance(args, dict) else {}
                    summary = str((args or {}).get("summary") or "").strip()
                    saved = create_action(
                        kind=action or "unknown",
                        payload={
                            "action": action,
                            "args": aargs if isinstance(aargs, dict) else {},
                            "requestedBySlackUserId": user_id,
                            "channelId": channel_id,
                            "threadTs": thread_ts,
                            "question": q,
                        },
                        ttl_seconds=600,
                    )
                    aid = str(saved.get("actionId") or "").strip()
                    blocks = _blocks_for_proposed_action(action_id=aid, summary=summary or action)
                    return SlackAgentAnswer(
                        text=f"{summary}\n\nAction id: `{aid}`",
                        blocks=blocks,
                        meta={"model": model, "steps": steps, "response_format": "chat_tools", "proposedAction": saved},
                    )

                tool = READ_TOOLS.get(name)
                if not tool:
                    messages.append(
                        {"role": "tool", "tool_call_id": call_id, "content": _safe_json({"ok": False, "error": "unknown_tool"})}
                    )
                    continue
                _tpl, func = tool
                try:
                    result = func(args if isinstance(args, dict) else {})
                except Exception as e:
                    result = {"ok": False, "error": str(e) or "tool_failed"}
                messages.append(
                    {"role": "tool", "tool_call_id": call_id, "content": _safe_json(result)}
                )

    prev_id: str | None = None
    steps = 0
    meta: dict[str, Any] = {"model": model, "steps": 0}

    while True:
        steps += 1
        if steps > max(1, int(max_steps)):
            raise AiUpstreamError("slack_agent_max_steps_exceeded")

        kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "tool_choice": _tool_choice_allowed(tool_names),
            "reasoning": {"effort": str(settings.openai_reasoning_effort_json or "low")},
            "text": {"verbosity": str(settings.openai_text_verbosity_json or "low")},
            "max_output_tokens": 900,
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id
            # For follow-up turns, the input will be provided as tool_output items only.
            kwargs["input"] = []  # required by SDK even if empty
        else:
            kwargs["input"] = input0

        resp = client.responses.create(**kwargs)
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

            # Terminal: model proposed an action.
            if name == ACTION_TOOL_NAME:
                action = str((args or {}).get("action") or "").strip()
                aargs = (args or {}).get("args") if isinstance(args, dict) else {}
                summary = str((args or {}).get("summary") or "").strip()
                saved = create_action(
                    kind=action or "unknown",
                    payload={
                        "action": action,
                        "args": aargs if isinstance(aargs, dict) else {},
                        "requestedBySlackUserId": user_id,
                        "channelId": channel_id,
                        "threadTs": thread_ts,
                        "question": q,
                    },
                    ttl_seconds=600,
                )
                aid = str(saved.get("actionId") or "").strip()
                blocks = _blocks_for_proposed_action(action_id=aid, summary=summary or action)
                return SlackAgentAnswer(
                    text=f"{summary}\n\nAction id: `{aid}`",
                    blocks=blocks,
                    meta={"model": model, "steps": steps, "response_id": prev_id, "proposedAction": saved},
                )

            tool = READ_TOOLS.get(name)
            if not tool:
                outputs.append(_tool_output_item(call_id, _safe_json({"ok": False, "error": "unknown_tool"})))
                continue
            _tpl, func = tool
            started = time.time()
            try:
                result = func(args if isinstance(args, dict) else {})
            except Exception as e:
                result = {"ok": False, "error": str(e) or "tool_failed"}
            dur_ms = int((time.time() - started) * 1000)
            try:
                log.info("slack_agent_tool", tool=name, ok=bool(result.get("ok")), duration_ms=dur_ms)
            except Exception:
                pass
            outputs.append(_tool_output_item(call_id, _safe_json(result)))

        # Continue the loop with tool outputs as the next input items.
        # Responses API: feed tool outputs via previous_response_id.
        resp2 = client.responses.create(
            model=model,
            previous_response_id=prev_id,
            input=outputs,
            tools=tools,
            tool_choice=_tool_choice_allowed(tool_names),
            reasoning={"effort": str(settings.openai_reasoning_effort_json or "low")},
            text={"verbosity": str(settings.openai_text_verbosity_json or "low")},
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
        return SlackAgentAnswer(text=text, meta=meta)

