from __future__ import annotations

from typing import Any

import boto3

from ..settings import settings


def _sesv2_client():
    return boto3.client("sesv2", region_name=settings.aws_region)


def send_text_email(*, to_email: str, from_email: str, subject: str, text: str) -> dict[str, Any]:
    to_ = str(to_email or "").strip()
    frm = str(from_email or "").strip()
    subj = str(subject or "").strip()[:200] or "Polaris daily digest"
    body = str(text or "").strip()
    if not to_ or not frm:
        return {"ok": False, "error": "missing_to_or_from"}
    if not body:
        body = "(empty)"
    resp = _sesv2_client().send_email(
        FromEmailAddress=frm,
        Destination={"ToAddresses": [to_]},
        Content={
            "Simple": {
                "Subject": {"Data": subj},
                "Body": {"Text": {"Data": body}},
            }
        },
    )
    msg_id = (resp or {}).get("MessageId") if isinstance(resp, dict) else None
    return {"ok": True, "messageId": msg_id}

