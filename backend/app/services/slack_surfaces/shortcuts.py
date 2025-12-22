from __future__ import annotations

import re
from typing import Any

from ...observability.logging import get_logger
from ...settings import settings
from ...domain.rfp.rfp_analyzer import analyze_rfp
from ...repositories.rfp.rfps_repo import create_rfp_from_analysis
from ..slack_actions_repo import create_action
from ..slack_agent import _blocks_for_proposed_action, run_slack_agent_question
from ..slack_thread_bindings_repo import get_binding as get_thread_binding
from ..slack_web import (
    chat_post_message_result,
    download_slack_file,
    get_user_info,
    slack_user_display_name,
)
from ...repositories.users.user_profiles_repo import get_user_profile_by_slack_user_id
from . import modals as modals_surface

log = get_logger("slack_shortcuts")


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _message_text_from_payload(payload: dict[str, Any]) -> str:
    msg = _as_dict(payload.get("message"))
    return str(msg.get("text") or "").strip()


def _first_pdf_file(payload: dict[str, Any]) -> dict[str, Any] | None:
    msg = _as_dict(payload.get("message"))
    files_raw = msg.get("files")
    files: list[Any] = files_raw if isinstance(files_raw, list) else []
    for f in files:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "").strip().lower()
        mimetype = str(f.get("mimetype") or "").strip().lower()
        filetype = str(f.get("filetype") or "").strip().lower()
        if mimetype == "application/pdf" or filetype == "pdf" or name.endswith(".pdf"):
            return f
    return None


def _extract_rfp_id(text: str) -> str | None:
    t = str(text or "")
    m = re.search(r"\b(rfp_[a-zA-Z0-9-]{6,})\b", t)
    return str(m.group(1)).strip() if m else None


