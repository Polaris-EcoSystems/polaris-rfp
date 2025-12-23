from __future__ import annotations

import json
from functools import lru_cache

import boto3

from ....settings import settings


@lru_cache(maxsize=1)
def _sqs():
    return boto3.client("sqs", region_name=settings.aws_region)


def enqueue_contracting_job(*, job_id: str) -> None:
    """
    Enqueue a contracting job id onto SQS for worker processing.
    """
    qurl = str(getattr(settings, "contracting_jobs_queue_url", "") or "").strip()
    if not qurl:
        raise RuntimeError("CONTRACTING_JOBS_QUEUE_URL is not set")
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id is required")
    body = json.dumps({"jobId": jid}, separators=(",", ":"))
    _sqs().send_message(QueueUrl=qurl, MessageBody=body)

