from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.db.dynamodb.table import get_main_table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def type_pk(t: str) -> str:
    return f"TYPE#{t}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def _profile_key(prefix: str, id_: str) -> dict[str, str]:
    return {"pk": f"{prefix}#{id_}", "sk": "PROFILE"}


def _normalize(item: dict[str, Any] | None, id_field: str | None = None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    if id_field and item.get(id_field):
        out["_id"] = item.get(id_field)
    return out


# --- Companies ---

def company_key(company_id: str) -> dict[str, str]:
    return _profile_key("COMPANY", company_id)


def get_company_by_company_id(company_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=company_key(company_id))
    return _normalize(item, id_field="companyId")


def list_companies(limit: int = 200) -> list[dict[str, Any]]:
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("COMPANY")),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 200))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = _normalize(it, id_field="companyId")
        if norm:
            out.append(norm)
    return out


def upsert_company(company: dict[str, Any]) -> dict[str, Any]:
    company_id = company.get("companyId") or new_id("company")
    now = now_iso()
    created_at = company.get("createdAt") or now
    item = {
        **company_key(company_id),
        "entityType": "Company",
        "companyId": company_id,
        "createdAt": created_at,
        "updatedAt": now,
        **company,
        "gsi1pk": type_pk("COMPANY"),
        "gsi1sk": f"{now}#{company_id}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item, id_field="companyId") or {}


# --- Team ---

def team_member_key(member_id: str) -> dict[str, str]:
    return _profile_key("TEAM", member_id)


def get_team_member_by_id(member_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=team_member_key(member_id))
    return _normalize(item, id_field="memberId")


def list_team_members(limit: int = 200) -> list[dict[str, Any]]:
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("TEAM_MEMBER")),
        scan_index_forward=False,
        limit=max(1, min(500, int(limit or 200))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = _normalize(it, id_field="memberId")
        if norm:
            out.append(norm)
    return out


def get_team_members_by_ids(member_ids: list[str]) -> list[dict[str, Any]]:
    # No batch_get helper yet; list + filter is fine for small selections.
    all_members = list_team_members(limit=500)
    wanted = {str(x) for x in (member_ids or [])}
    return [m for m in all_members if str(m.get("memberId")) in wanted]


def upsert_team_member(member: dict[str, Any]) -> dict[str, Any]:
    member_id = member.get("memberId") or new_id("member")
    now = now_iso()
    created_at = member.get("createdAt") or now
    item = {
        **team_member_key(member_id),
        "entityType": "TeamMember",
        "memberId": member_id,
        "createdAt": created_at,
        "updatedAt": now,
        **member,
        "gsi1pk": type_pk("TEAM_MEMBER"),
        "gsi1sk": f"{now}#{member_id}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item, id_field="memberId") or {}


# --- Past projects ---

def past_project_key(project_id: str) -> dict[str, str]:
    return _profile_key("PROJECT", project_id)


def list_past_projects(limit: int = 200) -> list[dict[str, Any]]:
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("PAST_PROJECT")),
        scan_index_forward=False,
        limit=max(1, min(500, int(limit or 200))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = _normalize(it, id_field="projectId")
        if norm:
            out.append(norm)
    return out


def get_past_project_by_id(project_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=past_project_key(project_id))
    return _normalize(item, id_field="projectId")


def upsert_past_project(project: dict[str, Any]) -> dict[str, Any]:
    project_id = project.get("projectId") or new_id("proj")
    now = now_iso()
    created_at = project.get("createdAt") or now
    item = {
        **past_project_key(project_id),
        "entityType": "PastProject",
        "projectId": project_id,
        "createdAt": created_at,
        "updatedAt": now,
        **project,
        "gsi1pk": type_pk("PAST_PROJECT"),
        "gsi1sk": f"{now}#{project_id}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item, id_field="projectId") or {}


# --- References ---

def project_reference_key(reference_id: str) -> dict[str, str]:
    return _profile_key("REF", reference_id)


def list_project_references(limit: int = 200) -> list[dict[str, Any]]:
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("PROJECT_REFERENCE")),
        scan_index_forward=False,
        limit=max(1, min(500, int(limit or 200))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = _normalize(it, id_field="referenceId")
        if norm:
            out.append(norm)
    return out


def get_project_references_by_ids(reference_ids: list[str]) -> list[dict[str, Any]]:
    all_refs = list_project_references(limit=500)
    wanted = {str(x) for x in (reference_ids or [])}
    out: list[dict[str, Any]] = []
    for r in all_refs:
        rid = str(r.get("_id") or r.get("referenceId") or "")
        if rid in wanted:
            out.append(r)
    return out


def get_project_reference_by_id(reference_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=project_reference_key(reference_id))
    return _normalize(item, id_field="referenceId")


def upsert_project_reference(ref: dict[str, Any]) -> dict[str, Any]:
    reference_id = ref.get("referenceId") or new_id("ref")
    now = now_iso()
    created_at = ref.get("createdAt") or now
    item = {
        **project_reference_key(reference_id),
        "entityType": "ProjectReference",
        "referenceId": reference_id,
        "createdAt": created_at,
        "updatedAt": now,
        **ref,
        "gsi1pk": type_pk("PROJECT_REFERENCE"),
        "gsi1sk": f"{now}#{reference_id}",
    }
    get_main_table().put_item(item=item)
    return _normalize(item, id_field="referenceId") or {}
