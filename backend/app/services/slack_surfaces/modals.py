from __future__ import annotations

import json
from typing import Any

from ...observability.logging import get_logger
from ..slack_actor_context import resolve_actor_context
from ..slack_actions_repo import create_action
from ..slack_agent import _blocks_for_proposed_action
from ..slack_thread_bindings_repo import set_binding
from ..slack_web import chat_post_message_result, slack_api_post
from ..workflow_tasks_repo import list_tasks_for_rfp

log = get_logger("slack_modals")

_BIND_VIEW = "polaris_bind_thread_view"
_ASSIGN_VIEW = "polaris_assign_task_view"
_BID_VIEW = "polaris_bid_decision_view"
_ASSIGN_REVIEW_VIEW = "polaris_assign_review_view"


def _open_modal(*, trigger_id: str, view: dict[str, Any]) -> bool:
    tid = str(trigger_id or "").strip()
    if not tid:
        return False
    resp = slack_api_post(method="views.open", json={"trigger_id": tid, "view": view})
    return bool(resp.get("ok"))


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def open_bind_thread_modal(*, trigger_id: str, channel_id: str, thread_ts: str) -> bool:
    view = {
        "type": "modal",
        "callback_id": _BIND_VIEW,
        "title": {"type": "plain_text", "text": "Bind thread"},
        "submit": {"type": "plain_text", "text": "Bind"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": json.dumps({"channelId": channel_id, "threadTs": thread_ts}),
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": "Bind this thread to an RFP id (`rfp_...`)."}},
            {
                "type": "input",
                "block_id": "rfp_block",
                "label": {"type": "plain_text", "text": "RFP id"},
                "element": {"type": "plain_text_input", "action_id": "rfp_id"},
            },
        ],
    }
    return _open_modal(trigger_id=trigger_id, view=view)


def open_assign_task_modal(*, trigger_id: str, channel_id: str, thread_ts: str, rfp_id: str) -> bool:
    tasks = list_tasks_for_rfp(rfp_id=rfp_id, limit=200, next_token=None).get("data") or []
    options: list[dict[str, Any]] = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        if str(t.get("status") or "").strip().lower() != "open":
            continue
        tid = str(t.get("_id") or t.get("taskId") or "").strip()
        title = str(t.get("title") or "Task").strip()[:70]
        if tid:
            options.append({"text": {"type": "plain_text", "text": title or tid}, "value": tid})
        if len(options) >= 20:
            break

    view = {
        "type": "modal",
        "callback_id": _ASSIGN_VIEW,
        "title": {"type": "plain_text", "text": "Assign task"},
        "submit": {"type": "plain_text", "text": "Propose"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": json.dumps({"channelId": channel_id, "threadTs": thread_ts, "rfpId": rfp_id}),
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*RFP:* `{rfp_id}`"}},
            {
                "type": "input",
                "block_id": "task_block",
                "label": {"type": "plain_text", "text": "Task"},
                "element": {"type": "static_select", "action_id": "task_id", "options": options or [{"text": {"type": "plain_text", "text": "No open tasks found"}, "value": "none"}]},
            },
            {
                "type": "input",
                "block_id": "assignee_block",
                "label": {"type": "plain_text", "text": "Assign to"},
                "element": {"type": "users_select", "action_id": "assignee_slack_user"},
            },
        ],
    }
    return _open_modal(trigger_id=trigger_id, view=view)


