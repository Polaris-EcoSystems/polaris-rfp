from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...repositories.contracting.contracting_repo import get_esign_envelope, update_esign_envelope


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def send_envelope(*, case_id: str, envelope_id: str) -> dict[str, Any] | None:
    """
    Provider-agnostic send action.
    For now, only supports the 'stub' provider.
    """
    env = get_esign_envelope(case_id, envelope_id)
    if not env:
        return None
    provider = str(env.get("provider") or "stub").strip().lower() or "stub"
    if provider != "stub":
        raise RuntimeError(f"Unsupported e-sign provider: {provider}")
    now = _now_iso()
    return update_esign_envelope(
        case_id,
        envelope_id,
        {
            "status": "sent",
            "sentAt": now,
            "providerMeta": {**(env.get("providerMeta") or {}), "sentVia": "stub"},
        },
    )


def mark_signed(*, case_id: str, envelope_id: str) -> dict[str, Any] | None:
    """
    Stub-only: simulate completion.
    """
    env = get_esign_envelope(case_id, envelope_id)
    if not env:
        return None
    provider = str(env.get("provider") or "stub").strip().lower() or "stub"
    if provider != "stub":
        raise RuntimeError(f"Unsupported e-sign provider: {provider}")
    now = _now_iso()
    return update_esign_envelope(
        case_id,
        envelope_id,
        {
            "status": "signed",
            "completedAt": now,
            "providerMeta": {**(env.get("providerMeta") or {}), "completedVia": "stub"},
        },
    )

