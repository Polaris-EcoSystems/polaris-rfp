from __future__ import annotations

import json
from typing import Any

from .aws_clients import secretsmanager_client
from ..observability.logging import get_logger

log = get_logger("google_drive_integration")

service_account: Any
build: Any

try:  # pragma: no cover
    from google.oauth2 import service_account as _service_account
    from googleapiclient.discovery import build as _build

    service_account = _service_account
    build = _build
except Exception:  # pragma: no cover
    service_account = None
    build = None


def _require_google_deps() -> None:
    if service_account is None or build is None:
        raise RuntimeError(
            "Google Drive dependencies are not installed (missing google-auth/google-api-python-client)."
        )


def _get_google_credentials(*, use_api_key: bool = False) -> Any:
    """
    Minimal credential loader. In production, secrets should be configurable; for now we keep existing ARNs.
    """
    _require_google_deps()
    if use_api_key:
        secret_arn = "arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_API_KEY-yPu460"
    else:
        secret_arn = "arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_CREDENTIALS-lqF0A9"
    sm = secretsmanager_client()
    resp = sm.get_secret_value(SecretId=secret_arn)
    secret_string = resp.get("SecretString")
    if not secret_string:
        raise RuntimeError("missing_google_secret_value")
    if use_api_key:
        return str(secret_string).strip()
    creds_dict = json.loads(secret_string)
    scopes = ["https://www.googleapis.com/auth/drive"]
    return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)


def upload_file_to_drive(
    *,
    name: str,
    content: str,
    mime_type: str,
    folder_id: str | None = None,
) -> dict[str, Any]:
    """
    Minimal upload helper used by the frontend-required `POST /googledrive/upload-proposal/{proposalId}`.
    """
    nm = str(name or "").strip()
    if not nm:
        return {"ok": False, "error": "missing_name"}
    _require_google_deps()

    try:
        from googleapiclient.http import MediaInMemoryUpload
    except Exception as e:
        return {"ok": False, "error": f"missing_googleapiclient_http:{str(e) or 'import_failed'}"}

    creds = _get_google_credentials(use_api_key=False)
    svc = build("drive", "v3", credentials=creds)

    file_metadata: dict[str, Any] = {"name": nm}
    fid = str(folder_id or "").strip()
    if fid:
        file_metadata["parents"] = [fid]

    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=str(mime_type or "application/octet-stream"))
    created = (
        svc.files()
        .create(body=file_metadata, media_body=media, fields="id,name,webViewLink")
        .execute()
    )
    return {"ok": True, "fileId": created.get("id"), "name": created.get("name"), "webViewLink": created.get("webViewLink")}


