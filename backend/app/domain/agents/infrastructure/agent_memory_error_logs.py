"""
Agent Error Log Storage - Store tool/function call errors in memory for debugging and learning.

Error logs are stored as ERROR_LOG memory type and can be retrieved to:
- Surface errors in Slack responses for user feedback
- Learn from error patterns
- Debug tool failures
- Track error trends
"""

from __future__ import annotations

from typing import Any

from .agent_memory_db import MemoryType, create_memory
from ....observability.logging import get_logger

log = get_logger("agent_memory_error_logs")


def store_error_log(
    *,
    tool_name: str,
    error_message: str,
    error_type: str | None = None,
    error_details: dict[str, Any] | None = None,
    tool_args: dict[str, Any] | None = None,
    tool_result: dict[str, Any] | None = None,
    user_query: str | None = None,
    traceback_str: str | None = None,
    # Provenance fields
    user_sub: str | None = None,
    cognito_user_id: str | None = None,
    slack_user_id: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    slack_team_id: str | None = None,
    rfp_id: str | None = None,
    source: str = "slack_operator",
) -> dict[str, Any] | None:
    """
    Store a tool/function call error as an ERROR_LOG memory.
    
    Args:
        tool_name: Name of the tool/function that failed
        error_message: Human-readable error message
        error_type: Type of error (e.g., "ValueError", "AccessDeniedException")
        error_details: Additional error details (errorCategory, retryable, etc.)
        tool_args: Arguments passed to the tool (will be redacted for sensitive data)
        tool_result: Result dict if available (may contain error details)
        user_query: User's original query that led to this error
        traceback_str: Full traceback string for debugging
        user_sub: User identifier (Cognito sub)
        cognito_user_id: Cognito user ID for provenance
        slack_user_id: Slack user ID for provenance
        slack_channel_id: Slack channel ID where error occurred
        slack_thread_ts: Slack thread timestamp where error occurred
        slack_team_id: Slack team ID
        rfp_id: RFP identifier if error occurred in RFP context
        source: Source system (e.g., "slack_operator", "slack_agent")
    
    Returns:
        Created memory dict or None if storage failed
    """
    if not tool_name or not error_message:
        log.warning("error_log_skipped_missing_fields", tool_name=tool_name)
        return None
    
    # Build scope ID (user-scoped if available, otherwise global)
    if user_sub:
        scope_id = f"USER#{user_sub}"
    elif rfp_id:
        scope_id = f"RFP#{rfp_id}"
    else:
        scope_id = "GLOBAL"
    
    # Build error content (structured for easy parsing)
    content_lines = [
        f"Tool: {tool_name}",
        f"Error: {error_message}",
    ]
    
    if error_type:
        content_lines.append(f"Error Type: {error_type}")
    
    if error_details:
        content_lines.append(f"Error Details: {error_details}")
    
    if tool_args:
        # Redact sensitive arguments (passwords, tokens, etc.)
        redacted_args = {}
        for k, v in tool_args.items():
            key_lower = str(k).lower()
            if any(sensitive in key_lower for sensitive in ["password", "token", "secret", "key", "credential"]):
                redacted_args[k] = "[REDACTED]"
            else:
                # Limit value length
                v_str = str(v)
                redacted_args[k] = v_str[:200] + "..." if len(v_str) > 200 else v_str
        
        content_lines.append(f"Tool Arguments: {redacted_args}")
    
    if tool_result and isinstance(tool_result, dict):
        result_preview = {k: v for k, v in list(tool_result.items())[:10]}
        content_lines.append(f"Tool Result: {result_preview}")
    
    if user_query:
        content_lines.append(f"User Query: {user_query[:500]}")  # Limit query length
    
    if traceback_str:
        # Include last 20 lines of traceback (most relevant)
        tb_lines = traceback_str.split("\n")
        content_lines.append("Traceback:\n" + "\n".join(tb_lines[-20:]))
    
    content = "\n".join(content_lines)
    
    # Build metadata
    metadata: dict[str, Any] = {
        "toolName": tool_name,
        "errorMessage": error_message,
    }
    
    if error_type:
        metadata["errorType"] = error_type
    
    if error_details:
        metadata.update(error_details)
    
    if tool_result and isinstance(tool_result, dict):
        metadata["errorCategory"] = tool_result.get("errorCategory")
        metadata["retryable"] = tool_result.get("retryable")
    
    # Build tags for easy filtering
    tags = ["error", "tool_failure", tool_name]
    if error_type:
        tags.append(f"error_type:{error_type}")
    if error_details and error_details.get("errorCategory"):
        tags.append(f"error_category:{error_details['errorCategory']}")
    if rfp_id:
        tags.append(f"rfp:{rfp_id}")
    
    try:
        memory = create_memory(
            memory_type=MemoryType.ERROR_LOG,
            scope_id=scope_id,
            content=content,
            tags=tags,
            keywords=[tool_name, error_message[:50]],  # Extract keywords for search
            metadata=metadata,
            summary=f"Tool {tool_name} failed: {error_message[:100]}",
            # Provenance
            cognito_user_id=cognito_user_id or user_sub,
            slack_user_id=slack_user_id,
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
            slack_team_id=slack_team_id,
            rfp_id=rfp_id,
            source=source,
        )
        
        log.info(
            "error_log_stored",
            memory_id=memory.get("memoryId"),
            tool_name=tool_name,
            error_type=error_type,
            scope_id=scope_id,
        )
        
        return memory
    except Exception as e:
        log.warning("error_log_storage_failed", tool_name=tool_name, error=str(e))
        return None
