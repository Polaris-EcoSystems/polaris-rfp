"""
Helper functions for long-running jobs with token budget support.
"""

from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger
from ..settings import settings
from .token_budget_tracker import TokenBudgetTracker

log = get_logger("long_running_job_helpers")


LONG_RUNNING_JOB_TYPES: set[str] = {
    "ai_agent_execute",
    "ai_agent_analyze_rfps",
    "ai_agent_solve_problem",
    "ai_agent_monitor_conditions",
    "ai_agent_maintain_data",
}


def is_long_running_job(job_type: str) -> bool:
    """Check if a job type is a long-running job that should use token budgets."""
    return job_type in LONG_RUNNING_JOB_TYPES


def initialize_token_budget_for_job(
    *,
    payload: dict[str, Any],
    checkpoint_data: dict[str, Any] | None = None,
    model: str | None = None,
) -> TokenBudgetTracker | None:
    """
    Initialize or restore token budget tracker for a long-running job.
    
    Uses default of 15 minutes, scaled proportionally (4 hours = $10 budget).
    
    Args:
        payload: Job payload (may contain timeBudgetMinutes or costBudgetUsd)
        checkpoint_data: Checkpoint data to restore from (optional)
        model: Model name (default: from settings)
    
    Returns:
        TokenBudgetTracker instance, or None if not a long-running job
    """
    # Restore from checkpoint if available
    if checkpoint_data and "token_budget" in checkpoint_data:
        try:
            tracker = TokenBudgetTracker.from_dict(checkpoint_data["token_budget"])
            log.info("token_budget_restored_from_checkpoint", budget_tokens=tracker.budget_tokens, remaining=tracker.remaining_tokens())
            return tracker
        except Exception as e:
            log.warning("token_budget_restore_failed", error=str(e))
    
    # Initialize new tracker
    time_budget_minutes = payload.get("timeBudgetMinutes")
    cost_budget_usd = payload.get("costBudgetUsd")
    model_name = model or settings.openai_model or "gpt-5.2"
    
    tracker = TokenBudgetTracker.from_time_budget(
        minutes=float(time_budget_minutes) if time_budget_minutes is not None else None,
        cost_budget_usd=float(cost_budget_usd) if cost_budget_usd is not None else None,
        model=model_name,
        default_minutes=15.0,  # Default: 15 minutes (scaled: 4 hours = $10)
    )
    
    log.info(
        "token_budget_initialized",
        budget_tokens=tracker.budget_tokens,
        model=model_name,
        time_budget_minutes=time_budget_minutes,
        cost_budget_usd=cost_budget_usd,
    )
    
    return tracker
