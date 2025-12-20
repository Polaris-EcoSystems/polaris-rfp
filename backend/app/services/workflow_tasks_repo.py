from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.errors import DdbConflict
from ..db.dynamodb.table import get_main_table
from .workflow_task_templates import STAGE_TASK_TEMPLATES, PipelineStage, StageTaskTemplate


TaskStatus = str  # open|done|cancelled


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def task_key(task_id: str) -> dict[str, str]:
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id is required")
    return {"pk": f"TASK#{tid}", "sk": "PROFILE"}


def _rfp_tasks_gsi_pk(rfp_id: str) -> str:
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    return f"RFP_TASKS#{rid}"


def _due_sort_value(due_at: str | None) -> str:
    # Use a stable max sentinel so open tasks without a due date sort last.
    d = str(due_at or "").strip()
    return d or "9999-12-31T23:59:59Z"


def _rfp_tasks_gsi_sk(*, status: TaskStatus, due_at: str | None, task_id: str) -> str:
    st = str(status or "open").strip().lower() or "open"
    due = _due_sort_value(due_at)
    tid = str(task_id or "").strip()
    return f"{st}#{due}#{tid}"


def normalize_task_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    obj = dict(item)
    obj["_id"] = str(item.get("taskId") or "").strip() or None
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        obj.pop(k, None)
    return obj


def get_task_by_id(task_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=task_key(task_id))
    return normalize_task_for_api(it)


def list_tasks_for_rfp(
    *,
    rfp_id: str,
    limit: int = 200,
    next_token: str | None = None,
) -> dict[str, Any]:
    rid = str(rfp_id or "").strip()
    if not rid:
        return {"data": [], "nextToken": None}

    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(_rfp_tasks_gsi_pk(rid)),
        scan_index_forward=True,
        limit=max(1, min(500, int(limit or 200))),
        next_token=next_token,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_task_for_api(it)
        if norm:
            out.append(norm)
    return {"data": out, "nextToken": pg.next_token}


def _stable_task_id(*, rfp_id: str, stage: PipelineStage, template_id: str) -> str:
    base = f"{str(rfp_id).strip()}|{str(stage).strip()}|{str(template_id).strip()}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()  # stable + short
    return f"task_{h[:16]}"


def _build_task_item(
    *,
    task_id: str,
    rfp_id: str,
    proposal_id: str | None,
    stage: PipelineStage,
    template: StageTaskTemplate,
    status: TaskStatus,
    assignee_user_sub: str | None,
    assignee_display_name: str | None,
    due_at: str | None,
) -> dict[str, Any]:
    now = now_iso()
    tid = str(task_id or "").strip()
    rid = str(rfp_id or "").strip()
    pid = str(proposal_id or "").strip() or None
    stg = str(stage or "").strip()
    tpl_id = str(template.get("templateId") or "").strip()
    title = str(template.get("title") or "").strip()
    desc = str(template.get("description") or "").strip()
    st = str(status or "open").strip().lower() or "open"

    item: dict[str, Any] = {
        **task_key(tid),
        "entityType": "WorkflowTask",
        "taskId": tid,
        "rfpId": rid,
        "proposalId": pid,
        "stage": stg,
        "templateId": tpl_id,
        "title": title,
        "description": desc,
        "status": st,
        "assigneeUserSub": str(assignee_user_sub).strip() if assignee_user_sub else None,
        "assigneeDisplayName": str(assignee_display_name).strip()
        if assignee_display_name
        else None,
        "createdAt": now,
        "updatedAt": now,
        "dueAt": str(due_at).strip() if due_at else None,
        "completedAt": None,
        "completedByUserSub": None,
        # GSI1: query tasks for an RFP quickly
        "gsi1pk": _rfp_tasks_gsi_pk(rid),
        "gsi1sk": _rfp_tasks_gsi_sk(status=st, due_at=due_at, task_id=tid),
    }
    return item


