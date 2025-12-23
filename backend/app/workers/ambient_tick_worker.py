from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..observability.logging import configure_logging, get_logger
from ..repositories.rfp.opportunity_state_repo import ensure_state_exists, patch_state, seed_from_platform
from ..repositories.rfp.proposals_repo import list_proposals
from ..repositories.rfp.rfps_repo import list_rfps
from ..repositories.workflows.tasks_repo import compute_pipeline_stage


log = get_logger("ambient_tick")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _days_until_submission(rfp: dict[str, Any]) -> int | None:
    try:
        dm = rfp.get("dateMeta")
        dates = (dm or {}).get("dates") if isinstance(dm, dict) else None
        sub = (dates or {}).get("submissionDeadline") if isinstance(dates, dict) else None
        du = sub.get("daysUntil") if isinstance(sub, dict) else None
        return int(du) if du is not None else None
    except Exception:
        return None


def run_once(*, limit: int = 200) -> dict[str, Any]:
    """
    Periodic “perch time” tick for quiet pipeline maintenance.

    Principles:
    - default to silence (no Slack messages)
    - update durable artifacts so next interactive invocation is better
    """
    started_at = _now_iso()
    lim = max(1, min(500, int(limit or 200)))

    rfps = (list_rfps(page=1, limit=lim, next_token=None).get("data") or [])[:lim]
    props = (list_proposals(page=1, limit=lim, next_token=None).get("data") or [])[:lim]
    by_rfp: dict[str, list[dict[str, Any]]] = {}
    for p in props:
        if not isinstance(p, dict):
            continue
        rid = str(p.get("rfpId") or "").strip()
        if not rid:
            continue
        by_rfp.setdefault(rid, []).append(p)

    touched = 0
    for r in rfps:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("_id") or r.get("rfpId") or "").strip()
        if not rid:
            continue

        proposals_for_rfp = by_rfp.get(rid, [])
        try:
            stage = compute_pipeline_stage(rfp=r, proposals_for_rfp=proposals_for_rfp)
        except Exception:
            stage = None

        # Ensure canonical state exists and keep it in sync (best-effort).
        try:
            ensure_state_exists(rfp_id=rid)
            seed = seed_from_platform(rfp_id=rid)

            du = _days_until_submission(r)
            nba: list[dict[str, Any]] = []
            if isinstance(du, int):
                if du <= 0:
                    nba.append({"type": "deadline", "priority": "high", "text": "Submission deadline is today/overdue."})
                elif du <= 3:
                    nba.append({"type": "deadline", "priority": "high", "text": f"Submission deadline in {du} day(s)."})
                elif du <= 7:
                    nba.append({"type": "deadline", "priority": "med", "text": f"Submission deadline in {du} day(s)."})

            if stage:
                nba.append({"type": "stage", "priority": "low", "text": f"Current stage: {stage}"})

            patch_state(
                rfp_id=rid,
                patch={
                    "stage": str(stage) if stage else seed.get("stage"),
                    "dueDates": seed.get("dueDates") if isinstance(seed.get("dueDates"), dict) else {},
                    "proposalIds": seed.get("proposalIds") if isinstance(seed.get("proposalIds"), list) else [],
                    "contractingCaseId": seed.get("contractingCaseId"),
                    "nextBestActions": nba,
                },
                updated_by_user_sub=None,
                create_snapshot=False,
            )
            touched += 1
        except Exception:
            # Best-effort: never crash the tick.
            continue

    finished_at = _now_iso()
    out = {"ok": True, "startedAt": started_at, "finishedAt": finished_at, "rfpsScanned": len(rfps), "touched": touched}
    try:
        log.info("ambient_tick_done", **out)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    configure_logging(level="INFO")
    run_once()

