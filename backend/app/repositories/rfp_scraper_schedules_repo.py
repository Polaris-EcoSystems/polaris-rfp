from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from boto3.dynamodb.conditions import Key

from app.db.dynamodb.errors import DdbConflict
from app.db.dynamodb.table import get_main_table

ScheduleFrequency = Literal["daily"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_next_run(*, frequency: ScheduleFrequency, from_iso: str | None = None) -> str:
    # Minimal: "daily" means "24h from now (or from provided timestamp)".
    base = datetime.now(timezone.utc)
    if from_iso:
        try:
            raw = str(from_iso).replace("Z", "+00:00")
            base = datetime.fromisoformat(raw)
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
        except Exception:
            base = datetime.now(timezone.utc)
    if frequency == "daily":
        return (base + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z")


def schedule_key(*, schedule_id: str) -> dict[str, str]:
    sid = str(schedule_id or "").strip()
    if not sid:
        raise ValueError("schedule_id is required")
    return {"pk": f"SCRAPERSCHED#{sid}", "sk": "PROFILE"}


def _due_index(*, next_run_at: str, schedule_id: str) -> dict[str, str]:
    nr = str(next_run_at or "").strip()
    sid = str(schedule_id or "").strip()
    return {"gsi1pk": "SCRAPERSCHED_DUE", "gsi1sk": f"{nr}#{sid}"}


def normalize_schedule(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "entityType", "gsi1pk", "gsi1sk"):
        out.pop(k, None)
    out["_id"] = str(out.get("scheduleId") or "").strip() or None
    return out


def create_schedule(
    *,
    name: str | None,
    source: str,
    frequency: ScheduleFrequency = "daily",
    enabled: bool = True,
    search_params: dict[str, Any] | None = None,
    next_run_at: str | None = None,
    created_by_user_sub: str | None = None,
) -> dict[str, Any]:
    sid = "ss_" + uuid.uuid4().hex[:18]
    now = now_iso()
    src = str(source or "").strip()
    if not src:
        raise ValueError("source is required")
    freq = str(frequency or "daily").strip().lower()
    if freq != "daily":
        raise ValueError("unsupported frequency")
    nr = str(next_run_at or "").strip() or _default_next_run(frequency="daily")

    item: dict[str, Any] = {
        **schedule_key(schedule_id=sid),
        "entityType": "ScraperSchedule",
        "scheduleId": sid,
        "name": (str(name).strip() if name else None) or f"{src} daily",
        "source": src,
        "frequency": "daily",
        "enabled": bool(enabled),
        "searchParams": search_params if isinstance(search_params, dict) else {},
        "nextRunAt": nr,
        "lastRunAt": None,
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
        "createdAt": now,
        "updatedAt": now,
        **_due_index(next_run_at=nr, schedule_id=sid),
    }
    item = {k: v for k, v in item.items() if v is not None}
    try:
        get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    except DdbConflict:
        return create_schedule(
            name=name,
            source=source,
            frequency=frequency,
            enabled=enabled,
            search_params=search_params,
            next_run_at=next_run_at,
            created_by_user_sub=created_by_user_sub,
        )
    return normalize_schedule(item) or {}


def get_schedule(*, schedule_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=schedule_key(schedule_id=schedule_id))
    return normalize_schedule(it)


def list_schedules(*, limit: int = 100, next_token: str | None = None) -> dict[str, Any]:
    lim = max(1, min(200, int(limit or 100)))
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq("SCRAPERSCHED_DUE"),
        scan_index_forward=False,
        limit=lim,
        next_token=next_token,
    )
    data: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_schedule(it)
        if norm:
            data.append(norm)
    return {"data": data, "nextToken": pg.next_token, "pagination": {"limit": lim}}


def claim_due_schedules(*, now_iso_str: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    now = str(now_iso_str or now_iso()).strip()
    lim = max(1, min(100, int(limit or 25)))
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq("SCRAPERSCHED_DUE") & Key("gsi1sk").lte(f"{now}#~"),
        scan_index_forward=True,
        limit=lim,
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_schedule(it)
        if not norm:
            continue
        if not bool(norm.get("enabled")):
            continue
        out.append(norm)
    return out


def mark_ran(
    *,
    schedule_id: str,
    now_iso_str: str | None = None,
    next_run_at: str | None = None,
) -> dict[str, Any] | None:
    sid = str(schedule_id or "").strip()
    if not sid:
        raise ValueError("schedule_id is required")
    now = str(now_iso_str or now_iso()).strip()

    existing = get_schedule(schedule_id=sid) or {}
    freq = str(existing.get("frequency") or "daily").strip().lower()
    nr = str(next_run_at or "").strip() or _default_next_run(frequency="daily", from_iso=now)
    if freq != "daily":
        nr = _default_next_run(frequency="daily", from_iso=now)

    updated = get_main_table().update_item(
        key=schedule_key(schedule_id=sid),
        update_expression="SET lastRunAt = :lr, nextRunAt = :nr, updatedAt = :u, gsi1pk = :gpk, gsi1sk = :gsk",
        expression_attribute_names=None,
        expression_attribute_values={
            ":lr": now,
            ":nr": nr,
            ":u": now_iso(),
            ":gpk": "SCRAPERSCHED_DUE",
            ":gsk": f"{nr}#{sid}",
        },
        return_values="ALL_NEW",
    )
    return normalize_schedule(updated)


def update_schedule(
    *,
    schedule_id: str,
    updates_obj: dict[str, Any],
) -> dict[str, Any] | None:
    sid = str(schedule_id or "").strip()
    if not sid:
        raise ValueError("schedule_id is required")

    allowed = {"name", "enabled", "searchParams", "nextRunAt"}
    raw = updates_obj if isinstance(updates_obj, dict) else {}
    updates = {k: raw.get(k) for k in allowed if k in raw}

    expr_parts: list[str] = []
    expr_values: dict[str, Any] = {":u": now_iso(), ":sid": sid}
    expr_names: dict[str, str] = {}

    if "name" in updates:
        expr_values[":n"] = (str(updates.get("name") or "").strip() or None)
        expr_parts.append("name = :n")
    if "enabled" in updates:
        expr_values[":e"] = bool(updates.get("enabled"))
        expr_parts.append("enabled = :e")
    if "searchParams" in updates:
        sp = updates.get("searchParams")
        expr_values[":sp"] = sp if isinstance(sp, dict) else {}
        expr_parts.append("searchParams = :sp")
    if "nextRunAt" in updates:
        nr = str(updates.get("nextRunAt") or "").strip()
        if nr:
            expr_values[":nr"] = nr
            expr_values[":gpk"] = "SCRAPERSCHED_DUE"
            expr_values[":gsk"] = f"{nr}#{sid}"
            expr_parts.append("nextRunAt = :nr")
            expr_parts.append("gsi1pk = :gpk")
            expr_parts.append("gsi1sk = :gsk")

    expr_parts.append("updatedAt = :u")
    updated = get_main_table().update_item(
        key=schedule_key(schedule_id=sid),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )
    return normalize_schedule(updated)