def open_assign_review_modal(*, trigger_id: str, channel_id: str, thread_ts: str, rfp_id: str) -> bool:
    """Open modal to assign bid/no-bid review to a user."""
    from ...repositories.rfp.rfps_repo import get_rfp_by_id
    
    rfp = get_rfp_by_id(rfp_id) or {}
    review_raw = rfp.get("review")
    review: dict[str, Any] = review_raw if isinstance(review_raw, dict) else {}
    current_assignee = str(review.get("assignedReviewerUserSub") or "").strip()
    
    assignee_text = f"Currently assigned to: `{current_assignee}`" if current_assignee else "No reviewer assigned"
    
    view = {
        "type": "modal",
        "callback_id": _ASSIGN_REVIEW_VIEW,
        "title": {"type": "plain_text", "text": "Assign review"},
        "submit": {"type": "plain_text", "text": "Propose"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": json.dumps({"channelId": channel_id, "threadTs": thread_ts, "rfpId": rfp_id}),
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*RFP:* `{rfp_id}`"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": assignee_text}},
            {
                "type": "input",
                "block_id": "assignee_block",
                "label": {"type": "plain_text", "text": "Assign to"},
                "element": {"type": "users_select", "action_id": "assignee_slack_user"},
            },
        ],
    }
    return _open_modal(trigger_id=trigger_id, view=view)


