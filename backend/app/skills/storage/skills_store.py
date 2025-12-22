from __future__ import annotations

import json
from typing import Any

from . import s3_assets


def skill_body_key(*, skill_id: str, version: int) -> str:
    sid = str(skill_id or "").strip()
    if not sid:
        raise ValueError("skill_id is required")
    v = max(1, int(version or 1))
    # Keep under allowlisted prefix `agent/`
    return f"agent/skills/{sid}/v{v}.json"


def put_skill_body(
    *,
    skill_id: str,
    version: int,
    body: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist the skill body to S3 as JSON.

    This stores the "payload" that is only loaded when the agent chooses to use the skill.
    """
    key = skill_body_key(skill_id=skill_id, version=version)
    payload = body if isinstance(body, dict) else {}
    # Ensure stable minimal shape.
    payload = {
        **payload,
        "skillId": str(skill_id).strip(),
        "version": max(1, int(version or 1)),
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    resp = s3_assets.put_object_bytes(key=key, data=data, content_type="application/json")
    return {"ok": True, "key": key, "etag": str(resp.get("ETag") or "").strip() or None}


def get_skill_body_text(
    *,
    key: str,
    max_bytes: int = 2 * 1024 * 1024,
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """
    Load skill body (JSON) from S3 and return it as text (clipped).
    """
    return s3_assets.get_object_text(key=str(key), max_bytes=max_bytes, max_chars=max_chars)

