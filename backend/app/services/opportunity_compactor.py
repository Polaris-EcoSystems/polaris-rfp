from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..ai.verified_calls import call_json_verified
from ..repositories.rfp.agent_journal_repo import list_recent_entries
from ..repositories.rfp.opportunity_state_repo import ensure_state_exists, get_state, patch_state


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class OpportunityCompactionAI(BaseModel):
    """
    Canonical compaction output: a short summary + refreshed goal stack fields.
    """

    summary: str = Field(min_length=1, max_length=2000)
    openLoops: list[str] = Field(default_factory=list, max_length=50)
    nextBestActions: list[str] = Field(default_factory=list, max_length=25)
    blockers: list[str] = Field(default_factory=list, max_length=25)
    evidenceNeeded: list[str] = Field(default_factory=list, max_length=25)


def run_opportunity_compaction(
    *,
    rfp_id: str,
    journal_limit: int = 25,
) -> dict[str, Any]:
    """
    Summarize recent journal entries into OpportunityState.state.summary and related fields.
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")

    ensure_state_exists(rfp_id=rid)
    state = get_state(rfp_id=rid) or {}
    st_raw = state.get("state") if isinstance(state, dict) else None
    st: dict[str, Any] = st_raw if isinstance(st_raw, dict) else {}

    entries = list_recent_entries(rfp_id=rid, limit=max(1, min(40, int(journal_limit or 25))))
    # Keep prompt bounded; include only key fields.
    facts: list[dict[str, Any]] = []
    for e in entries[:40]:
        if not isinstance(e, dict):
            continue
        facts.append(
            {
                "createdAt": e.get("createdAt"),
                "topics": e.get("topics"),
                "userStated": e.get("userStated"),
                "agentIntent": e.get("agentIntent"),
                "whatChanged": e.get("whatChanged"),
                "why": e.get("why"),
            }
        )

    prompt = "\n".join(
        [
            "You are an operations-grade agent that maintains a durable OpportunityState for an RFP.",
            "Your job is to compact the recent journal into a short summary and a refreshed goal stack.",
            "",
            "Rules:",
            "- Only use the journal entries and the existing state provided.",
            "- Keep the summary factual and specific; do not invent details.",
            "- Prefer short bullets in openLoops/nextBestActions/blockers/evidenceNeeded.",
            "- If information is missing, leave that list empty rather than guessing.",
            "",
            "Existing state snapshot (may be stale):",
            str({k: st.get(k) for k in ('stage', 'dueDates', 'summary', 'openLoops', 'nextBestActions', 'blockers', 'evidenceNeeded')}),
            "",
            "Recent journal entries (most recent first):",
            str(facts),
            "",
            "Return a JSON object with keys: summary, openLoops, nextBestActions, blockers, evidenceNeeded.",
        ]
    )

    parsed, _meta = call_json_verified(
        purpose="generate_content",
        response_model=OpportunityCompactionAI,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        temperature=0.0,
        retries=2,
    )

    patch = {
        "summary": parsed.summary.strip(),
        "openLoops": [str(x).strip() for x in (parsed.openLoops or []) if str(x).strip()][:50],
        "nextBestActions": [str(x).strip() for x in (parsed.nextBestActions or []) if str(x).strip()][:25],
        "blockers": [str(x).strip() for x in (parsed.blockers or []) if str(x).strip()][:25],
        "evidenceNeeded": [str(x).strip() for x in (parsed.evidenceNeeded or []) if str(x).strip()][:25],
        "lastCompactedAt": _now_iso(),
    }

    updated = patch_state(rfp_id=rid, patch=patch, updated_by_user_sub=None, create_snapshot=True)
    return {"ok": True, "rfpId": rid, "patch": patch, "opportunity": updated}

