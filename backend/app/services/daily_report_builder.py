from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .agent_events_repo import list_recent_events_global
from .change_proposals_repo import list_recent_change_proposals


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_northstar_daily_report(*, hours: int = 24) -> dict[str, Any]:
    """
    Build a compact daily report describing North Star's autonomous activity
    over the last N hours, based primarily on the durable AgentEvent log.
    """
    h = max(1, min(72, int(hours or 24)))
    end = _now()
    start = end - timedelta(hours=h)
    start_iso = _iso(start)

    events = list_recent_events_global(since_iso=start_iso, limit=500)

    by_type: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    opportunities_touched: set[str] = set()
    policy_failures = 0

    for e in events:
        if not isinstance(e, dict):
            continue
        t = str(e.get("type") or "").strip() or "event"
        by_type[t] = by_type.get(t, 0) + 1

        tool = str(e.get("tool") or "").strip()
        if tool:
            by_tool[tool] = by_tool.get(tool, 0) + 1

        rid = str(e.get("rfpId") or "").strip()
        if rid:
            opportunities_touched.add(rid)

        pcs = e.get("policyChecks")
        if isinstance(pcs, list):
            policy_failures += sum(
                1
                for x in pcs
                if isinstance(x, dict) and str(x.get("status") or "").strip().lower() in ("fail", "failed")
            )

    cps = list_recent_change_proposals(limit=100).get("data") or []
    recent_cps: list[dict[str, Any]] = []
    for cp in cps:
        if not isinstance(cp, dict):
            continue
        ca = str(cp.get("createdAt") or "").strip()
        if ca and ca >= start_iso:
            recent_cps.append(cp)

    # Summaries
    top_types = sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    top_tools = sorted(by_tool.items(), key=lambda kv: (-kv[1], kv[0]))[:8]

    pr_opened = sum(1 for cp in recent_cps if str(cp.get("status") or "") == "pr_opened")
    merged = sum(1 for cp in recent_cps if str(cp.get("status") or "") == "merged")
    failed = sum(1 for cp in recent_cps if str(cp.get("status") or "") == "failed")

    lines: list[str] = []
    lines.append(f"*North Star daily report* (last {h}h)")
    lines.append(f"- Opportunities touched: {len(opportunities_touched)}")
    lines.append(f"- Events logged: {len(events)}")

    if top_types:
        lines.append("- Top event types:")
        for k, v in top_types:
            lines.append(f"  - `{k}`: {v}")

    if top_tools:
        lines.append("- Top tools used:")
        for k, v in top_tools:
            lines.append(f"  - `{k}`: {v}")

    if recent_cps:
        lines.append("- Self-improvement (change proposals):")
        lines.append(f"  - Created: {len(recent_cps)}")
        lines.append(f"  - PRs opened: {pr_opened}")
        lines.append(f"  - Merged: {merged}")
        if failed:
            lines.append(f"  - Failed: {failed}")

    if policy_failures:
        lines.append(f"- Policy failures observed: {policy_failures}")

    return {
        "ok": True,
        "window": {"start": start_iso, "end": _iso(end), "hours": h},
        "events": {"count": len(events), "byType": by_type, "byTool": by_tool},
        "opportunitiesTouched": sorted(opportunities_touched)[:200],
        "changeProposals": {"recentCount": len(recent_cps), "prsOpened": pr_opened, "merged": merged, "failed": failed},
        "slackText": "\n".join(lines).strip(),
    }

