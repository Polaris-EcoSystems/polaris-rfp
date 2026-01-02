from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.settings import settings
from app.repositories import integrations_canva_repo as canva_repo
from app.infrastructure.token_crypto import decrypt_string, encrypt_string

CANVA_API_BASE = "https://api.canva.com/rest"
CANVA_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"


def _required_env(name: str) -> str:
    v = getattr(settings, name, None)
    if v:
        return str(v)
    raise RuntimeError(f"{name} is not configured")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def generate_pkce_pair() -> tuple[str, str]:
    # RFC 7636: code_verifier (43-128 chars) + base64url(SHA256(verifier))
    verifier = base64.urlsafe_b64encode(hashlib.sha256(str(time.time_ns()).encode()).digest()).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorize_url(*, state: str, scopes: list[str], code_challenge: str | None = None) -> str:
    client_id = _required_env("canva_client_id")
    redirect_uri = _required_env("canva_redirect_uri")

    url = httpx.URL(CANVA_AUTH_URL)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }

    if scopes:
        params["scope"] = " ".join([str(s) for s in scopes if str(s).strip()])

    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    return str(url.copy_with(params=params))


def exchange_code_for_token(*, code: str, code_verifier: str | None = None) -> dict[str, Any]:
    client_id = _required_env("canva_client_id")
    client_secret = _required_env("canva_client_secret")
    redirect_uri = _required_env("canva_redirect_uri")

    body = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if code_verifier:
        body["code_verifier"] = code_verifier

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            CANVA_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


def refresh_access_token(*, refresh_token: str) -> dict[str, Any]:
    client_id = _required_env("canva_client_id")
    client_secret = _required_env("canva_client_secret")

    body = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            CANVA_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


def upsert_connection_for_user(user_id: str, token_payload: dict[str, Any]) -> dict[str, Any]:
    access_token = token_payload.get("access_token")
    refresh_token = token_payload.get("refresh_token")
    token_type = token_payload.get("token_type") or "bearer"

    scopes_raw = token_payload.get("scope") or token_payload.get("scopes") or ""
    scopes: list[str]
    if isinstance(scopes_raw, str):
        scopes = [s.strip() for s in scopes_raw.split() if s.strip()]
    elif isinstance(scopes_raw, list):
        scopes = [str(s).strip() for s in scopes_raw if str(s).strip()]
    else:
        scopes = []

    expires_in = int(token_payload.get("expires_in") or 0)
    expires_at = (
        (_now_utc() + timedelta(seconds=expires_in)).isoformat().replace("+00:00", "Z")
        if expires_in
        else None
    )

    return canva_repo.upsert_connection_for_user(
        user_id,
        {
            "accessTokenEnc": encrypt_string(access_token) if access_token else None,
            "refreshTokenEnc": encrypt_string(refresh_token) if refresh_token else None,
            "tokenType": token_type,
            "scopes": scopes,
            "expiresAt": expires_at,
        },
    )


def get_valid_access_token_for_user(user_id: str) -> tuple[str, dict[str, Any]]:
    conn = canva_repo.get_connection_for_user(user_id)
    if not conn:
        raise RuntimeError("Canva is not connected for this user")

    access_token = decrypt_string(conn.get("accessTokenEnc"))
    refresh_token = decrypt_string(conn.get("refreshTokenEnc"))

    now = _now_utc()
    expires_at_ms = 0
    if conn.get("expiresAt"):
        try:
            expires_at_ms = int(
                datetime.fromisoformat(str(conn["expiresAt"]).replace("Z", "+00:00")).timestamp() * 1000
            )
        except Exception:
            expires_at_ms = 0

    needs_refresh = (not access_token) or (
        expires_at_ms and expires_at_ms - int(now.timestamp() * 1000) < 60 * 1000
    )

    if not needs_refresh:
        return str(access_token), conn

    if not refresh_token:
        raise RuntimeError("Canva token expired and no refresh token available")

    refreshed = refresh_access_token(refresh_token=str(refresh_token))

    updated = upsert_connection_for_user(
        user_id,
        {
            **refreshed,
            "refresh_token": refreshed.get("refresh_token") or str(refresh_token),
        },
    )

    next_access = decrypt_string(updated.get("accessTokenEnc"))
    if not next_access:
        raise RuntimeError("Failed to refresh Canva token")

    return str(next_access), updated


