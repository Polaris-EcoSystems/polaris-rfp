from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger
from ..services.agent_events_repo import append_event
from ..services.slack_events_repo import mark_seen
from ..services.slack_web import chat_post_message_result, slack_api_post

log = get_logger("slack_workflows")


def on_dm_message(*, payload: dict[str, Any]) -> None:
    """
    DM concierge handler (message events where channel_type == im).
    Kept intentionally minimal for v1; we'll evolve this into a real concierge.
    """
    # TODO: implement DM concierge in a later todo item.
    return


def handle_workflow_step_execute(*, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Handle Slack Workflow Builder 'Steps from Apps' executions.

    Expected payload type: workflow_step_execute (sent to a configured request URL).
    """
    # Best-effort dedupe: Slack includes workflow_step_execute_id.
    wseid = str(payload.get("workflow_step_execute_id") or "").strip()
    if wseid:
        if not mark_seen(event_id=f"wf:{wseid}", ttl_seconds=600):
            return {"ok": True}

    step = payload.get("workflow_step") if isinstance(payload.get("workflow_step"), dict) else {}
    inputs = step.get("inputs") if isinstance(step.get("inputs"), dict) else {}

    def _input(name: str) -> str:
        raw = inputs.get(name) if isinstance(inputs.get(name), dict) else {}
        return str(raw.get("value") or "").strip()

    channel = _input("channel")
    message = _input("message")
    thread_ts = _input("thread_ts") or None

    ok = False
    err: str | None = None
    try:
        if channel and message:
            res = chat_post_message_result(text=message, channel=channel, thread_ts=thread_ts, unfurl_links=False)
            ok = bool(res.get("ok"))
            if not ok:
                err = str(res.get("error") or "slack_rejected")
        else:
            err = "missing_inputs"
    except Exception as e:
        err = str(e) or "post_failed"

    # Notify Slack workflow engine of completion.
    try:
        if ok:
            slack_api_post(method="workflows.stepCompleted", json={"workflow_step_execute_id": wseid, "outputs": {}})
        else:
            slack_api_post(method="workflows.stepFailed", json={"workflow_step_execute_id": wseid, "error": {"message": err or "failed"}})
    except Exception:
        pass

    try:
        append_event(
            rfp_id="rfp_slack_agent",
            type="workflow_step_execute",
            tool="workflows.stepCompleted" if ok else "workflows.stepFailed",
            payload={"ok": bool(ok), "error": err},
            inputs_redacted={"inputsKeys": list(inputs.keys())[:40]},
            created_by="slack_workflows",
        )
    except Exception:
        pass

    return {"ok": True}

