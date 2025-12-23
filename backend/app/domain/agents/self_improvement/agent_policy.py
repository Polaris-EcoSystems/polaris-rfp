from __future__ import annotations

from typing import Any


def _is_nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def sanitize_opportunity_patch(*, patch: dict[str, Any], actor: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Enforce mechanical, tool-level policies for OpportunityState patches.

    Currently enforced:
    - commitments_append items must include provenance (commitments are durable facts).
    """
    p = dict(patch or {})
    checks: list[dict[str, Any]] = []

    actor_meta = actor if isinstance(actor, dict) else {}

    # Commitments: add-only; require provenance on appended items.
    ca = p.get("commitments_append")
    if ca is not None:
        if not isinstance(ca, list):
            checks.append(
                {
                    "policy": "commitment_provenance_required",
                    "status": "fail",
                    "reason": "commitments_append must be a list",
                    "actor": actor_meta,
                }
            )
            p.pop("commitments_append", None)
        else:
            keep: list[dict[str, Any]] = []
            dropped = 0
            for raw in ca:
                if not isinstance(raw, dict):
                    dropped += 1
                    continue
                txt = raw.get("text") or raw.get("fact") or raw.get("commitment")
                prov = raw.get("provenance")
                if not _is_nonempty_str(txt) or not isinstance(prov, dict):
                    dropped += 1
                    continue
                src = prov.get("source") or prov.get("kind")
                if not _is_nonempty_str(src):
                    dropped += 1
                    continue
                keep.append(raw)
            if dropped:
                checks.append(
                    {
                        "policy": "commitment_provenance_required",
                        "status": "fail",
                        "reason": f"dropped {dropped} commitment(s) missing text+provenance.source",
                        "actor": actor_meta,
                    }
                )
            if keep:
                p["commitments_append"] = keep
                checks.append(
                    {
                        "policy": "commitment_provenance_required",
                        "status": "pass",
                        "reason": f"accepted {len(keep)} commitment(s) with provenance",
                        "actor": actor_meta,
                    }
                )
            else:
                p.pop("commitments_append", None)

    return p, checks

