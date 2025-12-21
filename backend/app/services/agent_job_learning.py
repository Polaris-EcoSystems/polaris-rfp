from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger
from .agent_jobs_repo import list_recent_jobs, get_job
from .agent_memory import add_procedural_memory, retrieve_relevant_memories

log = get_logger("agent_job_learning")


def analyze_completed_jobs(
    *,
    limit: int = 50,
    job_type: str | None = None,
    include_failed: bool = True,
) -> dict[str, Any]:
    """
    Analyze completed jobs (successful and failed) to extract patterns and best practices.
    
    Args:
        limit: Maximum number of jobs to analyze
        job_type: Optional job type filter
        include_failed: Whether to include failed jobs in analysis
    
    Returns:
        Analysis results with patterns, best practices, and suggestions
    """
    try:
        # Get recent completed jobs
        completed_jobs_raw = list_recent_jobs(limit=limit, status="completed")
        failed_jobs_raw: list[dict[str, Any]] = []
        if include_failed:
            failed_jobs_raw = list_recent_jobs(limit=limit, status="failed")
        
        # Type guard: ensure we have dicts
        completed_jobs = [j for j in completed_jobs_raw if isinstance(j, dict)]
        failed_jobs = [j for j in failed_jobs_raw if isinstance(j, dict)]
        all_jobs = completed_jobs + failed_jobs
        
        # Filter by job type if specified
        if job_type:
            all_jobs = [j for j in all_jobs if str(j.get("jobType") or "").strip() == job_type]
        
        if not all_jobs:
            return {
                "ok": True,
                "analyzed": 0,
                "patterns": [],
                "suggestions": [],
            }
        
        # Analyze patterns
        patterns: list[dict[str, Any]] = []
        success_rate_by_type: dict[str, dict[str, int]] = {}
        
        for job in all_jobs:
            jtype = str(job.get("jobType") or "unknown")
            status = str(job.get("status") or "").strip().lower()
            
            if jtype not in success_rate_by_type:
                success_rate_by_type[jtype] = {"total": 0, "completed": 0, "failed": 0}
            
            success_rate_by_type[jtype]["total"] += 1
            if status == "completed":
                success_rate_by_type[jtype]["completed"] += 1
            elif status == "failed":
                success_rate_by_type[jtype]["failed"] += 1
            
            # Extract execution plan if available (for universal jobs)
            payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            execution_plan = payload.get("execution_plan")
            
            if execution_plan and isinstance(execution_plan, dict):
                steps = execution_plan.get("steps", [])
                if steps and status == "completed":
                    # Successful pattern
                    tool_sequence = [s.get("tool") for s in steps if s.get("tool")]
                    patterns.append({
                        "type": "successful_pattern",
                        "jobType": jtype,
                        "toolSequence": tool_sequence,
                        "stepCount": len(steps),
                        "jobId": job.get("jobId"),
                    })
            
            # Analyze failures
            if status == "failed":
                error = str(job.get("error") or "").strip()
                if error:
                    patterns.append({
                        "type": "failure_pattern",
                        "jobType": jtype,
                        "error": error[:200],
                        "jobId": job.get("jobId"),
                    })
        
        # Generate suggestions
        suggestions: list[str] = []
        
        for jtype, stats in success_rate_by_type.items():
            total = stats["total"]
            if total > 0:
                success_rate = stats["completed"] / total
                if success_rate < 0.5 and total >= 3:
                    suggestions.append(
                        f"Job type '{jtype}' has low success rate ({success_rate:.1%}). "
                        f"Consider reviewing failure patterns and improving error handling."
                    )
        
        log.info(
            "job_analysis_completed",
            analyzed=len(all_jobs),
            patterns_found=len(patterns),
            suggestions=len(suggestions),
        )
        
        return {
            "ok": True,
            "analyzed": len(all_jobs),
            "success_rate_by_type": success_rate_by_type,
            "patterns": patterns,
            "suggestions": suggestions,
        }
    
    except Exception as e:
        log.error("job_analysis_failed", error=str(e))
        return {
            "ok": False,
            "error": str(e),
        }


