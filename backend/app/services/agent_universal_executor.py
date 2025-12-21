from __future__ import annotations

from typing import Any, Callable

from ..observability.logging import get_logger
from .agent_checkpoint import get_latest_checkpoint
from .agent_job_planner import plan_job_execution
from .agent_long_running import LongRunningOrchestrator, StepDefinition
from .agent_memory import add_procedural_memory
from .agent_resilience import (
    classify_error,
    retry_with_classification,
)

log = get_logger("agent_universal_executor")


def _create_step_executor(tool_name: str, tool_args: dict[str, Any], alternatives: list[dict[str, Any]]) -> Any:
    """
    Create a step executor function that can try the primary tool and alternatives.
    """
    from .agent_tools.read_registry import READ_TOOLS
    from . import slack_operator_agent as op_agent
    
    # Get tool from either READ_TOOLS or OPERATOR_TOOLS
    tool = READ_TOOLS.get(tool_name) or op_agent.OPERATOR_TOOLS.get(tool_name)
    if not tool:
        def _unknown_tool(context: dict[str, Any]) -> dict[str, Any]:
            return {"ok": False, "error": f"unknown_tool: {tool_name}"}
        return _unknown_tool
    
    _tpl, tool_fn = tool
    
    # Create alternative tool functions (fix closure by using default args to capture values)
    alt_tool_fns: list[Callable[[dict[str, Any]], dict[str, Any]]] = []
    for alt in alternatives:
        alt_tool_name = str(alt.get("tool") or tool_name).strip()
        alt_tool_args = dict(alt.get("tool_args") or {})  # Make a copy
        alt_tool = READ_TOOLS.get(alt_tool_name) or op_agent.OPERATOR_TOOLS.get(alt_tool_name)
        if alt_tool:
            _alt_tpl, alt_tool_fn = alt_tool
            # Create executor with default args to capture loop variables in closure
            def _create_alt_executor(fn=alt_tool_fn, args=alt_tool_args):
                def _alt_executor(ctx: dict[str, Any]) -> dict[str, Any]:
                    merged = dict(args)  # Copy args
                    if isinstance(ctx, dict):
                        for key in ["rfpId", "jobId", "channelId", "threadTs"]:
                            if key in ctx:
                                merged.setdefault(key, ctx[key])
                    return fn(merged)
                return _alt_executor
            # Immediately invoke factory to create executor with captured values
            alt_tool_fns.append(_create_alt_executor())
    
    def _execute_step(context: dict[str, Any]) -> dict[str, Any]:
        """Execute the step with primary tool and alternatives if needed."""
        # Merge context into tool args
        merged_args = {**tool_args}
        if isinstance(context, dict):
            # Allow context to override args (for things like rfpId from job scope)
            for key in ["rfpId", "jobId", "channelId", "threadTs"]:
                if key in context:
                    merged_args.setdefault(key, context[key])
        
        # Try primary tool with retry
        try:
            result = retry_with_classification(
                lambda: tool_fn(merged_args if isinstance(merged_args, dict) else {}),
                max_retries=2,
            )
            if isinstance(result, dict) and result.get("ok"):
                return result
            # If not successful but no exception, try alternatives
        except Exception as e:
            error_class = classify_error(e)
            # For non-retryable errors, try alternatives immediately
            if not error_class.retryable:
                # Will try alternatives below
                pass
            else:
                # Retryable errors should have been handled by retry_with_classification
                # If we get here, retries were exhausted, try alternatives
                pass
        
        # Try alternatives if primary didn't succeed
        for i, alt_fn in enumerate(alt_tool_fns):
            try:
                alt_result = alt_fn(context)
                if isinstance(alt_result, dict) and alt_result.get("ok"):
                    log.info(
                        "step_alternative_succeeded",
                        step=tool_name,
                        alternative_index=i,
                    )
                    return alt_result
            except Exception:
                continue
        
        # All attempts failed
        return {"ok": False, "error": f"tool_execution_failed: {tool_name}", "tried_alternatives": len(alternatives)}
    
    return _execute_step


