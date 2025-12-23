from __future__ import annotations

from typing import Any

from ....settings import settings
from ....infrastructure.storage import s3_assets
from ...registry.allowlist import is_allowed_prefix, parse_csv, uniq


def _allowed_prefixes() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_s3_prefixes))
    if explicit:
        return explicit
    # Default allowlist (keep narrow; expand via env var if needed).
    # - rfp/: uploaded PDFs + derived artifacts
    # - team/: headshots/assets
    # - contracting/: contracting artifacts
    # - agent/: agent skills + agent-generated artifacts (trace, screenshots, etc.)
    return ["rfp/", "team/", "contracting/", "agent/"]


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


def head_object(*, key: str) -> dict[str, Any]:
    k = _require_allowed_key(key)
    meta = s3_assets.head_object(key=k)
    # Return only metadata (no body)
    out = {
        "ContentLength": meta.get("ContentLength"),
        "ContentType": meta.get("ContentType"),
        "ETag": meta.get("ETag"),
        "LastModified": str(meta.get("LastModified") or ""),
        "Metadata": meta.get("Metadata") if isinstance(meta.get("Metadata"), dict) else {},
    }
    return {"ok": True, "key": k, "head": out}


def presign_put_object(*, key: str, content_type: str | None = None, expires_in: int = 900) -> dict[str, Any]:
    k = _require_allowed_key(key)
    ct = str(content_type or "").strip() or None
    exp = max(60, min(3600, int(expires_in or 900)))
    return {"ok": True, **s3_assets.presign_put_object(key=k, content_type=ct, expires_in=exp)}

