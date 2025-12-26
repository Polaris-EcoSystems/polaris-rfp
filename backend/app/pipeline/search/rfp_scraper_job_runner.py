from __future__ import annotations

from typing import Any

from ...observability.logging import get_logger
from ...repositories.rfp_scraper_jobs_repo import (
    get_job_item as get_scraper_job_item,
    update_job as update_scraper_job,
)
from ...repositories.rfp_scraped_rfps_repo import create_scraped_rfp_deduped
from .rfp_scrapers.scraper_registry import get_scraper, is_source_available
from ...repositories.rfp_scraped_rfps_repo import now_iso

log = get_logger("rfp_scraper_job_runner")


def process_scraper_job(job_id: str) -> None:
    """Execute a scraper job and persist candidates (with dedupe + intake queue)."""
    log.info("scraper_job_starting", jobId=job_id)
    job = get_scraper_job_item(job_id) or {}
    if not job:
        return
    if job.get("status") not in ("queued", "running"):
        return

    try:
        update_scraper_job(
            job_id=job_id,
            updates_obj={
                "status": "running",
                "startedAt": now_iso(),
            },
        )

        source = str(job.get("source") or "").strip()
        search_params = job.get("searchParams") or {}
        user_sub = str(job.get("userSub") or "").strip() or None

        if not source or not is_source_available(source):
            raise ValueError(f"Invalid or unavailable source: {source}")

        scraper = get_scraper(source, search_params=search_params, user_sub=user_sub)
        if not scraper:
            raise ValueError(f"Failed to create scraper for source: {source}")

        # Run the scraper
        with scraper:
            candidates = scraper.scrape(search_params=search_params)

        saved_count = 0
        deduped_count = 0
        for candidate in candidates:
            try:
                if isinstance(candidate, dict):
                    candidate_dict: dict[str, Any] = candidate
                else:
                    candidate_dict = candidate.to_dict()
                _cand, created = create_scraped_rfp_deduped(
                    source=source,
                    source_url=str(candidate_dict.get("sourceUrl") or ""),
                    title=str(candidate_dict.get("title") or "Untitled RFP"),
                    detail_url=str(candidate_dict.get("detailUrl") or ""),
                    metadata=candidate_dict.get("metadata"),
                )
                if created:
                    saved_count += 1
                else:
                    deduped_count += 1
            except Exception as e:
                log.warning("failed_to_save_candidate", candidate=str(candidate), error=str(e))

        update_scraper_job(
            job_id=job_id,
            updates_obj={
                "status": "completed",
                "candidatesFound": len(candidates),
                "candidatesImported": saved_count,
                "candidatesDeduped": deduped_count,
                "finishedAt": now_iso(),
            },
        )
        log.info(
            "scraper_job_completed",
            jobId=job_id,
            candidates_found=len(candidates),
            candidates_saved=saved_count,
            candidates_deduped=deduped_count,
        )
    except Exception as e:
        update_scraper_job(
            job_id=job_id,
            updates_obj={
                "status": "failed",
                "error": str(e) or "Failed to process scraper job",
                "finishedAt": now_iso(),
            },
        )
        log.exception("scraper_job_failed", jobId=job_id)


