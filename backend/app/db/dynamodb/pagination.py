from __future__ import annotations

import json
from typing import Any

from ...services.token_crypto import decrypt_string, encrypt_string
from .errors import DdbValidation


_TOKEN_VERSION = 1


def encode_next_token(last_evaluated_key: dict[str, Any] | None) -> str | None:
    if not last_evaluated_key:
        return None

    payload = {"v": _TOKEN_VERSION, "lek": last_evaluated_key}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    tok = encrypt_string(raw)
    return tok


def decode_next_token(next_token: str | None) -> dict[str, Any] | None:
    if not next_token:
        return None

    raw = decrypt_string(next_token)
    if not raw:
        raise DdbValidation(message="Invalid nextToken")

    try:
        payload = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        raise DdbValidation(message="Invalid nextToken") from e

    if not isinstance(payload, dict):
        raise DdbValidation(message="Invalid nextToken")

    if payload.get("v") != _TOKEN_VERSION:
        raise DdbValidation(message="Invalid nextToken")

    lek = payload.get("lek")
    if lek is None:
        return None
    if not isinstance(lek, dict):
        raise DdbValidation(message="Invalid nextToken")

    return lek

