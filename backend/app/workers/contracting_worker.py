from __future__ import annotations

import json
import time
from typing import Any

import boto3

from ..observability.logging import configure_logging, get_logger
from ..pipeline.contracting.contracting_docgen import generate_budget_xlsx, render_contract_docx
from ..repositories.contracting_jobs_repo import (
    complete_job,
    fail_job,
    get_job,
    try_mark_running,
    update_progress,
)
from ..repositories.contracting_repo import get_client_package
from ..infrastructure.storage.s3_assets import get_object_bytes, put_object_bytes
from ..settings import settings


log = get_logger("contracting_worker")


def _sqs():
    return boto3.client("sqs", region_name=settings.aws_region)


def _queue_url() -> str:
    q = str(settings.contracting_jobs_queue_url or "").strip()
    if not q:
        raise RuntimeError("CONTRACTING_JOBS_QUEUE_URL is not set")
    return q


def _receive_count(msg: dict[str, Any]) -> int:
    try:
        attrs = msg.get("Attributes") or {}
        n = int(attrs.get("ApproximateReceiveCount") or 0)
        return n
    except Exception:
        return 0


def _process_job(job_id: str, *, receive_count: int) -> None:
    job = get_job(job_id) or {}
    if not job:
        # Nothing to do; message may be stale.
        return

    # Only one worker should process.
    running = try_mark_running(job_id=job_id)
    if not running:
        return

    raw_payload = job.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    job_type = str(job.get("jobType") or "").strip()
    case_id = str(payload.get("caseId") or job.get("caseId") or "").strip()
    if not case_id:
        fail_job(job_id=job_id, error="Missing caseId")
        return

    try:
        if job_type == "contract_generate":
            update_progress(job_id=job_id, pct=15, step="contract", message="Rendering contract")
            template_id = str(payload.get("templateId") or "").strip()
            template_version_id = str(payload.get("templateVersionId") or "").strip() or None
            render_inputs = payload.get("renderInputs") if isinstance(payload.get("renderInputs"), dict) else {}
            if not template_id:
                raise RuntimeError("Missing templateId")
            out = render_contract_docx(
                case_id=case_id,
                template_id=template_id,
                template_version_id=template_version_id,
                render_inputs=render_inputs,
                created_by_user_sub=str(job.get("requestedByUserSub") or "").strip() or None,
            )
            update_progress(job_id=job_id, pct=95, step="finalize", message="Finalizing")
            complete_job(job_id=job_id, result={"contract": out.get("version")})
            log.info("contracting_job_completed", jobId=job_id, jobType=job_type, caseId=case_id)
            return

        if job_type == "budget_generate":
            update_progress(job_id=job_id, pct=15, step="budget", message="Generating budget workbook")
            budget_model = payload.get("budgetModel") if isinstance(payload.get("budgetModel"), dict) else {}
            out = generate_budget_xlsx(
                case_id=case_id,
                budget_model=budget_model,
                created_by_user_sub=str(job.get("requestedByUserSub") or "").strip() or None,
            )
            update_progress(job_id=job_id, pct=95, step="finalize", message="Finalizing")
            complete_job(job_id=job_id, result={"budget": out.get("version"), "total": out.get("total")})
            log.info("contracting_job_completed", jobId=job_id, jobType=job_type, caseId=case_id)
            return

        if job_type == "package_zip":
            update_progress(job_id=job_id, pct=10, step="zip", message="Building zip bundle")
            package_id = str(payload.get("packageId") or "").strip()
            if not package_id:
                raise RuntimeError("Missing packageId")
            pkg = get_client_package(case_id=case_id, package_id=package_id) or {}
            files = pkg.get("selectedFiles") if isinstance(pkg.get("selectedFiles"), list) else []
            if not files:
                raise RuntimeError("Package has no selected files")

            import io
            import zipfile
            from datetime import datetime, timezone

            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out_key = f"contracting/{case_id}/packages/{package_id}/zips/{ts}.zip"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
                for idx, f in enumerate(files):
                    if not isinstance(f, dict):
                        continue
                    s3_key = str(f.get("s3Key") or "").strip()
                    if not s3_key:
                        continue
                    name = str(f.get("fileName") or f.get("label") or f.get("id") or f"file_{idx+1}").strip()
                    # Keep zip filenames safe.
                    safe = "".join([c if c.isalnum() or c in ("-", "_", ".", " ") else "_" for c in name])[:120]
                    if not safe:
                        safe = f"file_{idx+1}"
                    data = get_object_bytes(key=s3_key, max_bytes=25 * 1024 * 1024) or b""
                    if not data:
                        continue
                    z.writestr(safe, data)
                    if (idx + 1) % 2 == 0:
                        update_progress(job_id=job_id, pct=min(90, 10 + (idx + 1) * 10), step="zip", message=f"Added {idx+1} file(s)")

            zip_bytes = buf.getvalue() or b""
            if not zip_bytes:
                raise RuntimeError("Zip output was empty")

            put_object_bytes(key=out_key, data=zip_bytes, content_type="application/zip")
            update_progress(job_id=job_id, pct=95, step="finalize", message="Finalizing")
            complete_job(job_id=job_id, result={"zipS3Key": out_key, "fileCount": len(files)})
            log.info("contracting_job_completed", jobId=job_id, jobType=job_type, caseId=case_id)
            return

        # Unknown job types should fail.
        fail_job(job_id=job_id, error=f"Unknown jobType: {job_type or 'unknown'}")
    except Exception as e:
        # If SQS is configured with a DLQ redrive policy, we can rely on it.
        # Still write a failure status when we're at/over our max receive count.
        msg = (str(e) or "job_failed")[:800]
        max_recv = max(1, int(settings.contracting_jobs_max_receives or 6))
        if receive_count >= max_recv:
            try:
                fail_job(job_id=job_id, error=msg)
            except Exception:
                pass
        raise


def run_forever() -> None:
    configure_logging(level="INFO")
    qurl = _queue_url()
    sqs = _sqs()
    wait_s = max(1, min(20, int(settings.contracting_jobs_poll_wait_seconds or 10)))
    max_msgs = max(1, min(10, int(settings.contracting_jobs_poll_max_messages or 5)))

    log.info(
        "contracting_worker_starting",
        queue_url=qurl,
        wait_seconds=wait_s,
        max_messages=max_msgs,
    )

    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=qurl,
                MaxNumberOfMessages=max_msgs,
                WaitTimeSeconds=wait_s,
                AttributeNames=["ApproximateReceiveCount"],
            )
            msgs = resp.get("Messages") or []
            if not msgs:
                continue

            for m in msgs:
                receipt = m.get("ReceiptHandle")
                body = str(m.get("Body") or "")
                rc = _receive_count(m)
                try:
                    data = json.loads(body) if body else {}
                except Exception:
                    data = {}
                job_id = str((data or {}).get("jobId") or "").strip()
                if not job_id:
                    # Malformed; drop.
                    if receipt:
                        sqs.delete_message(QueueUrl=qurl, ReceiptHandle=receipt)
                    continue

                try:
                    _process_job(job_id, receive_count=rc)
                    if receipt:
                        sqs.delete_message(QueueUrl=qurl, ReceiptHandle=receipt)
                except Exception:
                    # Let visibility timeout + retries handle it.
                    log.exception("contracting_job_failed", jobId=job_id, receiveCount=rc)
                    continue
        except Exception:
            # Prevent tight crash loops.
            log.exception("contracting_worker_loop_error")
            time.sleep(2.0)


if __name__ == "__main__":
    run_forever()

