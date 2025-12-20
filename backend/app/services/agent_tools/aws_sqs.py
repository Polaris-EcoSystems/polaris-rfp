from __future__ import annotations

from typing import Any

from ...settings import settings
from .allowlist import parse_csv, uniq
from .aws_clients import sqs_client


def _allowed_queue_urls() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_sqs_queue_urls))
    if explicit:
        return explicit
    # Derive from core config.
    return uniq([str(settings.contracting_jobs_queue_url or "").strip()])


def _require_allowed_queue(queue_url: str) -> str:
    q = str(queue_url or "").strip()
    if not q:
        raise ValueError("missing_queueUrl")
    allowed = [x for x in _allowed_queue_urls() if x]
    if allowed and q not in allowed:
        raise ValueError("queue_not_allowed")
    return q


def get_queue_depth(*, queue_url: str) -> dict[str, Any]:
    q = _require_allowed_queue(queue_url)
    resp = sqs_client().get_queue_attributes(
        QueueUrl=q,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
            "ApproximateNumberOfMessagesDelayed",
            "CreatedTimestamp",
            "LastModifiedTimestamp",
            "VisibilityTimeout",
            "RedrivePolicy",
        ],
    )
    attrs = resp.get("Attributes") if isinstance(resp, dict) else None
    a = attrs if isinstance(attrs, dict) else {}
    # Coerce numeric strings where useful.
    def _int(v: Any) -> int | None:
        try:
            return int(v)
        except Exception:
            return None

    return {
        "ok": True,
        "queueUrl": q,
        "approximate": {
            "visible": _int(a.get("ApproximateNumberOfMessages")),
            "notVisible": _int(a.get("ApproximateNumberOfMessagesNotVisible")),
            "delayed": _int(a.get("ApproximateNumberOfMessagesDelayed")),
        },
        "visibilityTimeoutSeconds": _int(a.get("VisibilityTimeout")),
        "redrivePolicy": a.get("RedrivePolicy"),
        "createdTimestamp": _int(a.get("CreatedTimestamp")),
        "lastModifiedTimestamp": _int(a.get("LastModifiedTimestamp")),
    }


def get_queue_attributes(*, queue_url: str, attributes: list[str] | None = None) -> dict[str, Any]:
    q = _require_allowed_queue(queue_url)
    names = attributes if isinstance(attributes, list) and attributes else ["All"]
    names = [str(x).strip() for x in names if str(x).strip()][:25]
    if not names:
        names = ["All"]
    resp = sqs_client().get_queue_attributes(QueueUrl=q, AttributeNames=names)
    attrs = resp.get("Attributes") if isinstance(resp, dict) else None
    a = attrs if isinstance(attrs, dict) else {}
    # Bound output: keep up to 60 keys.
    out: dict[str, Any] = {}
    for k in list(a.keys())[:60]:
        out[str(k)] = a.get(k)
    return {"ok": True, "queueUrl": q, "attributes": out}


def redrive_dlq(*, source_queue_url: str, destination_queue_url: str, max_per_second: int | None = None) -> dict[str, Any]:
    """
    Start a message move task from a DLQ to a source queue.
    Uses SQS StartMessageMoveTask (approval-gated by caller).
    """
    src_q = _require_allowed_queue(source_queue_url)
    dst_q = _require_allowed_queue(destination_queue_url)
    # Look up ARNs
    src_attrs = sqs_client().get_queue_attributes(QueueUrl=src_q, AttributeNames=["QueueArn"]).get("Attributes") or {}
    dst_attrs = sqs_client().get_queue_attributes(QueueUrl=dst_q, AttributeNames=["QueueArn"]).get("Attributes") or {}
    src_arn = str((src_attrs or {}).get("QueueArn") or "").strip()
    dst_arn = str((dst_attrs or {}).get("QueueArn") or "").strip()
    if not src_arn or not dst_arn:
        return {"ok": False, "error": "missing_queue_arn"}
    kwargs: dict[str, Any] = {"SourceArn": src_arn, "DestinationArn": dst_arn}
    if max_per_second is not None:
        mps = int(max_per_second)
        if mps < 1 or mps > 500:
            raise ValueError("maxPerSecond_out_of_range")
        kwargs["MaxNumberOfMessagesPerSecond"] = mps
    resp = sqs_client().start_message_move_task(**kwargs)
    return {"ok": True, "sourceArn": src_arn, "destinationArn": dst_arn, "task": resp}

