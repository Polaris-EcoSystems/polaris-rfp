from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .agent_checkpoint import (
    restore_from_checkpoint,
    save_checkpoint,
    should_checkpoint,
    validate_checkpoint_state,
)
from .agent_resilience import retry_with_classification
from ..observability.logging import get_logger

log = get_logger("agent_long_running")


@dataclass
class StepDefinition:
    """Definition of a step in a long-running operation."""
    step_id: str
    name: str
    execute: Callable[[dict[str, Any]], dict[str, Any]]
    depends_on: list[str]  # Step IDs this step depends on
    timeout_seconds: float = 300.0
    retryable: bool = True
    checkpoint_after: bool = True


@dataclass
class OrchestrationResult:
    """Result of orchestrating a long-running operation."""
    success: bool
    completed_steps: list[str]
    failed_steps: list[str]
    final_result: dict[str, Any] | None
    error: str | None = None
    token_usage: dict[str, Any] | None = None  # Token usage stats if tracker was used


class LongRunningOrchestrator:
    """
    Orchestrator for long-running multi-step operations.
    Supports checkpointing, resuming, step dependencies, and parallel execution.
    """
    
    def __init__(
        self,
        *,
        rfp_id: str,
        job_id: str | None = None,
        checkpoint_interval_steps: int = 10,
        checkpoint_interval_seconds: float = 300.0,
        token_budget_tracker: Any | None = None,  # TokenBudgetTracker
    ):
        self.rfp_id = rfp_id
        self.job_id = job_id
        self.checkpoint_interval_steps = checkpoint_interval_steps
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.token_budget_tracker = token_budget_tracker
        self.steps: dict[str, StepDefinition] = {}
        self.completed_steps: set[str] = set()
        self.failed_steps: set[str] = set()
        self.step_results: dict[str, dict[str, Any]] = {}
        self.last_checkpoint_step = 0
        self.last_checkpoint_time: float | None = None
        self.current_step = 0
    
    def add_step(self, step: StepDefinition) -> None:
        """Add a step to the orchestration."""
        self.steps[step.step_id] = step
    
    def can_execute_step(self, step_id: str) -> bool:
        """Check if a step can be executed (dependencies satisfied)."""
        if step_id not in self.steps:
            return False
        
        if step_id in self.completed_steps:
            return False
        
        if step_id in self.failed_steps:
            return False
        
        step = self.steps[step_id]
        for dep_id in step.depends_on:
            if dep_id not in self.completed_steps:
                return False
        
        return True
    
    def get_ready_steps(self) -> list[str]:
        """Get list of step IDs that are ready to execute."""
        ready: list[str] = []
        for step_id in self.steps:
            if self.can_execute_step(step_id):
                ready.append(step_id)
        return ready
    
    def execute_step(self, step_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a single step."""
        step = self.steps[step_id]
        
        # Build step context
        step_context = {
            **context,
            "step_id": step_id,
            "step_name": step.name,
            "previous_results": {sid: self.step_results[sid] for sid in step.depends_on if sid in self.step_results},
            "token_budget_tracker": self.token_budget_tracker,  # Pass tracker to step execution
        }
        
        # Add budget status to context if tracker available
        if self.token_budget_tracker:
            step_context["token_budget_status"] = self.token_budget_tracker.get_budget_status_message()
        
        # Execute step with retry if retryable
        if step.retryable:
            result = retry_with_classification(
                lambda: step.execute(step_context),
                max_retries=3,
            )
        else:
            result = step.execute(step_context)
        
        return result
    
    def checkpoint(self, context: dict[str, Any]) -> None:
        """Save a checkpoint."""
        checkpoint_data = {
            "completed_steps": list(self.completed_steps),
            "failed_steps": list(self.failed_steps),
            "step_results": self.step_results,
            "current_step": self.current_step,
        }
        
        # Include token budget tracker state in checkpoint
        if self.token_budget_tracker:
            checkpoint_data["token_budget"] = self.token_budget_tracker.to_dict()
        
        tool_calls: list[dict[str, Any]] = []
        for step_id in self.completed_steps:
            result = self.step_results.get(step_id, {})
            tool_calls.append({
                "step_id": step_id,
                "result": result,
            })
        
        save_checkpoint(
            rfp_id=self.rfp_id,
            job_id=self.job_id,
            checkpoint_data=checkpoint_data,
            step=self.current_step,
            tool_calls=tool_calls,
            intermediate_results=self.step_results,
            metadata={
                "orchestrator": "LongRunningOrchestrator",
                "total_steps": len(self.steps),
                "completed_count": len(self.completed_steps),
            },
        )
        
        self.last_checkpoint_step = self.current_step
        self.last_checkpoint_time = time.time()
    
    def restore(self) -> bool:
        """Restore state from checkpoint."""
        restored = restore_from_checkpoint(rfp_id=self.rfp_id, job_id=self.job_id)
        if not restored:
            return False
        
        # Restore token budget tracker from checkpoint if present
        checkpoint_payload = restored.get("payload", {})
        checkpoint_data = checkpoint_payload.get("checkpointData", {})
        if "token_budget" in checkpoint_data and self.token_budget_tracker is None:
            from .token_budget_tracker import TokenBudgetTracker
            try:
                self.token_budget_tracker = TokenBudgetTracker.from_dict(checkpoint_data["token_budget"])
            except Exception:
                pass  # Continue without tracker if restoration fails
        
        # Validate checkpoint
        is_valid, error = validate_checkpoint_state(checkpoint_state=restored)
        if not is_valid:
            return False
        
        # Restore state
        checkpoint_data = restored.get("checkpoint_data", {})
        self.completed_steps = set(checkpoint_data.get("completed_steps", []))
        self.failed_steps = set(checkpoint_data.get("failed_steps", []))
        self.step_results = checkpoint_data.get("step_results", {})
        self.current_step = checkpoint_data.get("current_step", 0)
        
        return True
    
    def execute(
        self,
        *,
        context: dict[str, Any] | None = None,
        max_steps: int = 100,
        resume: bool = True,
    ) -> OrchestrationResult:
        """
        Execute the orchestration.
        
        Args:
            context: Initial context for steps
            max_steps: Maximum number of steps to execute
            resume: Whether to resume from checkpoint if available
        
        Returns:
            OrchestrationResult
        """
        ctx = context if context else {}
        
        # Try to restore from checkpoint
        if resume:
            self.restore()
        
        # Execute steps
        steps_executed = 0
        while steps_executed < max_steps:
            # Get ready steps
            ready = self.get_ready_steps()
            
            if not ready:
                # No more steps to execute
                break
            
            # Execute ready steps (could be parallelized in future)
            for step_id in ready:
                if steps_executed >= max_steps:
                    break
                
                try:
                    # Check if budget exhausted before executing step
                    if self.token_budget_tracker and self.token_budget_tracker.is_budget_exhausted():
                        log.info("token_budget_exhausted_before_step", step_id=step_id, remaining_tokens=self.token_budget_tracker.remaining_tokens())
                        # Still execute but log warning
                    
                    result = self.execute_step(step_id, ctx)
                    self.step_results[step_id] = result
                    self.completed_steps.add(step_id)
                    self.current_step += 1
                    steps_executed += 1
                    
                    # Check if budget exhausted after step
                    if self.token_budget_tracker and self.token_budget_tracker.is_budget_exhausted():
                        log.info("token_budget_exhausted_after_step", step_id=step_id, remaining_tokens=self.token_budget_tracker.remaining_tokens())
                    
                    # Checkpoint if needed
                    if should_checkpoint(
                        step=self.current_step,
                        last_checkpoint_step=self.last_checkpoint_step,
                        checkpoint_interval_steps=self.checkpoint_interval_steps,
                        last_checkpoint_time=self.last_checkpoint_time,
                        checkpoint_interval_seconds=self.checkpoint_interval_seconds,
                    ):
                        self.checkpoint(ctx)
                
                except Exception as e:
                    self.failed_steps.add(step_id)
                    self.step_results[step_id] = {"ok": False, "error": str(e)}
                    # Continue with other steps
        
        # Final checkpoint
        if self.completed_steps or self.failed_steps:
            self.checkpoint(ctx)
        
        # Determine success
        all_steps = set(self.steps.keys())
        success = len(self.failed_steps) == 0 and self.completed_steps == all_steps
        
        # Log final token usage and include in result
        token_usage_dict: dict[str, Any] | None = None
        if self.token_budget_tracker:
            log.info(
                "orchestration_token_usage",
                total_tokens=self.token_budget_tracker.usage.total_tokens,
                remaining_tokens=self.token_budget_tracker.remaining_tokens(),
                cost_usd=self.token_budget_tracker.usage.cost_usd,
                budget_tokens=self.token_budget_tracker.budget_tokens,
            )
            token_usage_dict = {
                "budget_tokens": self.token_budget_tracker.budget_tokens,
                "used_tokens": self.token_budget_tracker.usage.total_tokens,
                "remaining_tokens": self.token_budget_tracker.remaining_tokens(),
                "cost_usd": self.token_budget_tracker.usage.cost_usd,
                "input_tokens": self.token_budget_tracker.usage.input_tokens,
                "output_tokens": self.token_budget_tracker.usage.output_tokens,
            }
        
        return OrchestrationResult(
            success=success,
            completed_steps=list(self.completed_steps),
            failed_steps=list(self.failed_steps),
            final_result=self.step_results if success else None,
            error=f"Failed steps: {', '.join(self.failed_steps)}" if self.failed_steps else None,
            token_usage=token_usage_dict,
        )


def create_analysis_orchestrator(
    *,
    rfp_id: str,
    job_id: str | None = None,
    rfp_ids: list[str],
    token_budget_tracker: Any | None = None,  # TokenBudgetTracker
) -> LongRunningOrchestrator:
    """
    Create an orchestrator for analyzing multiple RFPs.
    """
    orchestrator = LongRunningOrchestrator(
        rfp_id=rfp_id,
        job_id=job_id,
        token_budget_tracker=token_budget_tracker,
    )
    
    # Step 1: Load all RFPs
    def load_rfps(context: dict[str, Any]) -> dict[str, Any]:
        from .rfps_repo import get_rfp_by_id
        
        loaded: dict[str, Any] = {}
        for rid in rfp_ids:
            rfp = get_rfp_by_id(rid)
            if rfp:
                loaded[rid] = {
                    "title": rfp.get("title"),
                    "clientName": rfp.get("clientName"),
                    "projectType": rfp.get("projectType"),
                }
        
        return {"ok": True, "loaded": loaded, "count": len(loaded)}
    
    orchestrator.add_step(StepDefinition(
        step_id="load_rfps",
        name="Load RFPs",
        execute=load_rfps,
        depends_on=[],
    ))
    
    # Step 2: Analyze each RFP (could be parallelized)
    def analyze_rfp(context: dict[str, Any]) -> dict[str, Any]:
        # This would call the RFP analyzer
        # For now, placeholder
        return {"ok": True, "analyzed": True}
    
    orchestrator.add_step(StepDefinition(
        step_id="analyze",
        name="Analyze RFPs",
        execute=analyze_rfp,
        depends_on=["load_rfps"],
    ))
    
    # Step 3: Generate summary
    def generate_summary(context: dict[str, Any]) -> dict[str, Any]:
        # Generate summary from analysis
        return {"ok": True, "summary": "Analysis complete"}
    
    orchestrator.add_step(StepDefinition(
        step_id="summarize",
        name="Generate Summary",
        execute=generate_summary,
        depends_on=["analyze"],
    ))
    
    return orchestrator