def _rfp_url(rfp_id: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    rid = str(rfp_id or "").strip()
    return f"{base}/rfps/{rid}"


def handle_shortcut(*, payload: dict[str, Any], background_tasks: Any) -> dict[str, Any]:
    """
    Handle message/global shortcuts.

    For v1 we keep this minimal and post an in-thread response.
    """
    cb = str(payload.get("callback_id") or payload.get("type") or "").strip()
    user = _as_dict(payload.get("user"))
    channel = _as_dict(payload.get("channel"))
    user_id = str(user.get("id") or "").strip()
    channel_id = str(channel.get("id") or "").strip()

    # Slack sometimes provides message_ts; if present, thread on it.
    msg = _as_dict(payload.get("message"))
    msg_ts = str(msg.get("ts") or "").strip() or None
    thread_ts = str(msg.get("thread_ts") or "").strip() or None
    th = thread_ts or msg_ts
    trigger_id = str(payload.get("trigger_id") or "").strip()

    # Minimal: "Summarize" shortcut - feed message text to agent as context.
    if cb in ("polaris_summarize_message", "summarize_message", "summarize"):
        text = _message_text_from_payload(payload)
        q = f"Summarize this Slack message for an RFP/proposal workflow:\n\n{text}"

        slack_user = get_user_info(user_id=user_id) if user_id else None
        display_name = slack_user_display_name(slack_user) if slack_user else None
        user_profile = get_user_profile_by_slack_user_id(slack_user_id=user_id) if user_id else None

        ans = run_slack_agent_question(
            question=q,
            user_id=user_id or None,
            user_display_name=display_name,
            user_email=None,
            user_profile=user_profile,
            channel_id=channel_id or None,
            thread_ts=th,
        )
        if channel_id and th:
            chat_post_message_result(text=str(ans.text or "").strip() or "No answer.", channel=channel_id, thread_ts=th, unfurl_links=False)
        return {"response_type": "ephemeral", "text": "Posted summary in thread."}

    # Modal wizards (message shortcuts)
    if cb in ("polaris_bind_thread", "bind_thread"):
        if not channel_id or not th or not trigger_id:
            return {"response_type": "ephemeral", "text": "Missing channel/thread context."}
        ok = modals_surface.open_bind_thread_modal(trigger_id=trigger_id, channel_id=channel_id, thread_ts=th)
        return {"response_type": "ephemeral", "text": "Opening…" if ok else "Failed to open modal."}

    if cb in ("polaris_assign_task", "assign_task"):
        if not channel_id or not th or not trigger_id:
            return {"response_type": "ephemeral", "text": "Missing channel/thread context."}
        rid = None
        try:
            b = get_thread_binding(channel_id=channel_id, thread_ts=th) or {}
            rid = str((b or {}).get("rfpId") or "").strip() or None
        except Exception:
            rid = None
        if not rid:
            rid = _extract_rfp_id(_message_text_from_payload(payload))
        if not rid:
            return {"response_type": "ephemeral", "text": "Bind this thread first: `@polaris link rfp_...`"}
        ok = modals_surface.open_assign_task_modal(trigger_id=trigger_id, channel_id=channel_id, thread_ts=th, rfp_id=rid)
        return {"response_type": "ephemeral", "text": "Opening…" if ok else "Failed to open modal."}

    if cb in ("polaris_bid_decision", "bid_decision"):
        if not channel_id or not th or not trigger_id:
            return {"response_type": "ephemeral", "text": "Missing channel/thread context."}
        rid = None
        try:
            b = get_thread_binding(channel_id=channel_id, thread_ts=th) or {}
            rid = str((b or {}).get("rfpId") or "").strip() or None
        except Exception:
            rid = None
        if not rid:
            rid = _extract_rfp_id(_message_text_from_payload(payload))
        if not rid:
            return {"response_type": "ephemeral", "text": "Bind this thread first: `@polaris link rfp_...`"}
        ok = modals_surface.open_bid_decision_modal(trigger_id=trigger_id, channel_id=channel_id, thread_ts=th, rfp_id=rid)
        return {"response_type": "ephemeral", "text": "Opening…" if ok else "Failed to open modal."}

    # Create RFP from a PDF attached to the message.
    if cb in ("polaris_create_rfp_from_message", "create_rfp_from_message"):
        f = _first_pdf_file(payload)
        if not f:
            return {"response_type": "ephemeral", "text": "No PDF found on that message. Attach a PDF, then try again."}
        url = (
            str(f.get("url_private_download") or "").strip()
            or str(f.get("url_private") or "").strip()
        )
        name = str(f.get("name") or "upload.pdf").strip() or "upload.pdf"
        if not url:
            return {"response_type": "ephemeral", "text": "That PDF is missing a downloadable URL (Slack file metadata incomplete)."}
        try:
            pdf = download_slack_file(url=url, max_bytes=60 * 1024 * 1024)
            analysis = analyze_rfp(pdf, name)
            saved = create_rfp_from_analysis(analysis=analysis, source_file_name=name, source_file_size=len(pdf))
            rid = str(saved.get("_id") or saved.get("rfpId") or "").strip()
            if channel_id and th and rid:
                chat_post_message_result(
                    text=f"Created RFP: <{_rfp_url(rid)}|`{rid}`>",
                    channel=channel_id,
                    thread_ts=th,
                    unfurl_links=False,
                )
            return {"response_type": "ephemeral", "text": f"Created `{rid}` (see thread)."}
        except Exception as e:
            err_msg = str(e) or "create_failed"
            if len(err_msg) > 180:
                err_msg = err_msg[:180] + "…"
            return {"response_type": "ephemeral", "text": f"Failed to create RFP: {err_msg}"}

    # Create tasks from message: bind to an RFP (via thread binding or explicit rfp_...) and propose seeding tasks.
    if cb in ("polaris_create_tasks_from_message", "create_tasks_from_message"):
        rid = _extract_rfp_id(_message_text_from_payload(payload))
        if not rid and channel_id and th:
            try:
                b = get_thread_binding(channel_id=channel_id, thread_ts=th) or {}
                rid = str((b or {}).get("rfpId") or "").strip() or None
            except Exception:
                rid = None
        if not rid:
            return {"response_type": "ephemeral", "text": "No RFP id found. Include `rfp_...` in the message or bind the thread with `@polaris link rfp_...`."}

        saved = create_action(
            kind="seed_tasks_for_rfp",
            payload={
                "action": "seed_tasks_for_rfp",
                "args": {"rfpId": rid},
                "summary": f"Seed missing tasks for `{rid}`",
                "requestedBySlackUserId": user_id,
                "channelId": channel_id,
                "threadTs": th,
                "question": f"seed tasks for {rid}",
            },
            ttl_seconds=900,
        )
        aid = str(saved.get("actionId") or "").strip()
        if channel_id and th:
            chat_post_message_result(
                text=f"Proposed: seed tasks for `{rid}`",
                channel=channel_id,
                thread_ts=th,
                blocks=_blocks_for_proposed_action(action_id=aid, summary=f"Seed missing tasks for `{rid}`"),
                unfurl_links=False,
            )
        return {"response_type": "ephemeral", "text": "Posted task seeding proposal in thread."}

    return {"response_type": "ephemeral", "text": "Shortcut received. (Not implemented yet.)"}

