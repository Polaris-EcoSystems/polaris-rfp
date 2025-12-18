from __future__ import annotations

import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
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


# Signed URL cache for headshots
_HEADSHOT_GET_CACHE: TTLCache[str, str] = TTLCache(maxsize=2048, ttl=55 * 60)


def get_cached_headshot_url(key: str) -> str | None:
    return _HEADSHOT_GET_CACHE.get(key)


def set_cached_headshot_url(key: str, url: str) -> None:
    _HEADSHOT_GET_CACHE[key] = url
