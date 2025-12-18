from __future__ import annotations

import base64
import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..settings import settings


def _get_key() -> bytes:
    raw = (
        settings.canva_token_enc_key
        or settings.jwt_secret
        or "your-secret-key"
    )
    return hashlib.sha256(str(raw).encode("utf-8")).digest()  # 32 bytes


def encrypt_string(plain_text: Any) -> str | None:
    if plain_text is None:
        return None

    text = str(plain_text)
    key = _get_key()
    iv = os.urandom(12)  # 12 bytes for GCM

    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(iv, text.encode("utf-8"), None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    return ":".join(
        [
            "v1",
            base64.b64encode(iv).decode("ascii"),
            base64.b64encode(tag).decode("ascii"),
            base64.b64encode(ciphertext).decode("ascii"),
        ]
    )


def decrypt_string(cipher_text: Any) -> str | None:
    if not cipher_text:
        return None

    raw = str(cipher_text)
    parts = raw.split(":")
    if len(parts) != 4 or parts[0] != "v1":
        return None

    _, iv_b64, tag_b64, data_b64 = parts

    try:
        iv = base64.b64decode(iv_b64)
        tag = base64.b64decode(tag_b64)
        data = base64.b64decode(data_b64)
        if len(iv) != 12 or len(tag) != 16:
            return None

        key = _get_key()
        aesgcm = AESGCM(key)
        pt = aesgcm.decrypt(iv, data + tag, None)
        return pt.decode("utf-8")
    except Exception:
        return None
