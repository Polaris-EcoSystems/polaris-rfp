from __future__ import annotations

from typing import Any

from .....observability.logging import get_logger
from .....settings import settings
from ..slack_actor_context import resolve_actor_context
from ..slack_web import slack_api_post
from .....repositories.rfp.rfps_repo import get_rfp_by_id, list_rfps
from .....repositories.workflows.tasks_repo import list_tasks_for_rfp

log = get_logger("slack_home")


def _rfp_url(rfp_id: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    rid = str(rfp_id or "").strip()
    return f"{base}/rfps/{rid}"


def _safe_list(value: Any, *, max_items: int = 20) -> list[Any]:
    xs = value if isinstance(value, list) else []
    return list(xs)[:max_items]


def _home_view(*, user_id: str) -> dict[str, Any]:
    """
    Minimal Home tab view v1.
    We'll expand this once we have pinned RFPs, tasks, and per-user prefs wired.
    """
    uid = str(user_id or "").strip()
    header = "North Star RFP"

    ctx = resolve_actor_context(slack_user_id=uid, slack_team_id=None, slack_enterprise_id=None)
    prof: dict[str, Any] = ctx.user_profile if isinstance(ctx.user_profile, dict) else {}
    prefs_raw = prof.get("aiPreferences")
    prefs: dict[str, Any] = prefs_raw if isinstance(prefs_raw, dict) else {}
    pinned_ids = [
        str(x).strip()
        for x in _safe_list(prefs.get("pinnedRfpIds"), max_items=12)
        if str(x).strip()
    ]
    action_policy = str(prefs.get("actionPolicy") or "confirm_risky").strip()

    # Recent RFPs
    recent = list_rfps(page=1, limit=8).get("data") or []
    recent_ids = [str(r.get("_id") or "").strip() for r in recent if isinstance(r, dict) and str(r.get("_id") or "").strip()]
    recent_ids = recent_ids[:6]

    # My open tasks (best-effort: filter tasks for pinned + a few recent RFPs)
    my_sub = str(prof.get("_id") or prof.get("userSub") or "").strip() or None
    candidate_rfps = pinned_ids + [x for x in recent_ids if x not in pinned_ids]
    candidate_rfps = candidate_rfps[:8]
    tasks_lines: list[str] = []
    if my_sub and candidate_rfps:
        count = 0
        for rid in candidate_rfps:
            data = list_tasks_for_rfp(rfp_id=rid, limit=200, next_token=None).get("data") or []
            for t in data:
                if not isinstance(t, dict):
                    continue
                if str(t.get("status") or "").strip().lower() != "open":
                    continue
                if str(t.get("assigneeUserSub") or "").strip() != my_sub:
                    continue
                title = str(t.get("title") or "Task").strip()
                due = str(t.get("dueAt") or "").strip()
                suffix = f" (due {due})" if due else ""
                tasks_lines.append(f"- {title}{suffix} — <{_rfp_url(rid)}|`{rid}`>")
                count += 1
                if count >= 8:
                    break
            if count >= 8:
                break
    if not tasks_lines:
        tasks_lines = ["- No open assigned tasks found (or not linked yet)."]

    pinned_lines: list[str] = []
    for rid in pinned_ids[:8]:
        r = get_rfp_by_id(rid) or {}
        title = str((r or {}).get("title") or "RFP").strip()
        pinned_lines.append(f"- <{_rfp_url(rid)}|{title}> `{rid}`")
    if not pinned_lines:
        pinned_lines = ["- None yet. Pin an RFP from the web app profile (or we’ll add Slack pin actions next)."]

    recent_lines: list[str] = []
    for r in recent[:6]:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("_id") or "").strip()
        if not rid:
            continue
        title = str(r.get("title") or "RFP").strip()
        recent_lines.append(f"- <{_rfp_url(rid)}|{title}> `{rid}`")
    if not recent_lines:
        recent_lines = ["- No RFPs found."]

    return {
        "type": "home",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": header}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(
                        [
                            f"*Hi{(' ' + ctx.display_name) if ctx.display_name else ''}*",
                            "",
                            "*Quick actions*",
                            "- Mention me in a thread to work in-context",
                            "- Use `/polaris recent` to list recent RFPs",
                            "- Use the message shortcut: *Summarize*",
                        ]
                    ),
                },
            },
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*My open tasks*\n" + "\n".join(tasks_lines)}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Pinned RFPs*\n" + "\n".join(pinned_lines)}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Recent RFPs*\n" + "\n".join(recent_lines)}},
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(
                        [
                            "*Settings*",
                            f"- Action policy: `{action_policy}` (default: auto low-risk, confirm risky)",
                        ]
                    ),
                },
            },
        ],
    }


def on_app_home_opened(*, payload: dict[str, Any]) -> None:
    """
    Event handler for app_home_opened.
    Publishes a Home tab view via views.publish.
    """
    try:
        ev = payload.get("event")
        ev = ev if isinstance(ev, dict) else {}
        user_id = str(ev.get("user") or "").strip()
        if not user_id:
            return
        view = _home_view(user_id=user_id)
        slack_api_post(method="views.publish", json={"user_id": user_id, "view": view})
    except Exception:
        return

