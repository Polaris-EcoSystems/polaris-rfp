from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from boto3.dynamodb.conditions import Key

from ...db.dynamodb.table import get_main_table


ChangeProposalStatus = Literal["draft", "proposed", "pr_opened", "merged", "failed", "cancelled"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _type_pk(t: str) -> str:
    return f"TYPE#{t}"


def proposal_key(*, proposal_id: str) -> dict[str, str]:
    pid = str(proposal_id or "").strip()
    if not pid:
        raise ValueError("proposal_id is required")
    return {"pk": f"CHANGEPROP#{pid}", "sk": "PROFILE"}


def normalize(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    out["_id"] = str(out.get("proposalId") or "").strip() or None
    return out


def create_change_proposal(
    *,
    title: str,
    summary: str,
    patch: str,
    files_touched: list[str] | None = None,
    rfp_id: str | None = None,
    created_by_slack_user_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pid = "cp_" + uuid.uuid4().hex[:18]
    now = _now_iso()
    item: dict[str, Any] = {
        **proposal_key(proposal_id=pid),
        "entityType": "ChangeProposal",
        "proposalId": pid,
        "status": "proposed",
        "title": str(title or "").strip()[:180] or "Change proposal",
        "summary": str(summary or "").strip()[:2000],
        "patch": str(patch or ""),
        "filesTouched": [str(x).strip() for x in (files_touched or []) if str(x).strip()][:50],
        "rfpId": str(rfp_id).strip() if rfp_id else None,
        "createdBySlackUserId": str(created_by_slack_user_id).strip() if created_by_slack_user_id else None,
        "createdAt": now,
        "updatedAt": now,
        "gsi1pk": _type_pk("CHANGE_PROPOSAL"),
        "gsi1sk": f"{now}#{pid}",
        "meta": meta if isinstance(meta, dict) else {},
    }
    item = {k: v for k, v in item.items() if v is not None}
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize(item) or {}


def get_change_proposal(proposal_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=proposal_key(proposal_id=str(proposal_id)))
    return normalize(it)


def update_change_proposal(proposal_id: str, updates_obj: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {"status", "prUrl", "prNumber", "error", "updatedAt"}
    updates = {k: v for k, v in (updates_obj or {}).items() if k in allowed}
    if "updatedAt" not in updates:
        updates["updatedAt"] = _now_iso()

    expr_parts: list[str] = []
    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        names[nk] = k
        values[vk] = v
        expr_parts.append(f"{nk} = {vk}")

    updated = get_main_table().update_item(
        key=proposal_key(proposal_id=str(proposal_id)),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=names,
        expression_attribute_values=values,
        return_values="ALL_NEW",
    )
    return normalize(updated)


def list_recent_change_proposals(limit: int = 50) -> dict[str, Any]:
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(_type_pk("CHANGE_PROPOSAL")),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=None,
    )
    out = [normalize(it) for it in pg.items or []]
    return {"data": [x for x in out if x], "nextToken": pg.next_token}

