from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from ..services.agent_events_repo import list_recent_events, list_recent_events_global
from ..repositories.rfp.agent_journal_repo import list_recent_entries
from ..services.agent_jobs_repo import claim_due_jobs
from ..services.change_proposals_repo import list_recent_change_proposals
from ..repositories.rfp.opportunity_state_repo import ensure_state_exists, get_state
from ..services.slack_thread_bindings_repo import get_binding as get_thread_binding


router = APIRouter(tags=["northstar"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/northstar/audit/opportunity/{rfp_id}")
def audit_opportunity(rfp_id: str, journal_limit: int = 20, events_limit: int = 30) -> dict[str, Any]:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="missing_rfp_id")
    ensure_state_exists(rfp_id=rid)
    return {
        "ok": True,
        "rfpId": rid,
        "opportunity": get_state(rfp_id=rid),
        "journal": list_recent_entries(rfp_id=rid, limit=max(1, min(50, int(journal_limit or 20)))),
        "events": list_recent_events(rfp_id=rid, limit=max(1, min(100, int(events_limit or 30)))),
    }


@router.get("/northstar/audit/thread-binding")
def audit_thread_binding(channel_id: str, thread_ts: str) -> dict[str, Any]:
    ch = str(channel_id or "").strip()
    th = str(thread_ts or "").strip()
    if not ch or not th:
        raise HTTPException(status_code=400, detail="missing_channel_or_thread")
    b = get_thread_binding(channel_id=ch, thread_ts=th)
    return {"ok": True, "binding": b}


@router.get("/northstar/audit/events/recent")
def audit_recent_events(hours: int = 24, limit: int = 200) -> dict[str, Any]:
    h = max(1, min(72, int(hours or 24)))
    lim = max(1, min(500, int(limit or 200)))
    since = datetime.now(timezone.utc) - timedelta(hours=h)
    since_iso = since.isoformat().replace("+00:00", "Z")
    evs = list_recent_events_global(since_iso=since_iso, limit=lim)
    return {"ok": True, "since": since_iso, "count": len(evs), "data": evs}


@router.get("/northstar/audit/change-proposals/recent")
def audit_recent_change_proposals(limit: int = 50) -> dict[str, Any]:
    lim = max(1, min(200, int(limit or 50)))
    return {"ok": True, **list_recent_change_proposals(limit=lim)}


@router.get("/northstar/audit/jobs/due")
def audit_due_jobs(limit: int = 25) -> dict[str, Any]:
    lim = max(1, min(100, int(limit or 25)))
    now = _now_iso()
    jobs = claim_due_jobs(now_iso=now, limit=lim)
    return {"ok": True, "now": now, "count": len(jobs), "data": jobs}

