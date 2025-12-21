"""
Worker for external context aggregation job.

Runs as a scheduled ECS task to aggregate and report on external context sources.
"""

from __future__ import annotations

from ..observability.logging import configure_logging, get_logger
from ..services.external_context_aggregator_scheduler import run_external_context_aggregation_and_reschedule

log = get_logger("external_context_aggregator_worker")


def main() -> None:
    """Main entry point for the external context aggregator worker."""
    configure_logging(level="INFO")
    
    log.info("external_context_aggregator_worker_started")
    
    try:
        result = run_external_context_aggregation_and_reschedule(
            hours=4,
            reschedule_hours=4,
            report_to_slack=True,
        )
        
        if result.get("ok"):
            log.info(
                "external_context_aggregator_worker_completed",
                next_run=result.get("nextRun"),
            )
        else:
            log.error(
                "external_context_aggregator_worker_failed",
                error=result.get("error"),
            )
    except Exception as e:
        log.error("external_context_aggregator_worker_exception", error=str(e), exc_info=True)
        raise


if __name__ == "__main__":
    main()