def open_bid_decision_modal(*, trigger_id: str, channel_id: str, thread_ts: str, rfp_id: str) -> bool:
    """Open modal for bid/no-bid decision, showing current assignee if any."""
    from ...repositories.rfp.rfps_repo import get_rfp_by_id
    
    rfp = get_rfp_by_id(rfp_id) or {}
    review_raw = rfp.get("review")
    review: dict[str, Any] = review_raw if isinstance(review_raw, dict) else {}
    current_assignee = str(review.get("assignedReviewerUserSub") or "").strip()
    current_decision = str(review.get("decision") or "").strip()
    
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*RFP:* `{rfp_id}`"}},
    ]
    
    if current_assignee:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Assigned reviewer:* `{current_assignee}`"},
        })
    
    notes_value: str | None = None
    if review.get("notes"):
        notes_value = str(review.get("notes") or "").strip()
    
    blocks.extend([
        {
            "type": "input",
            "block_id": "decision_block",
            "label": {"type": "plain_text", "text": "Decision"},
            "element": {
                "type": "static_select",
                "action_id": "decision",
                "initial_option": {"text": {"type": "plain_text", "text": current_decision.title() if current_decision else "Unreviewed"}, "value": current_decision or "unreviewed"} if current_decision else None,
                "options": [
                    {"text": {"type": "plain_text", "text": "Bid"}, "value": "bid"},
                    {"text": {"type": "plain_text", "text": "No bid"}, "value": "no_bid"},
                    {"text": {"type": "plain_text", "text": "Unreviewed"}, "value": "unreviewed"},
                ],
            },
        },
        {
            "type": "input",
            "optional": True,
            "block_id": "notes_block",
            "label": {"type": "plain_text", "text": "Notes"},
            "element": {
                "type": "plain_text_input",
                "action_id": "notes",
                "multiline": True,
                "initial_value": notes_value,
            },
        },
    ])
    
    view = {
        "type": "modal",
        "callback_id": _BID_VIEW,
        "title": {"type": "plain_text", "text": "Bid decision"},
        "submit": {"type": "plain_text", "text": "Propose"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": json.dumps({"channelId": channel_id, "threadTs": thread_ts, "rfpId": rfp_id}),
        "blocks": blocks,
    }
    return _open_modal(trigger_id=trigger_id, view=view)


def handle_block_actions(*, payload: dict[str, Any], background_tasks: Any) -> dict[str, Any]:
    """
    Handle Block Kit interactions (buttons/selects).

    v1: handle new modal-launch actions; legacy action ids remain in the router.
    """
    actions_raw = payload.get("actions")
    actions: list[Any] = actions_raw if isinstance(actions_raw, list) else []
    act = actions[0] if actions else {}
    action_id = str(act.get("action_id") or "").strip()
    trigger_id = str(payload.get("trigger_id") or "").strip()
    channel = _as_dict(payload.get("channel"))
    message = _as_dict(payload.get("message"))
    channel_id = str(channel.get("id") or "").strip()
    msg_ts = str(message.get("ts") or "").strip()
    thread_ts = str(message.get("thread_ts") or "").strip() or msg_ts

    if action_id == "polaris_open_bind_thread_modal":
        ok = open_bind_thread_modal(trigger_id=trigger_id, channel_id=channel_id, thread_ts=thread_ts)
        return {"response_type": "ephemeral", "text": "Opening…" if ok else "Failed to open modal."}

    return {"response_type": "ephemeral", "text": "Working…"}


def handle_view(*, payload: dict[str, Any], background_tasks: Any) -> dict[str, Any]:
    """
    Handle modal submissions and closes.

    v1: no modals are wired yet; acknowledge.
    """
    ptype = str(payload.get("type") or "").strip()
    view = _as_dict(payload.get("view"))
    cb = str(view.get("callback_id") or "").strip()
    meta_raw = str(view.get("private_metadata") or "").strip()
    try:
        meta = json.loads(meta_raw) if meta_raw else {}
    except Exception:
        meta = {}

    if ptype != "view_submission":
        return {}

    user = _as_dict(payload.get("user"))
    actor_slack_id = str(user.get("id") or "").strip() or None
    actor_ctx = resolve_actor_context(slack_user_id=actor_slack_id, slack_team_id=None, slack_enterprise_id=None)

    state = _as_dict(view.get("state"))
    values = _as_dict(state.get("values"))

    def _v(block_id: str, action_id: str) -> dict[str, Any]:
        b = _as_dict(values.get(block_id))
        return _as_dict(b.get(action_id))

    if cb == _BIND_VIEW:
        rfp_id = str(_v("rfp_block", "rfp_id").get("value") or "").strip()
        ch = str(meta.get("channelId") or "").strip()
        th = str(meta.get("threadTs") or "").strip()
        if not rfp_id.startswith("rfp_"):
            return {"response_action": "errors", "errors": {"rfp_block": "Enter an id like rfp_..."}}  # keep modal open
        if not ch or not th:
            return {"response_action": "errors", "errors": {"rfp_block": "Missing Slack thread context."}}
        set_binding(channel_id=ch, thread_ts=th, rfp_id=rfp_id, bound_by_slack_user_id=actor_slack_id)
        chat_post_message_result(
            text=f"Bound this thread to `{rfp_id}`.",
            channel=ch,
            thread_ts=th,
            unfurl_links=False,
        )
        return {}

    if cb == _ASSIGN_VIEW:
        task_id = str(_v("task_block", "task_id").get("selected_option", {}).get("value") or "").strip()
        assignee_slack = str(_v("assignee_block", "assignee_slack_user").get("selected_user") or "").strip()
        ch = str(meta.get("channelId") or "").strip()
        th = str(meta.get("threadTs") or "").strip()
        rid = str(meta.get("rfpId") or "").strip()
        if not task_id or task_id == "none":
            return {"response_action": "errors", "errors": {"task_block": "No task selected."}}
        if not assignee_slack:
            return {"response_action": "errors", "errors": {"assignee_block": "Pick an assignee."}}
        assignee_ctx = resolve_actor_context(slack_user_id=assignee_slack, slack_team_id=None, slack_enterprise_id=None)
        if not assignee_ctx.user_sub:
            return {"response_action": "errors", "errors": {"assignee_block": "Assignee is not recognized in Polaris yet."}}

        saved = create_action(
            kind="assign_task",
            payload={
                "action": "assign_task",
                "args": {"taskId": task_id, "assigneeUserSub": assignee_ctx.user_sub},
                "summary": f"Assign `{task_id}` to `{assignee_ctx.user_sub}`",
                "requestedBySlackUserId": actor_slack_id,
                "requestedByUserSub": actor_ctx.user_sub,
                "channelId": ch,
                "threadTs": th,
                "question": f"assign task {task_id}",
                "rfpId": rid or None,
            },
            ttl_seconds=900,
        )
        aid = str(saved.get("actionId") or "").strip()
        if ch and th:
            chat_post_message_result(
                text=f"Proposed: assign `{task_id}`",
                channel=ch,
                thread_ts=th,
                blocks=_blocks_for_proposed_action(action_id=aid, summary=str(saved.get('payload', {}).get('summary') or 'Assign task') if isinstance(saved.get('payload'), dict) else 'Assign task'),
                unfurl_links=False,
            )
        return {}

    if cb == _BID_VIEW:
        decision = str(_v("decision_block", "decision").get("selected_option", {}).get("value") or "").strip()
        notes = str(_v("notes_block", "notes").get("value") or "").strip() or None
        ch = str(meta.get("channelId") or "").strip()
        th = str(meta.get("threadTs") or "").strip()
        rid = str(meta.get("rfpId") or "").strip()
        if not rid:
            return {"response_action": "errors", "errors": {"decision_block": "Missing RFP context."}}
        if decision not in ("bid", "no_bid", "unreviewed"):
            return {"response_action": "errors", "errors": {"decision_block": "Pick a valid decision."}}

        saved = create_action(
            kind="update_rfp_review",
            payload={
                "action": "update_rfp_review",
                "args": {"rfpId": rid, "decision": decision, "notes": notes},
                "summary": f"Set bid decision for `{rid}` to `{decision}`",
                "requestedBySlackUserId": actor_slack_id,
                "requestedByUserSub": actor_ctx.user_sub,
                "channelId": ch,
                "threadTs": th,
                "question": f"set bid decision {decision} for {rid}",
                "rfpId": rid,
            },
            ttl_seconds=900,
        )
        aid = str(saved.get("actionId") or "").strip()
        if ch and th:
            chat_post_message_result(
                text=f"Proposed: update bid decision for `{rid}`",
                channel=ch,
                thread_ts=th,
                blocks=_blocks_for_proposed_action(action_id=aid, summary=f"Set bid decision for `{rid}` to `{decision}`"),
                unfurl_links=False,
            )
        return {}

    if cb == _ASSIGN_REVIEW_VIEW:
        assignee_slack = str(_v("assignee_block", "assignee_slack_user").get("selected_user") or "").strip()
        ch = str(meta.get("channelId") or "").strip()
        th = str(meta.get("threadTs") or "").strip()
        rid = str(meta.get("rfpId") or "").strip()
        if not rid:
            return {"response_action": "errors", "errors": {"assignee_block": "Missing RFP context."}}
        if not assignee_slack:
            return {"response_action": "errors", "errors": {"assignee_block": "Pick a reviewer."}}
        assignee_ctx = resolve_actor_context(slack_user_id=assignee_slack, slack_team_id=None, slack_enterprise_id=None)
        if not assignee_ctx.user_sub:
            return {"response_action": "errors", "errors": {"assignee_block": "Reviewer is not recognized in Polaris yet."}}

        saved = create_action(
            kind="assign_rfp_review",
            payload={
                "action": "assign_rfp_review",
                "args": {"rfpId": rid, "assigneeUserSub": assignee_ctx.user_sub},
                "summary": f"Assign bid/no-bid review for `{rid}` to `{assignee_ctx.user_sub}`",
                "requestedBySlackUserId": actor_slack_id,
                "requestedByUserSub": actor_ctx.user_sub,
                "channelId": ch,
                "threadTs": th,
                "question": f"assign review for {rid}",
                "rfpId": rid,
            },
            ttl_seconds=900,
        )
        aid = str(saved.get("actionId") or "").strip()
        if ch and th:
            chat_post_message_result(
                text=f"Proposed: assign review for `{rid}` to `{assignee_ctx.user_sub}`",
                channel=ch,
                thread_ts=th,
                blocks=_blocks_for_proposed_action(action_id=aid, summary=f"Assign bid/no-bid review for `{rid}` to `{assignee_ctx.user_sub}`"),
                unfurl_links=False,
            )
        return {}

    return {}

