from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..ai.client import AiNotConfigured, AiUpstreamError
from ..ai.user_context import load_user_profile_from_request
from ..domain.agents.telemetry.agent_diagnostics import build_agent_diagnostics
from ..infrastructure.integrations.slack.slack_action_executor import execute_action
from ..repositories.slack.actions_repo import create_action, get_action, mark_action_done
from ..domain.agents.slack_agent import run_slack_agent_question
from ..settings import settings


router = APIRouter(tags=["ai-agent"])


def _require_user_sub(request: Request) -> str:
    user = getattr(getattr(request, "state", None), "user", None)
    sub = str(getattr(user, "sub", "") or "").strip() if user else ""
    if not sub:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return sub


@router.post("/ask")
def ask(body: dict, request: Request):
    """
    Conversational agent endpoint (shared tool registry with Slack).
    """
    q = str((body or {}).get("question") or (body or {}).get("q") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required")

    # Best-effort user profile + Slack id enrichment (for memory + action gating parity).
    user_profile = load_user_profile_from_request(request)
    slack_user_id = str((user_profile or {}).get("slackUserId") or "").strip() or None
    email = str((user_profile or {}).get("email") or "").strip().lower() or None
    display_name = str((user_profile or {}).get("preferredName") or (user_profile or {}).get("fullName") or "").strip() or None

    try:
        ans = run_slack_agent_question(
            question=q,
            user_id=slack_user_id,
            user_display_name=display_name,
            user_email=email,
            user_profile=user_profile,
            channel_id=None,
            thread_ts=None,
        )
        return {"ok": True, "text": ans.text, "blocks": ans.blocks, "meta": ans.meta}
    except AiNotConfigured:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")
    except AiUpstreamError as e:
        code = 503 if str(e) == "ai_temporarily_unavailable" else 502
        raise HTTPException(status_code=code, detail={"error": "AI upstream failure", "details": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "agent_failed", "details": str(e)})


@router.post("/propose")
def propose(body: dict, request: Request):
    """
    Create an approval-gated action without Slack.
    This is useful for internal UIs that want a review step.
    """
    sub = _require_user_sub(request)
    if not bool(settings.slack_agent_actions_enabled):
        raise HTTPException(status_code=400, detail="Actions are disabled")

    kind = str((body or {}).get("kind") or (body or {}).get("action") or "").strip()
    args = (body or {}).get("args")
    summary = str((body or {}).get("summary") or "").strip()
    ttl = int((body or {}).get("ttlSeconds") or 900)

    if not kind:
        raise HTTPException(status_code=400, detail="kind is required")
    if not isinstance(args, dict):
        args = {}

    saved = create_action(
        kind=kind,
        payload={
            "action": kind,
            "args": args,
            "summary": summary,
            "requestedByUserSub": sub,
        },
        ttl_seconds=max(60, min(3600, ttl)),
    )
    return {"ok": True, "action": saved}


@router.post("/confirm")
def confirm(body: dict, request: Request):
    """
    Confirm and execute a previously proposed action (approval-gated).
    """
    sub = _require_user_sub(request)
    if not bool(settings.slack_agent_actions_enabled):
        raise HTTPException(status_code=400, detail="Actions are disabled")

    aid = str((body or {}).get("actionId") or (body or {}).get("id") or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="actionId is required")

    stored = get_action(aid)
    if not stored:
        raise HTTPException(status_code=404, detail="Action expired or not found")

    kind = str(stored.get("kind") or "").strip()
    payload = stored.get("payload") if isinstance(stored.get("payload"), dict) else {}
    args2 = payload.get("args") if isinstance(payload, dict) else {}
    args2 = args2 if isinstance(args2, dict) else {}

    # Authorization: if action was proposed via internal API, bind it to the proposing user.
    req_sub = str(payload.get("requestedByUserSub") or "").strip() if isinstance(payload, dict) else ""
    if req_sub and req_sub != sub:
        raise HTTPException(status_code=403, detail="Not authorized for this action")

    # Inject actor identifiers.
    args2["_actorUserSub"] = sub
    user_profile = load_user_profile_from_request(request) or {}
    slack_user_id = str(user_profile.get("slackUserId") or "").strip()
    if slack_user_id:
        args2["_actorSlackUserId"] = slack_user_id

    try:
        result = execute_action(action_id=aid, kind=kind, args=args2)
    except Exception as e:
        result = {"ok": False, "error": str(e) or "execution_failed"}

    try:
        mark_action_done(action_id=aid, status="done" if result.get("ok") else "failed", result=result)
    except Exception:
        pass

    return {"ok": True, "actionId": aid, "kind": kind, "result": result}


@router.post("/cancel")
def cancel(body: dict, request: Request):
    sub = _require_user_sub(request)
    aid = str((body or {}).get("actionId") or (body or {}).get("id") or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="actionId is required")

    stored = get_action(aid)
    if not stored:
        return {"ok": True, "cancelled": True}

    payload = stored.get("payload") if isinstance(stored.get("payload"), dict) else {}
    req_sub = str(payload.get("requestedByUserSub") or "").strip() if isinstance(payload, dict) else ""
    if req_sub and req_sub != sub:
        raise HTTPException(status_code=403, detail="Not authorized for this action")

    try:
        mark_action_done(action_id=aid, status="cancelled", result={"ok": True})
    except Exception:
        pass
    return {"ok": True, "cancelled": True}


@router.get("/diagnostics")
def get_diagnostics(
    hours: int = 24,
    user_sub: str | None = None,
    rfp_id: str | None = None,
    channel_id: str | None = None,
    use_cache: bool = True,
    force_refresh: bool = False,
):
    """
    Get agent diagnostics including metrics and recent activities.
    
    Enhanced with contextual filtering and caching.
    
    Args:
        hours: Number of hours to look back (default 24, max 168)
        user_sub: Optional user filter for activities
        rfp_id: Optional RFP filter for activities
        channel_id: Optional Slack channel filter
        use_cache: Whether to use cached results (default True)
        force_refresh: Force refresh even if cache is valid (default False)
    
    Returns:
        Dict with metrics, activities, and summary
    """
    try:
        diagnostics = build_agent_diagnostics(
            hours=hours,
            user_sub=user_sub,
            rfp_id=rfp_id,
            channel_id=channel_id,
            use_cache=use_cache,
            force_refresh=force_refresh,
        )
        return diagnostics
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "diagnostics_failed", "details": str(e)})

