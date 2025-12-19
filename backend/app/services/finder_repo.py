from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.table import get_main_table


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def user_state_key(user_sub: str) -> dict[str, str]:
    return {"pk": f"USER#{user_sub}", "sk": "LINKEDIN#STATE"}


def run_key(run_id: str) -> dict[str, str]:
    return {"pk": f"FINDER#RUN#{run_id}", "sk": "PROFILE"}


def rfp_run_link_key(rfp_id: str, run_id: str) -> dict[str, str]:
    return {"pk": f"RFP#{rfp_id}", "sk": f"FINDER#RUN#{run_id}"}


def profile_key(run_id: str, profile_id: str) -> dict[str, str]:
    return {"pk": f"FINDER#RUN#{run_id}", "sk": f"FINDER#PROFILE#{profile_id}"}


def put_user_linkedin_state(*, user_sub: str, encrypted_storage_state: str) -> None:
    item = {
        **user_state_key(user_sub),
        "entityType": "LinkedInState",
        "userSub": user_sub,
        "encryptedStorageState": encrypted_storage_state,
        "updatedAt": now_iso(),
    }
    get_main_table().put_item(item=item)


def get_user_linkedin_state(*, user_sub: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key=user_state_key(user_sub))


def create_run(
    *,
    run_id: str,
    rfp_id: str,
    user_sub: str,
    company_name: str | None,
    company_linkedin_url: str | None,
    max_people: int,
    target_titles: list[str] | None,
) -> dict[str, Any]:
    created_at = now_iso()
    run_item: dict[str, Any] = {
        **run_key(run_id),
        "entityType": "FinderRun",
        "runId": run_id,
        "rfpId": rfp_id,
        "userSub": user_sub,
        "status": "queued",
        "companyName": company_name or "",
        "companyLinkedInUrl": company_linkedin_url or "",
        "maxPeople": int(max_people or 0),
        "targetTitles": target_titles or [],
        "createdAt": created_at,
        "updatedAt": created_at,
        "progress": {"discovered": 0, "saved": 0, "scored": 0},
        "error": None,
    }
    link_item: dict[str, Any] = {
        **rfp_run_link_key(rfp_id, run_id),
        "entityType": "FinderRunLink",
        "runId": run_id,
        "rfpId": rfp_id,
        "userSub": user_sub,
        "createdAt": created_at,
    }

    # Transactional create: ensure the run and the RFP link are created atomically.
    t = get_main_table()
    t.transact_write(
        puts=[
            t.tx_put(
                item=run_item,
                condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            ),
            t.tx_put(
                item=link_item,
                condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            ),
        ]
    )
    return run_item


def get_run(run_id: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key=run_key(run_id))


def update_run_fields(run_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    updates = dict(updates or {})
    updates["updatedAt"] = now_iso()

    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {}
    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        expr_names[nk] = k
        expr_values[vk] = v
        expr_parts.append(f"{nk} = {vk}")

    return get_main_table().update_item(
        key=run_key(run_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )


def put_profiles(*, run_id: str, profiles: Iterable[dict[str, Any]]) -> int:
    n = 0
    for p in profiles:
        profile_id = str(p.get("profileId") or "") or new_id("li")
        item = {
            **profile_key(run_id, profile_id),
            "entityType": "FinderProfile",
            "runId": run_id,
            "profileId": profile_id,
            "createdAt": now_iso(),
            **p,
        }
        get_main_table().put_item(item=item)
        n += 1
    return n


def list_profiles(run_id: str, limit: int = 200) -> list[dict[str, Any]]:
    lim = max(1, min(500, int(limit or 200)))
    t = get_main_table()
    pg = t.query_page(
        key_condition_expression=Key("pk").eq(f"FINDER#RUN#{run_id}")
        & Key("sk").begins_with("FINDER#PROFILE#"),
        scan_index_forward=True,
        limit=lim,
        next_token=None,
    )
    return pg.items


def normalize_storage_state(storage_state: Any) -> dict[str, Any]:
    if storage_state is None:
        raise ValueError("storageState is required")
    if isinstance(storage_state, str):
        raw = storage_state.strip()
        if not raw:
            raise ValueError("storageState is required")
        return json.loads(raw)
    if isinstance(storage_state, dict):
        return storage_state
    return json.loads(json.dumps(storage_state))



