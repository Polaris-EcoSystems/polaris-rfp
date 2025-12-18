from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from .ddb import delete_item, get_item, put_item


@dataclass
class PasswordResetToken:
    token: str
    email: str
    expires_at: int


def _pk(token: str) -> str:
    return f"passwordReset#{token}"


def create_password_reset(email: str, ttl_seconds: int = 30 * 60) -> PasswordResetToken:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + ttl_seconds

    put_item(
        {
            "pk": _pk(token),
            "sk": "v1",
            "type": "password_reset",
            "email": email,
            "expiresAt": expires_at,
        }
    )

    return PasswordResetToken(token=token, email=email, expires_at=expires_at)


def consume_password_reset(token: str) -> PasswordResetToken | None:
    item = get_item(_pk(token), "v1")
    if not item:
        return None

    expires_at = int(item.get("expiresAt") or 0)
    if expires_at and expires_at < int(time.time()):
        # expired
        delete_item(_pk(token), "v1")
        return None

    email = str(item.get("email") or "").strip()
    if not email:
        delete_item(_pk(token), "v1")
        return None

    # one-time
    delete_item(_pk(token), "v1")
    return PasswordResetToken(token=token, email=email, expires_at=expires_at)
