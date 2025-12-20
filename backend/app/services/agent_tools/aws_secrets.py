from __future__ import annotations

from typing import Any

from ...settings import settings
from .allowlist import parse_csv, uniq
from .aws_clients import secretsmanager_client


def _allowed_secret_ids() -> list[str]:
    """
    Allowlist for secrets metadata inspection. This does NOT allow reading SecretString.
    """
    explicit = uniq(parse_csv(settings.agent_allowed_secrets_arns))
    if explicit:
        return explicit
    # Derive from known config.
    cands = [
        str(settings.slack_secret_arn or "").strip(),
        str(settings.github_secret_arn or "").strip(),
    ]
    return uniq([x for x in cands if x])


def _require_allowed(secret_id: str) -> str:
    sid = str(secret_id or "").strip()
    if not sid:
        raise ValueError("missing_secretId")
    allowed = _allowed_secret_ids()
    if allowed and sid not in allowed:
        raise ValueError("secret_not_allowed")
    return sid


def describe_secret(*, secret_id: str) -> dict[str, Any]:
    sid = _require_allowed(secret_id)
    resp = secretsmanager_client().describe_secret(SecretId=sid)
    if not isinstance(resp, dict):
        return {"ok": False, "error": "invalid_response"}
    # Strip potentially large fields and anything resembling secret material.
    keep = [
        "ARN",
        "Name",
        "Description",
        "KmsKeyId",
        "RotationEnabled",
        "RotationLambdaARN",
        "RotationRules",
        "LastChangedDate",
        "LastRotatedDate",
        "LastAccessedDate",
        "DeletedDate",
        "Tags",
    ]
    out: dict[str, Any] = {}
    for k in keep:
        if k in resp:
            out[k] = resp.get(k)
    return {"ok": True, "secretId": sid, "secret": out}