def extract_best_practices(
    *,
    job_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Extract best practices from successful job executions.
    
    Returns reusable patterns and templates that can be used for future jobs.
    """
    try:
        # Get successful jobs
        completed_jobs_raw = list_recent_jobs(limit=limit * 2, status="completed")
        
        # Type guard: ensure we have dicts
        completed_jobs = [j for j in completed_jobs_raw if isinstance(j, dict)]
        
        if job_type:
            completed_jobs = [j for j in completed_jobs if str(j.get("jobType") or "").strip() == job_type]
        
        best_practices: list[dict[str, Any]] = []
        
        for job in completed_jobs[:limit]:
            payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            execution_plan = payload.get("execution_plan")
            
            if execution_plan and isinstance(execution_plan, dict):
                steps = execution_plan.get("steps", [])
                if steps:
                    practice = {
                        "jobId": job.get("jobId"),
                        "jobType": job.get("jobType"),
                        "request": payload.get("request", ""),
                        "toolSequence": [s.get("tool") for s in steps if s.get("tool")],
                        "stepCount": len(steps),
                        "estimatedTime": execution_plan.get("estimated_total_time_seconds", 0),
                    }
                    best_practices.append(practice)
        
        return best_practices
    
    except Exception as e:
        log.error("best_practices_extraction_failed", error=str(e))
        return []


def update_memory_from_job_outcomes() -> dict[str, Any]:
    """
    Analyze job outcomes and update procedural memory with successful workflows.
    This can be run periodically to learn from job executions.
    """
    try:
        # Analyze recent jobs
        analysis = analyze_completed_jobs(limit=100, include_failed=True)
        if not analysis.get("ok"):
            return {"ok": False, "error": "analysis_failed"}
        
        patterns = analysis.get("patterns", [])
        best_practices = extract_best_practices(limit=20)
        
        # Store successful patterns in procedural memory
        user_sub = "system_job_learning"
        stored_count = 0
        
        for practice in best_practices:
            if not practice.get("toolSequence"):
                continue
            
            workflow_name = f"Job Pattern: {practice.get('jobType', 'unknown')}"
            try:
                add_procedural_memory(
                    user_sub=user_sub,
                    workflow=workflow_name,
                    success=True,
                    context={
                        "toolSequence": practice.get("toolSequence", []),
                        "stepCount": practice.get("stepCount", 0),
                        "estimatedTime": practice.get("estimatedTime", 0),
                        "jobId": practice.get("jobId"),
                        "request": practice.get("request", "")[:500],
                    },
                    source="job_learning_service",
                )
                stored_count += 1
            except Exception as e:
                log.warning("memory_store_failed", error=str(e), practice=workflow_name)
        
        # Store failure patterns
        failure_patterns = [p for p in patterns if p.get("type") == "failure_pattern"]
        for pattern in failure_patterns[:10]:  # Limit to top 10 failure patterns
            try:
                add_procedural_memory(
                    user_sub=user_sub,
                    workflow=f"Failure Pattern: {pattern.get('jobType', 'unknown')}",
                    success=False,
                    context={
                        "error": pattern.get("error", ""),
                        "jobType": pattern.get("jobType"),
                        "jobId": pattern.get("jobId"),
                    },
                    source="job_learning_service",
                )
                stored_count += 1
            except Exception as e:
                log.warning("failure_pattern_store_failed", error=str(e))
        
        log.info(
            "memory_updated_from_jobs",
            patterns_analyzed=len(patterns),
            best_practices_found=len(best_practices),
            stored_count=stored_count,
        )
        
        return {
            "ok": True,
            "patterns_analyzed": len(patterns),
            "best_practices_found": len(best_practices),
            "stored_count": stored_count,
        }
    
    except Exception as e:
        log.error("memory_update_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def get_similar_successful_jobs(
    *,
    request: str,
    job_type: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Find similar successful jobs that can serve as templates for a new request.
    Uses memory search to find relevant patterns.
    """
    try:
        # Search procedural memory for similar successful workflows
        user_sub = "system_job_learning"
        scope_id = f"USER#{user_sub}"
        
        memories = retrieve_relevant_memories(
            scope_id=scope_id,
            memory_types=["procedural"],
            query_text=request,
            limit=limit * 2,
        )
        
        # Filter for successful patterns only
        successful_memories = []
        for memory in memories:
            # Check if this is a successful pattern (workflow name indicates success)
            workflow = memory.get("content", "") or ""
            if "Failed" not in workflow and "Failure" not in workflow:
                successful_memories.append(memory)
        
        # Extract job information from memories
        similar_jobs: list[dict[str, Any]] = []
        for memory in successful_memories[:limit]:
            if not isinstance(memory, dict):
                continue
            context = memory.get("context", {})
            if not isinstance(context, dict):
                context = {}
            
            job_info = {
                "toolSequence": context.get("toolSequence", []),
                "stepCount": context.get("stepCount", 0),
                "request": context.get("request", ""),
                "jobId": context.get("jobId"),
            }
            similar_jobs.append(job_info)
        
        return similar_jobs
    
    except Exception as e:
        log.warning("similar_jobs_search_failed", error=str(e), request=request[:200])
        return []


def generate_job_template(
    *,
    request: str,
    job_type: str = "ai_agent_execute",
) -> dict[str, Any] | None:
    """
    Generate a job template based on similar successful jobs.
    """
    try:
        similar_jobs = get_similar_successful_jobs(request=request, limit=3)
        
        if not similar_jobs:
            return None
        
        # Use the most relevant similar job as a template
        template_job = similar_jobs[0]
        
        # Get full job details if we have a jobId
        template: dict[str, Any] = {
            "jobType": job_type,
            "request": request,
        }
        
        if template_job.get("jobId"):
            try:
                full_job = get_job(job_id=str(template_job["jobId"]))
                if full_job:
                    payload = full_job.get("payload") if isinstance(full_job.get("payload"), dict) else {}
                    execution_plan = payload.get("execution_plan")
                    if execution_plan:
                        template["suggested_plan"] = execution_plan
            except Exception:
                pass
        
        # Add tool sequence as guidance
        if template_job.get("toolSequence"):
            template["suggested_tools"] = template_job.get("toolSequence")
        
        return template
    
    except Exception as e:
        log.warning("template_generation_failed", error=str(e))
        return None
