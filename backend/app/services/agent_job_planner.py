from __future__ import annotations

import json
from typing import Any

from ..ai.client import AiNotConfigured
from ..observability.logging import get_logger
from ..settings import settings
from .agent_tools.read_registry import READ_TOOLS
from . import slack_operator_agent as op_agent

log = get_logger("agent_job_planner")


def _get_tool_inventory() -> str:
    """
    Generate a comprehensive inventory of available tools for the AI planner.
    """
    # Categorize tools
    categories: dict[str, list[str]] = {
        "Slack": [],
        "DynamoDB": [],
        "S3": [],
        "AWS Services": [],
        "GitHub": [],
        "Telemetry": [],
        "Browser": [],
        "Memory": [],
        "RFPs/Proposals": [],
        "Skills": [],
        "Jobs": [],
        "Opportunity State": [],
        "Other": [],
    }
    
    for tool_name, (tool_def, _fn) in READ_TOOLS.items():
        desc = tool_def.get("description", "") if isinstance(tool_def, dict) else ""
        
        # Categorize based on name
        if tool_name.startswith("slack_"):
            categories["Slack"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("ddb_") or tool_name.startswith("dynamodb_"):
            categories["DynamoDB"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("s3_") or tool_name == "extract_resume_text":
            categories["S3"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("ecs_") or tool_name.startswith("sqs_") or tool_name.startswith("cognito_") or tool_name.startswith("secrets_"):
            categories["AWS Services"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("github_"):
            categories["GitHub"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("telemetry_") or tool_name.startswith("logs_"):
            categories["Telemetry"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("browser_") or tool_name.startswith("bw_"):
            categories["Browser"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("agent_memory_") or tool_name.startswith("memory_"):
            categories["Memory"].append(f"- `{tool_name}`: {desc}")
        elif "rfp" in tool_name.lower() or "proposal" in tool_name.lower():
            categories["RFPs/Proposals"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("skills_"):
            categories["Skills"].append(f"- `{tool_name}`: {desc}")
        else:
            categories["Other"].append(f"- `{tool_name}`: {desc}")
    
    # Add operator tools
    for tool_name, (tool_def, _fn) in op_agent.OPERATOR_TOOLS.items():
        if tool_name in READ_TOOLS:
            continue  # Skip duplicates
        desc = tool_def.get("description", "") if isinstance(tool_def, dict) else ""
        
        if tool_name.startswith("schedule_job") or tool_name.startswith("agent_job_"):
            categories["Jobs"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("opportunity_") or tool_name.startswith("journal_") or tool_name.startswith("event_"):
            categories["Opportunity State"].append(f"- `{tool_name}`: {desc}")
        elif tool_name.startswith("slack_"):
            categories["Slack"].append(f"- `{tool_name}`: {desc}")
        else:
            categories["Other"].append(f"- `{tool_name}`: {desc}")
    
    # Build inventory text
    lines: list[str] = []
    for category, tool_list in categories.items():
        if tool_list:
            lines.append(f"\n**{category}:**")
            lines.extend(tool_list)
    
    return "\n".join(lines)


def plan_job_execution(
    *,
    request: str,
    context: dict[str, Any] | None = None,
    rfp_id: str | None = None,
    token_budget_tracker: Any | None = None,  # TokenBudgetTracker (optional, for token tracking during planning)
) -> dict[str, Any]:
    """
    Use AI to plan a job execution for a user request.
    
    Returns an execution plan with steps, tools, dependencies, and estimates.
    """
    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")
    
    tool_inventory = _get_tool_inventory()
    ctx = context if context else {}
    
    # Build planning prompt
    system_prompt = f"""You are a job execution planner for an RFP/proposal workflow platform.

Your job is to analyze user requests and create detailed execution plans that can be executed by an autonomous agent system.

**Available Tools:**
{tool_inventory}

**Planning Guidelines:**
1. Break down the request into clear, executable steps
2. Each step should use specific tools from the inventory
3. Identify dependencies between steps (which steps must complete before others)
4. Consider failure scenarios and alternative approaches
5. Estimate execution time and resource requirements
6. Plan for checkpointing on long-running operations
7. Identify what success looks like for each step

**Output Format:**
Return a JSON object with this structure:
{{
  "goal": "Clear description of what we're trying to accomplish",
  "steps": [
    {{
      "step_id": "unique_step_id",
      "name": "Human-readable step name",
      "description": "What this step does",
      "tool": "tool_name_to_use",
      "tool_args": {{"arg1": "value1", "arg2": "value2"}},
      "depends_on": ["step_id_of_prerequisite"],
      "estimated_time_seconds": 30,
      "retryable": true,
      "alternative_approaches": [
        {{
          "tool": "alternative_tool",
          "tool_args": {{...}},
          "when": "When to use this alternative"
        }}
      ],
      "success_criteria": "How to determine if this step succeeded",
      "failure_handling": "What to do if this step fails"
    }}
  ],
  "estimated_total_time_seconds": 300,
  "requires_checkpointing": false,
  "can_partial_succeed": false,
  "notes": "Any additional notes or considerations"
}}

Be specific with tool names and arguments. Think through edge cases and failure modes.
"""
    
    # Include similar successful jobs as guidance if available
    guidance_text = ""
    if ctx and isinstance(ctx, dict):
        similar_jobs = ctx.get("similar_successful_jobs")
        if similar_jobs and isinstance(similar_jobs, list) and len(similar_jobs) > 0:
            guidance_text = "\n\n**Similar Successful Jobs (for reference):**\n"
            for i, similar in enumerate(similar_jobs[:2], 1):
                if isinstance(similar, dict):
                    tools = similar.get("toolSequence", [])
                    req = similar.get("request", "")
                    if tools or req:
                        guidance_text += f"\n{i}. Request: {req[:200]}\n   Tools used: {', '.join(str(t) for t in tools[:10])}\n"
            guidance_text += "\nYou can use these as patterns, but adapt them to the specific request above.\n"
    
    user_prompt = f"""Create an execution plan for this request:

{request}

**Additional Context:**
{json.dumps({k: v for k, v in ctx.items() if k != "similar_successful_jobs"}, indent=2) if ctx else "None"}{guidance_text}
"""
    
    try:
        # Use text mode and parse JSON manually (more flexible)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        from ..ai.client import call_text
        
        response_text, _meta = call_text(
            purpose="job_planning",
            messages=messages,
            temperature=0.3,
            max_tokens=4000,
            token_budget_tracker=token_budget_tracker,  # Track tokens during planning
        )
        if not response_text or not isinstance(response_text, str):
            raise RuntimeError("empty_or_invalid_response_from_planner")
        
        # Parse JSON from response
        try:
            # Try to extract JSON from markdown code blocks if present
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)
            else:
                # Try to find JSON object directly
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(0)
            
            plan_dict = json.loads(response_text)
        except (json.JSONDecodeError, AttributeError) as e:
            log.warning("job_plan_json_parse_failed", error=str(e), response_preview=response_text[:500])
            # Return fallback plan
            plan_dict = {
                "goal": request,
                "steps": [],
                "estimated_total_time_seconds": 60.0,
                "requires_checkpointing": False,
                "can_partial_succeed": False,
                "notes": f"Failed to parse plan JSON: {str(e)}",
            }
        
        log.info(
            "job_plan_created",
            goal=plan_dict.get("goal", ""),
            step_count=len(plan_dict.get("steps", [])),
            estimated_time=plan_dict.get("estimated_total_time_seconds", 0),
        )
        
        return {
            "ok": True,
            "plan": plan_dict,
        }
    
    except Exception as e:
        log.error("job_planning_failed", error=str(e), request=request[:200])
        # Fallback to simple plan structure
        return {
            "ok": False,
            "error": str(e),
            "plan": {
                "goal": request,
                "steps": [
                    {
                        "step_id": "execute_request",
                        "name": "Execute request",
                        "description": f"Attempt to fulfill: {request}",
                        "tool": "unknown",
                        "tool_args": {},
                        "depends_on": [],
                        "estimated_time_seconds": 60.0,
                        "retryable": True,
                        "alternative_approaches": [],
                        "success_criteria": "Request completed successfully",
                        "failure_handling": "Retry or report failure",
                    }
                ],
                "estimated_total_time_seconds": 60.0,
                "requires_checkpointing": False,
                "can_partial_succeed": False,
                "notes": f"Planning failed: {str(e)}",
            },
        }
