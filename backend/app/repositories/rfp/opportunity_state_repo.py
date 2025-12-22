from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ...db.dynamodb.errors import DdbConflict
from ...db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def opportunity_state_key(*, rfp_id: str) -> dict[str, str]:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    return {"pk": f"OPPORTUNITY#{rid}", "sk": "STATE#CURRENT"}


def opportunity_snapshot_key(*, rfp_id: str, snapshot_id: str, created_at: str) -> dict[str, str]:
    rid = str(rfp_id or "").strip()
    sid = str(snapshot_id or "").strip()
    ts = str(created_at or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    if not sid:
        raise ValueError("snapshot_id is required")
    if not ts:
        raise ValueError("created_at is required")
    # Keep snapshot SK sortable by time, then id.
    return {"pk": f"OPPORTUNITY#{rid}", "sk": f"STATE#SNAPSHOT#{ts}#{sid}"}


def normalize_state_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "entityType"):
        out.pop(k, None)
    # Provide a stable _id that matches rfpId.
    rid = str(out.get("rfpId") or "").strip()
    out["_id"] = rid or None
    return out


def default_state(*, rfp_id: str) -> dict[str, Any]:
    """
    Canonical durable state artifact for an opportunity (RFP-centric).

    This is the replacement for Strix “state files”: every agent invocation should
    reconstruct context from this object + journal + events.
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    return {
        "rfpId": rid,
        # Linkage to other domain objects (best-effort; may be empty early).
        "proposalIds": [],
        "contractingCaseId": None,
        # Long-lived working summary (compacted from journal + events).
        "summary": None,
        "lastCompactedAt": None,
        # High-level workflow state.
        "stage": None,  # BidDecision|ProposalDraft|...|Contracting|...
        "owners": {},
        "dueDates": {},  # submission/questions/meeting/etc
        "comms": {},  # e.g. lastSlackSummaryAt, lastCustomerEmailAt
        "winThemes": [],
        "pricingAssumptions": [],
        # Contracting-style layers.
        "requirements": [],
        "riskRegister": [],
        # Commitments are durable facts: add-only; never silently rewrite.
        "commitments": [],
        "stakeholders": [],
        # Open loops / goal stack (agent-visible planning primitives).
        "openLoops": [],
        "nextBestActions": [],
        "blockers": [],
        "evidenceNeeded": [],
        # Google Drive integration.
        "driveFolders": {},  # Map of folder type to Drive folder ID
        "driveFiles": [],  # Array of {fileId, fileName, folderId, category, uploadedAt, uploadedBy}
    }


def seed_from_platform(*, rfp_id: str) -> dict[str, Any]:
    """
    Best-effort seed of OpportunityState.state from existing platform objects.

    This enforces the “state is externalized” pattern:
    - authoritative inputs: RFP + proposals + contracting case
    - computed: stage (mirrors frontend pipeline)
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")

    # Local imports to keep module load light and avoid cyclic import issues.
    from .contracting_repo import get_case_by_proposal_id
    from ..repositories.rfp.proposals_repo import list_proposals_by_rfp
    from ..repositories.rfp.rfps_repo import get_rfp_by_id
    from .workflow_tasks_repo import compute_pipeline_stage

    rfp = get_rfp_by_id(rid) or {}
    proposals = list_proposals_by_rfp(rid) or []
    proposal_ids = [
        str(p.get("_id") or p.get("proposalId") or "").strip()
        for p in proposals
        if isinstance(p, dict)
    ]
    proposal_ids = [pid for pid in proposal_ids if pid]

    # Stage: mirror frontend pipeline stage logic.
    stage = None
    try:
        stage = compute_pipeline_stage(rfp=rfp if isinstance(rfp, dict) else {}, proposals_for_rfp=proposals)
    except Exception:
        stage = None

    # Contracting linkage: if any proposal has a case, attach it (prefer most-recent proposal).
    case_id: str | None = None
    for p in proposals[:15]:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("_id") or p.get("proposalId") or "").strip()
        if not pid:
            continue
        c = get_case_by_proposal_id(pid)
        if c and isinstance(c, dict):
            case_id = str(c.get("_id") or c.get("caseId") or "").strip() or None
            if case_id:
                break

    due: dict[str, Any] = {}
    for k in ("submissionDeadline", "questionsDeadline", "bidMeetingDate", "bidRegistrationDate", "projectDeadline"):
        v = (rfp or {}).get(k) if isinstance(rfp, dict) else None
        if v:
            due[k] = v

    return {
        "rfpId": rid,
        "proposalIds": proposal_ids,
        "contractingCaseId": case_id,
        "stage": str(stage) if stage else None,
        "dueDates": due,
    }


def get_state(*, rfp_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=opportunity_state_key(rfp_id=rfp_id))
    return normalize_state_for_api(it)


