from __future__ import annotations

import json
from typing import Any

from ....settings import settings
from ...registry.allowlist import parse_csv, uniq
from ...registry.aws_clients import secretsmanager_client
from ...observability.logging import get_logger

log = get_logger("aws_secrets")


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


def get_secret_value(*, secret_id: str, parse_json: bool = True) -> dict[str, Any]:
    """
    Get secret value from Secrets Manager.
    
    Note: ECS task has permissions to access any secret, but we still check allowlist
    for safety. If allowlist is empty, all secrets are allowed.
    
    Args:
        secret_id: ARN or name of the secret
        parse_json: If True, attempt to parse SecretString as JSON
    
    Returns:
        Dict with 'ok', 'secretId', and either 'value' (string) or 'valueJson' (parsed JSON)
    """
    sid = str(secret_id or "").strip()
    if not sid:
        return {"ok": False, "error": "secret_id is required"}
    
    # Check allowlist if it's configured
    allowed = _allowed_secret_ids()
    if allowed and sid not in allowed:
        # If allowlist exists and secret is not in it, check if it's a known Google secret
        # This allows Google secrets to be accessed even if not explicitly in allowlist
        if "GOOGLE" in sid.upper() or "google" in sid.lower():
            log.info("allowing_google_secret", secret_id=sid)
        else:
            return {"ok": False, "error": f"secret_not_allowed: {sid}"}
    
    try:
        sm = secretsmanager_client()
        resp = sm.get_secret_value(SecretId=sid)
        
        if not isinstance(resp, dict):
            return {"ok": False, "error": "invalid_response"}
        
        secret_string = resp.get("SecretString")
        secret_binary = resp.get("SecretBinary")
        
        if secret_string:
            if parse_json:
                try:
                    value_json = json.loads(secret_string)
                    return {
                        "ok": True,
                        "secretId": sid,
                        "valueJson": value_json,
                        "value": secret_string,  # Also include raw string
                    }
                except json.JSONDecodeError:
                    # Not JSON, return as string
                    pass
            
            return {
                "ok": True,
                "secretId": sid,
                "value": secret_string,
            }
        elif secret_binary:
            return {
                "ok": True,
                "secretId": sid,
                "valueBinary": secret_binary,
            }
        else:
            return {"ok": False, "error": "no_secret_value"}
    
    except Exception as e:
        log.error("get_secret_value_failed", secret_id=sid, error=str(e))
        return {"ok": False, "error": str(e)}