def execute_universal_job(
    *,
    job_id: str,
    payload: dict[str, Any],
    rfp_id: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """
    Execute a universal job that can handle any user request.
    
    This is the core universal executor that:
    1. Plans the execution (if not resuming)
    2. Executes the plan using LongRunningOrchestrator
    3. Handles failures with self-healing
    4. Learns from outcomes
    """
    request = str(payload.get("request") or "").strip()
    if not request and not resume:
        return {"ok": False, "error": "missing_request_in_payload"}
    
    rfp_id_for_job = rfp_id or payload.get("rfpId") or "rfp_universal_job"
    
    # Initialize token budget tracker (default: 15 minutes, scale: 4 hours = $10)
    from .long_running_job_helpers import initialize_token_budget_for_job
    
    # Check if resuming from checkpoint - restore plan and tracker if present
    plan = payload.get("execution_plan")
    checkpoint_id = payload.get("checkpoint_id")
    checkpoint_data_for_budget: dict[str, Any] | None = None
    
    if resume and checkpoint_id:
        checkpoint = get_latest_checkpoint(rfp_id=rfp_id_for_job, job_id=job_id)
        if checkpoint:
            checkpoint_data_for_budget = checkpoint.get("payload", {}).get("checkpointData", {})
            if "execution_plan" in checkpoint_data_for_budget:
                plan = checkpoint_data_for_budget.get("execution_plan")
    
    # Initialize or restore token budget tracker
    token_budget_tracker = initialize_token_budget_for_job(
        payload=payload,
        checkpoint_data=checkpoint_data_for_budget,
    )
    
    # Plan if we don't have one
    if not plan:
        # Try to get similar successful jobs as guidance
        from .agent_job_learning import get_similar_successful_jobs
        similar_jobs = get_similar_successful_jobs(request=request, limit=3)
        
        planning_context = payload.get("context") or {}
        if similar_jobs:
            planning_context["similar_successful_jobs"] = similar_jobs[:2]  # Include top 2 as guidance
        
        # Pass token budget tracker to planner if available (for token tracking during planning)
        planning_result = plan_job_execution(
            request=request,
            context=planning_context,
            rfp_id=rfp_id,
            token_budget_tracker=token_budget_tracker,
        )
        if not planning_result.get("ok"):
            return {
                "ok": False,
                "error": f"planning_failed: {planning_result.get('error', 'unknown')}",
            }
        plan = planning_result.get("plan")
        if not plan:
            return {"ok": False, "error": "planning_returned_no_plan"}
    
    # Create orchestrator with token budget tracker
    orchestrator = LongRunningOrchestrator(
        rfp_id=rfp_id_for_job,
        job_id=job_id,
        checkpoint_interval_steps=10,
        checkpoint_interval_seconds=300.0,
        token_budget_tracker=token_budget_tracker,
    )
    
    # Add steps from plan
    steps = plan.get("steps", [])
    if not steps:
        return {"ok": False, "error": "plan_has_no_steps"}
    
    step_definitions: dict[str, StepDefinition] = {}
    for step_data in steps:
        step_id = str(step_data.get("step_id") or "").strip()
        if not step_id:
            continue
        
        tool_name = str(step_data.get("tool") or "").strip()
        tool_args = step_data.get("tool_args") if isinstance(step_data.get("tool_args"), dict) else {}
        alternatives = step_data.get("alternative_approaches") if isinstance(step_data.get("alternative_approaches"), list) else []
        depends_on = [str(d) for d in step_data.get("depends_on", []) if str(d).strip()]
        retryable = bool(step_data.get("retryable", True))
        
        step_executor = _create_step_executor(tool_name, tool_args, alternatives)
        
        step_def = StepDefinition(
            step_id=step_id,
            name=str(step_data.get("name") or step_id),
            execute=step_executor,
            depends_on=depends_on,
            timeout_seconds=float(step_data.get("estimated_time_seconds") or 300.0),
            retryable=retryable,
            checkpoint_after=True,
        )
        
        step_definitions[step_id] = step_def
        orchestrator.add_step(step_def)
    
    # Store plan in context for checkpointing
    context = {
        "jobId": job_id,
        "request": request,
        "execution_plan": plan,
        "rfpId": rfp_id,
        **payload.get("context", {}),
    }
    
    # Execute
    try:
        result = orchestrator.execute(
            context=context,
            max_steps=200,  # Allow for complex multi-step operations
            resume=resume,
        )
        
        if result.success:
            # Job completed successfully - learn from it
            try:
                _learn_from_successful_job(
                    job_id=job_id,
                    request=request,
                    plan=plan,
                    result=result,
                    rfp_id=rfp_id,
                )
            except Exception as e:
                log.warning("job_learning_failed", error=str(e), job_id=job_id)
            
            # Include token usage in result (prefer from result, otherwise from tracker)
            result_dict = {
                "ok": True,
                "success": True,
                "completed_steps": result.completed_steps,
                "final_result": result.final_result,
            }
            
            # Use token_usage from result if available, otherwise from tracker
            if result.token_usage:
                result_dict["token_usage"] = result.token_usage
            elif token_budget_tracker:
                result_dict["token_usage"] = {
                    "budget_tokens": token_budget_tracker.budget_tokens,
                    "used_tokens": token_budget_tracker.usage.total_tokens,
                    "remaining_tokens": token_budget_tracker.remaining_tokens(),
                    "cost_usd": token_budget_tracker.usage.cost_usd,
                    "input_tokens": token_budget_tracker.usage.input_tokens,
                    "output_tokens": token_budget_tracker.usage.output_tokens,
                }
            
            return result_dict
        else:
            # Job failed - learn from failure and attempt recovery
            recovery_attempted = False
            try:
                recovery_result = _attempt_failure_recovery(
                    job_id=job_id,
                    request=request,
                    plan=plan,
                    failed_steps=result.failed_steps,
                    step_results=orchestrator.step_results,
                    rfp_id=rfp_id,
                )
                recovery_attempted = recovery_result.get("attempted", False)
            except Exception as e:
                log.warning("job_recovery_failed", error=str(e), job_id=job_id)
            
            # Learn from failure
            try:
                _learn_from_failed_job(
                    job_id=job_id,
                    request=request,
                    plan=plan,
                    failed_steps=result.failed_steps,
                    step_results=orchestrator.step_results,
                    rfp_id=rfp_id,
                )
            except Exception as e:
                log.warning("job_learning_failed", error=str(e), job_id=job_id)
            
            # Include token usage in result (prefer from result, otherwise from tracker)
            result_dict = {
                "ok": False,
                "success": False,
                "error": result.error,
                "completed_steps": result.completed_steps,
                "failed_steps": result.failed_steps,
                "recovery_attempted": recovery_attempted,
                "partial_results": result.final_result if result.final_result else {},
            }
            
            # Use token_usage from result if available, otherwise from tracker
            if result.token_usage:
                result_dict["token_usage"] = result.token_usage
            elif token_budget_tracker:
                result_dict["token_usage"] = {
                    "budget_tokens": token_budget_tracker.budget_tokens,
                    "used_tokens": token_budget_tracker.usage.total_tokens,
                    "remaining_tokens": token_budget_tracker.remaining_tokens(),
                    "cost_usd": token_budget_tracker.usage.cost_usd,
                    "input_tokens": token_budget_tracker.usage.input_tokens,
                    "output_tokens": token_budget_tracker.usage.output_tokens,
                }
            
            return result_dict
    
    except Exception as e:
        log.error("universal_job_execution_failed", error=str(e), job_id=job_id, request=request[:200])
        result_dict = {
            "ok": False,
            "error": str(e),
            "success": False,
        }
        
        # Include token usage if tracker available
        if token_budget_tracker:
            result_dict["token_usage"] = {
                "budget_tokens": token_budget_tracker.budget_tokens,
                "used_tokens": token_budget_tracker.usage.total_tokens,
                "remaining_tokens": token_budget_tracker.remaining_tokens(),
                "cost_usd": token_budget_tracker.usage.cost_usd,
                "input_tokens": token_budget_tracker.usage.input_tokens,
                "output_tokens": token_budget_tracker.usage.output_tokens,
            }
        
        return result_dict


def _learn_from_successful_job(
    *,
    job_id: str,
    request: str,
    plan: dict[str, Any],
    result: Any,
    rfp_id: str | None = None,
) -> None:
    """
    Learn from a successful job execution.
    Store successful patterns in procedural memory.
    """
    # Extract successful workflow pattern
    workflow_name = f"Job: {request[:100]}"
    tool_sequence = [step.get("tool") for step in plan.get("steps", []) if step.get("tool")]
    
    # Store in procedural memory (global scope for job patterns)
    # Use a system user_sub for global patterns
    user_sub = "system_job_learning"
    
    try:
        add_procedural_memory(
            user_sub=user_sub,
            workflow=workflow_name,
            success=True,
            context={
                "toolSequence": tool_sequence,
                "jobId": job_id,
                "request": request,
                "stepCount": len(plan.get("steps", [])),
                "completedSteps": result.completed_steps if hasattr(result, "completed_steps") else [],
            },
            rfp_id=rfp_id,
            source="universal_job_executor",
        )
    except Exception as e:
        log.warning("procedural_memory_store_failed", error=str(e))


def _learn_from_failed_job(
    *,
    job_id: str,
    request: str,
    plan: dict[str, Any],
    failed_steps: list[str],
    step_results: dict[str, Any],
    rfp_id: str | None = None,
) -> None:
    """
    Learn from a failed job execution.
    Store failure patterns to avoid in future.
    """
    user_sub = "system_job_learning"
    
    # Extract failure information
    failure_pattern = {
        "failedSteps": failed_steps,
        "request": request,
        "stepErrors": {
            step_id: result.get("error") 
            for step_id, result in step_results.items() 
            if step_id in failed_steps and isinstance(result, dict)
        },
    }
    
    try:
        add_procedural_memory(
            user_sub=user_sub,
            workflow=f"Failed Job: {request[:100]}",
            success=False,
            context={
                "jobId": job_id,
                "failurePattern": failure_pattern,
                "failedSteps": failed_steps,
            },
            rfp_id=rfp_id,
            source="universal_job_executor",
        )
    except Exception as e:
        log.warning("failure_pattern_store_failed", error=str(e))


def _attempt_failure_recovery(
    *,
    job_id: str,
    request: str,
    plan: dict[str, Any],
    failed_steps: list[str],
    step_results: dict[str, Any],
    rfp_id: str | None = None,
) -> dict[str, Any]:
    """
    Attempt to recover from job failure.
    Analyzes failures and attempts automatic recovery strategies.
    """
    from .agent_resilience import analyze_failure_and_recover
    
    # Analyze each failed step
    recovery_results: list[dict[str, Any]] = []
    
    for step_id in failed_steps:
        step_result = step_results.get(step_id, {})
        error_msg = step_result.get("error") or "unknown_error"
        
        # Create a synthetic exception for analysis
        class SyntheticError(Exception):
            pass
        
        synthetic_error = SyntheticError(error_msg)
        
        recovery_analysis = analyze_failure_and_recover(
            error=synthetic_error,
            context={
                "step_id": step_id,
                "job_id": job_id,
                "request": request,
                "step_result": step_result,
            },
            job_id=job_id,
        )
        
        recovery_results.append({
            "step_id": step_id,
            "analysis": recovery_analysis,
        })
    
    log.info(
        "job_recovery_analysis",
        job_id=job_id,
        failed_steps=failed_steps,
        request=request[:200],
        recovery_results_count=len(recovery_results),
    )
    
    # For now, just analyze - actual automatic recovery would require:
    # - Modifying the plan to skip optional failed steps
    # - Retrying with alternative approaches
    # - Creating follow-up jobs for partial completion
    # This is a foundation that can be enhanced in the future
    
    return {
        "attempted": False,
        "reason": "automatic_recovery_analysis_complete",
        "recovery_analysis": recovery_results,
    }