def ensure_state_exists(
    *,
    rfp_id: str,
    created_by_user_sub: str | None = None,
    seed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create the OpportunityState row if missing; return the current row.

    This is safe to call from multiple invocations; it will not overwrite.
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")

    existing = get_state(rfp_id=rid)
    if existing:
        return existing

    now = _now_iso()
    base = default_state(rfp_id=rid)
    # Populate with best-effort linkage + computed stage on first create.
    try:
        base.update(seed_from_platform(rfp_id=rid))
    except Exception:
        pass
    if isinstance(seed, dict) and seed:
        # Shallow merge; deeper merges happen through patch APIs.
        base.update({k: v for k, v in seed.items() if k in base})

    item: dict[str, Any] = {
        **opportunity_state_key(rfp_id=rid),
        "entityType": "OpportunityState",
        "rfpId": rid,
        "version": 1,
        "state": base,
        "createdAt": now,
        "updatedAt": now,
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
    }
    # Clean nulls.
    item = {k: v for k, v in item.items() if v is not None}
    try:
        get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    except DdbConflict:
        pass
    return normalize_state_for_api(get_main_table().get_item(key=opportunity_state_key(rfp_id=rid))) or {}


def _merge_state(existing_state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """
    Patch semantics:
    - top-level keys in `state` may be replaced (shallow) for known keys
    - list fields support append via special *_append keys
    - commitments are add-only: only appends are allowed
    """
    cur = existing_state if isinstance(existing_state, dict) else {}
    nxt = dict(cur)

    # Known canonical keys.
    allowed_keys = set(default_state(rfp_id=str(cur.get("rfpId") or patch.get("rfpId") or "")).keys())

    # Apply direct replacements (shallow).
    for k, v in (patch or {}).items():
        if k.endswith("_append"):
            continue
        if k not in allowed_keys:
            continue
        # Guard: commitments must be add-only (no overwrite).
        if k == "commitments":
            continue
        # Dict-like fields: merge rather than replace to reduce accidental erasure.
        if k in ("owners", "dueDates", "comms", "driveFolders") and isinstance(nxt.get(k), dict) and isinstance(v, dict):
            merged = dict(nxt.get(k) or {})
            merged.update(v)
            nxt[k] = merged
        else:
            nxt[k] = v

    # Append helpers (bounded).
    def _append_list(field: str, items: Any, *, max_items: int = 50) -> None:
        if field not in allowed_keys:
            return
        if not isinstance(items, list):
            return
        existing = nxt.get(field)
        base_list = existing if isinstance(existing, list) else []
        nxt[field] = base_list + [x for x in items[:max_items]]

    _append_list("requirements", patch.get("requirements_append"))
    _append_list("riskRegister", patch.get("riskRegister_append"))
    _append_list("stakeholders", patch.get("stakeholders_append"))
    _append_list("openLoops", patch.get("openLoops_append"))
    _append_list("nextBestActions", patch.get("nextBestActions_append"))
    _append_list("blockers", patch.get("blockers_append"))
    _append_list("evidenceNeeded", patch.get("evidenceNeeded_append"))
    _append_list("driveFiles", patch.get("driveFiles_append"), max_items=100)

    # Commitments: add-only via commitments_append
    _append_list("commitments", patch.get("commitments_append"), max_items=25)

    return nxt


def patch_state(
    *,
    rfp_id: str,
    patch: dict[str, Any],
    updated_by_user_sub: str | None = None,
    create_snapshot: bool = True,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    Optimistic concurrency patch of OpportunityState.state.
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")

    ensure_state_exists(rfp_id=rid)

    retries = max(1, min(8, int(max_retries or 3)))
    table = get_main_table()

    for _ in range(retries):
        current = table.get_item(key=opportunity_state_key(rfp_id=rid)) or {}
        if not current:
            ensure_state_exists(rfp_id=rid)
            current = table.get_item(key=opportunity_state_key(rfp_id=rid)) or {}

        cur_ver = int(current.get("version") or 0)
        raw_state = current.get("state")
        cur_state: dict[str, Any] = raw_state if isinstance(raw_state, dict) else default_state(rfp_id=rid)
        next_state = _merge_state(cur_state, patch if isinstance(patch, dict) else {})

        now = _now_iso()
        next_ver = max(1, cur_ver + 1)

        # Optional snapshot for audit/debug/rollback.
        if create_snapshot:
            sid = "snap_" + uuid.uuid4().hex[:18]
            snap_item: dict[str, Any] = {
                **opportunity_snapshot_key(rfp_id=rid, snapshot_id=sid, created_at=now),
                "entityType": "OpportunityStateSnapshot",
                "rfpId": rid,
                "snapshotId": sid,
                "createdAt": now,
                "version": cur_ver,
                "state": cur_state,
                "createdByUserSub": str(updated_by_user_sub).strip() if updated_by_user_sub else None,
            }
            snap_item = {k: v for k, v in snap_item.items() if v is not None}

            table.transact_write(
                puts=[
                    table.tx_put(
                        item=snap_item,
                        condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
                    )
                ],
                updates=[
                    table.tx_update(
                        key=opportunity_state_key(rfp_id=rid),
                        update_expression="SET #s = :s, version = :nv, updatedAt = :u",
                        expression_attribute_names={"#s": "state"},
                        expression_attribute_values={
                            ":s": next_state,
                            ":nv": next_ver,
                            ":u": now,
                            ":v": cur_ver,
                        },
                        condition_expression="version = :v",
                    )
                ],
            )
        else:
            updated = table.update_item(
                key=opportunity_state_key(rfp_id=rid),
                update_expression="SET #s = :s, version = :nv, updatedAt = :u",
                expression_attribute_names={"#s": "state"},
                expression_attribute_values={":s": next_state, ":nv": next_ver, ":u": now, ":v": cur_ver},
                condition_expression="version = :v",
                return_values="ALL_NEW",
            )
            if updated:
                return normalize_state_for_api(updated) or {}

        # Re-read after transaction path
        out = table.get_item(key=opportunity_state_key(rfp_id=rid))
        if out:
            return normalize_state_for_api(out) or {}

    # If we got here, we failed to win the concurrency race repeatedly.
    # Return the latest state as best-effort.
    latest = table.get_item(key=opportunity_state_key(rfp_id=rid))
    return normalize_state_for_api(latest) or {}

