from __future__ import annotations

import re
import uuid
from functools import lru_cache
from typing import Any

import boto3
from cachetools import TTLCache

from ..settings import settings


def get_assets_bucket_name() -> str:
    name = (settings.assets_bucket_name or "").strip()
    if not name:
        raise RuntimeError("ASSETS_BUCKET_NAME is not set")
    return name


def _safe_member(member_id: str | None) -> str:
    safe = (member_id or "unassigned").strip() or "unassigned"
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", safe)[:80]
    return safe


def make_key(*, kind: str = "headshot", file_name: str = "", member_id: str | None = None) -> str:
    ext = ""
    raw = (file_name or "").strip()
    m = re.search(r"\.([a-zA-Z0-9]{1,10})$", raw)
    if m:
        ext = f".{m.group(1).lower()}"

    return f"team/{_safe_member(member_id)}/{kind}/{uuid.uuid4()}{ext}"


def make_rfp_upload_key(*, file_name: str = "") -> str:
    """
    Key namespace for uploaded RFP PDFs.
    """
    raw = (file_name or "").strip()
    ext = ".pdf"
    m = re.search(r"\.([a-zA-Z0-9]{1,10})$", raw)
    if m:
        got = f".{m.group(1).lower()}"
        if got == ".pdf":
            ext = got
    return f"rfp/uploads/{uuid.uuid4()}{ext}"


def make_rfp_upload_key_for_hash(*, sha256: str) -> str:
    """
    Deterministic key for an RFP PDF based on its SHA-256 (lowercase hex).

    This enables storage-level convergence and makes de-dupe robust across retries.
    """
    s = str(sha256 or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", s):
        raise ValueError("Invalid sha256")
    return f"rfp/uploads/sha256/{s}.pdf"


@lru_cache(maxsize=1)
def _s3_client():
    return boto3.client("s3", region_name=settings.aws_region)


def presign_put_object(*, key: str, content_type: str | None, expires_in: int = 900) -> dict[str, Any]:
    bucket = get_assets_bucket_name()
    params: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if content_type:
        params["ContentType"] = str(content_type)

    url = _s3_client().generate_presigned_url(
        ClientMethod="put_object",
        Params=params,
        ExpiresIn=max(60, min(3600, int(expires_in or 900))),
    )
    return {"bucket": bucket, "key": key, "url": url}


def presign_get_object(*, key: str, expires_in: int = 3600) -> dict[str, Any]:
    bucket = get_assets_bucket_name()
    url = _s3_client().generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=max(60, min(24 * 3600, int(expires_in or 3600))),
    )
    return {"bucket": bucket, "key": key, "url": url}


def to_s3_uri(*, bucket: str, key: str) -> str:
    b = (bucket or "").strip()
    k = (key or "").strip()
    if not b or not k:
        return ""
    return f"s3://{b}/{k}"


def copy_object(*, source_key: str, dest_key: str) -> None:
    bucket = get_assets_bucket_name()
    _s3_client().copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": source_key},
        Key=dest_key,
    )


def delete_object(*, key: str) -> None:
    bucket = get_assets_bucket_name()
    _s3_client().delete_object(Bucket=bucket, Key=key)


def move_object(*, source_key: str, dest_key: str) -> None:
    copy_object(source_key=source_key, dest_key=dest_key)
    delete_object(key=source_key)


def head_object(*, key: str) -> dict[str, Any]:
    bucket = get_assets_bucket_name()
    return _s3_client().head_object(Bucket=bucket, Key=str(key))


def get_object_bytes(*, key: str, max_bytes: int = 60 * 1024 * 1024) -> bytes:
    """
    Download an object into memory, with a safety max to prevent OOM.
    """
    bucket = get_assets_bucket_name()
    meta = head_object(key=str(key))
    size = int(meta.get("ContentLength") or 0)
    if size <= 0:
        return b""
    if size > int(max_bytes):
        raise RuntimeError(f"Object too large ({size} bytes), max is {int(max_bytes)} bytes")

    resp = _s3_client().get_object(Bucket=bucket, Key=str(key))
    body = resp.get("Body")
    if not body:
        return b""
    data = body.read()
    return data or b""


# Signed URL cache for headshots
_HEADSHOT_GET_CACHE: TTLCache[str, str] = TTLCache(maxsize=2048, ttl=55 * 60)


def get_cached_headshot_url(key: str) -> str | None:
    return _HEADSHOT_GET_CACHE.get(key)


def set_cached_headshot_url(key: str, url: str) -> None:
    _HEADSHOT_GET_CACHE[key] = url