def canva_request(
    user_id: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
    response_type: str = "json",
) -> Any:
    access_token, _ = get_valid_access_token_for_user(user_id)
    url = f"{CANVA_API_BASE}{path}"

    with httpx.Client(timeout=60) as client:
        resp = client.request(
            method.upper(),
            url,
            params=params,
            json=data if data is not None else None,
            headers={"Authorization": f"Bearer {access_token}", **(headers or {})},
        )

    if response_type == "raw":
        resp.raise_for_status()
        return resp.content

    resp.raise_for_status()
    return resp.json()


def list_brand_templates(user_id: str, query: str = "") -> dict[str, Any]:
    return canva_request(
        user_id,
        "GET",
        "/v1/brand-templates",
        params={"query": query} if query else None,
    )


def get_brand_template_dataset(user_id: str, brand_template_id: str) -> dict[str, Any]:
    import urllib.parse

    safe = urllib.parse.quote(str(brand_template_id), safe="")
    return canva_request(user_id, "GET", f"/v1/brand-templates/{safe}/dataset")


def create_autofill_job(
    user_id: str, *, brand_template_id: str, title: str | None, data: dict[str, Any]
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "brand_template_id": brand_template_id,
        "data": data,
    }
    if title:
        payload["title"] = title
    return canva_request(user_id, "POST", "/v1/autofills", data=payload)


def get_autofill_job(user_id: str, job_id: str) -> dict[str, Any]:
    return canva_request(user_id, "GET", f"/v1/autofills/{job_id}")


def create_export_job(user_id: str, *, design_id: str, format: str = "pdf") -> dict[str, Any]:
    return canva_request(user_id, "POST", "/v1/exports", data={"design_id": design_id, "format": format})


def get_export_job(user_id: str, export_id: str) -> dict[str, Any]:
    return canva_request(user_id, "GET", f"/v1/exports/{export_id}")


def create_url_asset_upload_job(user_id: str, *, name: str, url: str) -> dict[str, Any]:
    return canva_request(user_id, "POST", "/v1/url-asset-uploads", data={"name": name, "url": url})


def get_url_asset_upload_job(user_id: str, job_id: str) -> dict[str, Any]:
    return canva_request(user_id, "GET", f"/v1/url-asset-uploads/{job_id}")


def create_asset_upload_job(user_id: str, *, name: str, bytes_data: bytes) -> dict[str, Any]:
    access_token, _ = get_valid_access_token_for_user(user_id)
    name_b64 = base64.b64encode(str(name or "Asset").encode("utf-8")).decode("ascii")

    url = f"{CANVA_API_BASE}/v1/asset-uploads"
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            url,
            content=bytes_data,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/octet-stream",
                "Asset-Upload-Metadata": json.dumps({"name_base64": name_b64}),
            },
        )
        resp.raise_for_status()
        return resp.json()


def get_asset_upload_job(user_id: str, job_id: str) -> dict[str, Any]:
    return canva_request(user_id, "GET", f"/v1/asset-uploads/{job_id}")


def download_url(url: str) -> tuple[bytes, str]:
    with httpx.Client(timeout=120) as client:
        resp = client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type") or "application/octet-stream"
        return resp.content, content_type


def poll_job(fn, *, interval_ms: int = 1500, timeout_ms: int = 90000) -> dict[str, Any]:
    start = time.time()
    while True:
        res = fn()
        status = ((res or {}).get("job") or {}).get("status")
        if status and status != "in_progress":
            return res
        if (time.time() - start) * 1000 > timeout_ms:
            raise RuntimeError("Timed out waiting for Canva job to complete")
        time.sleep(interval_ms / 1000.0)



