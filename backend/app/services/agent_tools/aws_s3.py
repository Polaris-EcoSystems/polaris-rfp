from __future__ import annotations

from typing import Any

from ...settings import settings
from .. import s3_assets
from .allowlist import is_allowed_prefix, parse_csv, uniq


def _allowed_prefixes() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_s3_prefixes))
    if explicit:
        return explicit
    return ["rfp/", "team/", "contracting/"]


def _require_allowed_key(key: str) -> str:
    k = str(key or "").strip()
    if not k:
        raise ValueError("missing_key")
    allowed = _allowed_prefixes()
    if allowed and not is_allowed_prefix(k, allowed):
        raise ValueError("s3_key_not_allowed")
    return k


def copy_object(*, source_key: str, dest_key: str) -> dict[str, Any]:
    src = _require_allowed_key(source_key)
    dst = _require_allowed_key(dest_key)
    s3_assets.copy_object(source_key=src, dest_key=dst)
    return {"ok": True, "sourceKey": src, "destKey": dst}


def delete_object(*, key: str) -> dict[str, Any]:
    k = _require_allowed_key(key)
    s3_assets.delete_object(key=k)
    return {"ok": True, "deletedKey": k}


def move_object(*, source_key: str, dest_key: str) -> dict[str, Any]:
    src = _require_allowed_key(source_key)
    dst = _require_allowed_key(dest_key)
    s3_assets.move_object(source_key=src, dest_key=dst)
    return {"ok": True, "sourceKey": src, "destKey": dst}