def seed_missing_tasks_for_stage(
    *,
    rfp_id: str,
    stage: PipelineStage,
    proposal_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Create missing template tasks for an RFP at a given stage.

    Idempotent: tasks use a stable taskId derived from (rfpId, stage, templateId).
    """
    rid = str(rfp_id or "").strip()
    stg = str(stage or "").strip()
    if not rid or not stg:
        return []

    templates = STAGE_TASK_TEMPLATES.get(stg) or []
    if not templates:
        return []

    # Fetch existing tasks for this RFP (single-page best-effort; UI will usually be small).
    existing = list_tasks_for_rfp(rfp_id=rid, limit=500, next_token=None).get("data") or []
    existing_keys: set[tuple[str, str]] = set()
    for t in existing:
        if not isinstance(t, dict):
            continue
        existing_keys.add((str(t.get("stage") or "").strip(), str(t.get("templateId") or "").strip()))

    created: list[dict[str, Any]] = []
    table = get_main_table()
    for tpl in templates:
        tpl_id = str(tpl.get("templateId") or "").strip()
        if not tpl_id:
            continue
        if (stg, tpl_id) in existing_keys:
            continue

        task_id = _stable_task_id(rfp_id=rid, stage=stg, template_id=tpl_id)
        item = _build_task_item(
            task_id=task_id,
            rfp_id=rid,
            proposal_id=proposal_id,
            stage=stg,
            template=tpl,
            status="open",
            assignee_user_sub=None,
            assignee_display_name=None,
            due_at=None,
        )
        try:
            table.put_item(item=item, condition_expression="attribute_not_exists(pk)")
            created.append(normalize_task_for_api(item) or {})
        except DdbConflict:
            continue
        except Exception:
            # Best-effort: ignore individual task failures.
            continue

    return created


def assign_task(
    *,
    task_id: str,
    assignee_user_sub: str,
    assignee_display_name: str | None = None,
) -> dict[str, Any] | None:
    tid = str(task_id or "").strip()
    sub = str(assignee_user_sub or "").strip()
    if not tid:
        raise ValueError("task_id is required")
    if not sub:
        raise ValueError("assignee_user_sub is required")

    now = now_iso()
    updated = get_main_table().update_item(
        key=task_key(tid),
        update_expression="SET assigneeUserSub = :a, assigneeDisplayName = :n, updatedAt = :u",
        expression_attribute_names=None,
        expression_attribute_values={
            ":a": sub,
            ":n": str(assignee_display_name).strip() if assignee_display_name else None,
            ":u": now,
        },
        return_values="ALL_NEW",
    )
    return normalize_task_for_api(updated)


def complete_task(*, task_id: str, completed_by_user_sub: str | None) -> dict[str, Any] | None:
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id is required")

    now = now_iso()
    # We need the existing record to recompute gsi1sk for status change.
    raw = get_main_table().get_required(key=task_key(tid), message="Task not found")
    due_at = str(raw.get("dueAt") or "").strip() or None

    updated = get_main_table().update_item(
        key=task_key(tid),
        update_expression=(
            "SET #s = :s, completedAt = :c, completedByUserSub = :by, updatedAt = :u, gsi1sk = :g"
        ),
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": "done",
            ":c": now,
            ":by": str(completed_by_user_sub).strip() if completed_by_user_sub else None,
            ":u": now,
            ":g": _rfp_tasks_gsi_sk(status="done", due_at=due_at, task_id=tid),
        },
        return_values="ALL_NEW",
    )
    return normalize_task_for_api(updated)


def reopen_task(*, task_id: str) -> dict[str, Any] | None:
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id is required")

    now = now_iso()
    raw = get_main_table().get_required(key=task_key(tid), message="Task not found")
    due_at = str(raw.get("dueAt") or "").strip() or None

    updated = get_main_table().update_item(
        key=task_key(tid),
        update_expression=(
            "SET #s = :s, completedAt = :c, completedByUserSub = :by, updatedAt = :u, gsi1sk = :g"
        ),
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": "open",
            ":c": None,
            ":by": None,
            ":u": now,
            ":g": _rfp_tasks_gsi_sk(status="open", due_at=due_at, task_id=tid),
        },
        return_values="ALL_NEW",
    )
    return normalize_task_for_api(updated)


def cancel_task(*, task_id: str) -> dict[str, Any] | None:
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id is required")

    now = now_iso()
    raw = get_main_table().get_required(key=task_key(tid), message="Task not found")
    due_at = str(raw.get("dueAt") or "").strip() or None

    updated = get_main_table().update_item(
        key=task_key(tid),
        update_expression="SET #s = :s, updatedAt = :u, gsi1sk = :g",
        expression_attribute_names={"#s": "status"},
        expression_attribute_values={
            ":s": "cancelled",
            ":u": now,
            ":g": _rfp_tasks_gsi_sk(status="cancelled", due_at=due_at, task_id=tid),
        },
        return_values="ALL_NEW",
    )
    return normalize_task_for_api(updated)


def compute_pipeline_stage(*, rfp: dict[str, Any], proposals_for_rfp: Iterable[dict[str, Any]]) -> PipelineStage:
    """
    Mirror frontend pipeline stage logic (frontend/app/(app)/pipeline/page.tsx).
    """
    try:
        if bool((rfp or {}).get("isDisqualified")):
            return "Disqualified"
        review = (rfp or {}).get("review") if isinstance((rfp or {}).get("review"), dict) else {}
        decision = str((review or {}).get("decision") or "").strip().lower()
        if decision == "no_bid":
            return "NoBid"
        if decision != "bid":
            return "BidDecision"

        ps = [p for p in (proposals_for_rfp or []) if isinstance(p, dict)]
        if not ps:
            return "ProposalDraft"

        p = sorted(ps, key=lambda x: str(x.get("updatedAt") or ""), reverse=True)[0]
        status = str(p.get("status") or "").strip().lower()
        if status == "submitted":
            return "Submitted"
        if status == "ready_to_submit":
            return "ReadyToSubmit"
        if status in ("rework", "needs_changes"):
            return "Rework"
        if status == "in_review":
            return "ReviewRebuttal"
        return "ProposalDraft"
    except Exception:
        return "BidDecision"

