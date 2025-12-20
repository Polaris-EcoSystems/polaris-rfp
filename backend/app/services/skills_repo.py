from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_tags(tags: Any, *, max_items: int = 25) -> list[str]:
    raw = tags if isinstance(tags, list) else []
    out: list[str] = []
    for t in raw[: max(0, int(max_items))]:
        s = str(t or "").strip()
        if not s:
            continue
        s2 = s.lower()
        if s2 not in out:
            out.append(s2)
    return out


def skill_key(*, skill_id: str) -> dict[str, str]:
    sid = str(skill_id or "").strip()
    if not sid:
        raise ValueError("skill_id is required")
    return {"pk": f"SKILL#{sid}", "sk": "PROFILE"}


def normalize_skill(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    out["_id"] = str(out.get("skillId") or "").strip() or None
    return out


def create_skill_index(
    *,
    name: str,
    description: str,
    tags: list[str] | None,
    s3_key: str,
    version: int = 1,
    enabled: bool = True,
    risk_level: str | None = None,
    required_tools: list[str] | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """
    Create a new SkillIndex row (metadata) in the main DynamoDB table.

    Skill body content lives in S3; this row stores only pointers + metadata.
    """
    nm = str(name or "").strip()
    if not nm:
        raise ValueError("name is required")
    desc = str(description or "").strip()
    if not desc:
        raise ValueError("description is required")
    sk = str(s3_key or "").strip()
    if not sk:
        raise ValueError("s3_key is required")

    sid = "sk_" + uuid.uuid4().hex[:18]
    now = _now_iso()

    nm_l = nm.lower()
    item: dict[str, Any] = {
        **skill_key(skill_id=sid),
        "entityType": "SkillIndex",
        "skillId": sid,
        "name": nm,
        "nameLower": nm_l,
        "description": desc[:2000],
        "tags": _clean_tags(tags),
        "version": max(1, int(version or 1)),
        "enabled": bool(enabled),
        "riskLevel": str(risk_level or "").strip().lower() or "low",
        "requiredTools": [str(x).strip() for x in (required_tools or []) if str(x).strip()][:50],
        "owner": str(owner or "").strip() or None,
        "s3Key": sk,
        "createdAt": now,
        "updatedAt": now,
        # Listing / prefix search index
        "gsi1pk": "TYPE#SKILL",
        "gsi1sk": f"NAME#{nm_l}#{sid}",
    }
    item = {k: v for k, v in item.items() if v is not None}
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_skill(item) or {}


def upsert_skill_index(
    *,
    skill_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Admin/operator upsert of SkillIndex (not exposed as a tool by default).

    This is intentionally shallow and bounded to prevent accidental metadata explosion.
    """
    sid = str(skill_id or "").strip()
    if not sid:
        raise ValueError("skill_id is required")
    current = get_main_table().get_item(key=skill_key(skill_id=sid)) or {}
    now = _now_iso()

    item: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
    if not item:
        # If missing, create a minimal base row; caller must provide required fields.
        item = {
            **skill_key(skill_id=sid),
            "entityType": "SkillIndex",
            "skillId": sid,
            "createdAt": now,
        }

    allowed = {
        "name",
        "description",
        "tags",
        "version",
        "enabled",
        "riskLevel",
        "requiredTools",
        "owner",
        "s3Key",
    }
    u = updates if isinstance(updates, dict) else {}
    for k, v in list(u.items())[:80]:
        if k not in allowed:
            continue
        if k == "name":
            nm = str(v or "").strip()
            if nm:
                item["name"] = nm[:240]
                item["nameLower"] = nm.lower()
        elif k == "description":
            item["description"] = str(v or "").strip()[:2000]
        elif k == "tags":
            item["tags"] = _clean_tags(v)
        elif k == "version":
            item["version"] = max(1, int(v or 1))
        elif k == "enabled":
            item["enabled"] = bool(v)
        elif k == "riskLevel":
            item["riskLevel"] = str(v or "").strip().lower()[:40] or "low"
        elif k == "requiredTools":
            item["requiredTools"] = [str(x).strip() for x in (v if isinstance(v, list) else []) if str(x).strip()][:50]
        elif k == "owner":
            item["owner"] = str(v or "").strip()[:200] or None
        elif k == "s3Key":
            sk = str(v or "").strip()
            if sk:
                item["s3Key"] = sk[:2048]

    # Recompute index keys if we have a name.
    nm_l = str(item.get("nameLower") or "").strip().lower()
    if nm_l:
        item["gsi1pk"] = "TYPE#SKILL"
        item["gsi1sk"] = f"NAME#{nm_l}#{sid}"

    item["pk"] = skill_key(skill_id=sid)["pk"]
    item["sk"] = "PROFILE"
    item["entityType"] = "SkillIndex"
    item["skillId"] = sid
    item["updatedAt"] = now

    get_main_table().put_item(item=item)
    return normalize_skill(item) or {}


def get_skill_index(*, skill_id: str) -> dict[str, Any] | None:
    sid = str(skill_id or "").strip()
    if not sid:
        return None
    it = get_main_table().get_item(key=skill_key(skill_id=sid))
    return normalize_skill(it)


def search_skills(
    *,
    query: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
    next_token: str | None = None,
) -> dict[str, Any]:
    """
    Search SkillIndex entries.

    Implementation notes:
    - Primary fast path: prefix search on name via GSI1 begins_with(NAME#<query_lower>).
    - Tag filtering: applied in code (bounded) since tags are not indexed.
    """
    q = str(query or "").strip().lower()
    want_tags = _clean_tags(tags) if tags else []
    lim = max(1, min(25, int(limit or 10)))

    table = get_main_table()
    items: list[dict[str, Any]] = []

    # We'll loop a few pages to satisfy tag filtering without scanning unboundedly.
    scanned_pages = 0
    tok = str(next_token or "").strip() or None

    while len(items) < lim and scanned_pages < 6:
        scanned_pages += 1
        if q:
            expr = Key("gsi1pk").eq("TYPE#SKILL") & Key("gsi1sk").begins_with(f"NAME#{q}")
        else:
            expr = Key("gsi1pk").eq("TYPE#SKILL")

        pg = table.query_page(
            index_name="GSI1",
            key_condition_expression=expr,
            scan_index_forward=True,
            limit=50,
            next_token=tok,
        )
        tok = pg.next_token

        for raw in pg.items or []:
            norm = normalize_skill(raw if isinstance(raw, dict) else None)
            if not norm:
                continue
            if want_tags:
                have = norm.get("tags")
                have_tags = [str(t).strip().lower() for t in (have if isinstance(have, list) else []) if str(t).strip()]
                if any(t not in have_tags for t in want_tags):
                    continue
            items.append(norm)
            if len(items) >= lim:
                break

        if not tok:
            break

    return {"ok": True, "data": items[:lim], "nextToken": tok}

