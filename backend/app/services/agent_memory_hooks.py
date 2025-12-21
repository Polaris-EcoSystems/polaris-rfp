from __future__ import annotations

from typing import Any

from .agent_memory import add_episodic_memory, add_procedural_memory
from ..observability.logging import get_logger

log = get_logger("agent_memory_hooks")


def store_episodic_memory_from_agent_interaction(
    *,
    user_sub: str | None,
    user_message: str,
    agent_response: str,
    context: dict[str, Any] | None = None,
    # Provenance fields
    cognito_user_id: str | None = None,
    slack_user_id: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    slack_team_id: str | None = None,
    rfp_id: str | None = None,
    source: str | None = None,
) -> None:
    """
    Store an episodic memory from an agent interaction with full provenance tracking.
    
    This is called after a successful agent interaction to remember
    the conversation, decision, or outcome.
    
    Args:
        user_sub: User identifier (Cognito sub)
        user_message: What the user asked/said
        agent_response: What the agent responded/did
        context: Optional additional context (channel, thread, tools used, etc.)
        cognito_user_id: Cognito user identifier (for traceability - typically same as user_sub)
        slack_user_id: Slack user ID if memory originated from Slack
        slack_channel_id: Slack channel ID where memory originated
        slack_thread_ts: Slack thread timestamp where memory originated
        slack_team_id: Slack team ID
        rfp_id: RFP identifier if memory is related to an RFP
        source: Source system (e.g., "slack_agent", "slack_operator", "api")
    """
    if not user_sub:
        return  # Can't store without user identifier
    
    try:
        content = f"User: {user_message}\nAgent: {agent_response}"
        
        memory_context = {
            "userMessage": user_message,
            "agentResponse": agent_response,
        }
        if context:
            memory_context.update(context)
        
        # Extract provenance from context if not explicitly provided
        final_cognito_user_id = cognito_user_id or user_sub
        final_slack_user_id = slack_user_id or (context.get("slackUserId") if context else None)
        final_slack_channel_id = slack_channel_id or (context.get("channelId") if context else None)
        final_slack_thread_ts = slack_thread_ts or (context.get("threadTs") if context else None)
        final_slack_team_id = slack_team_id or (context.get("slackTeamId") if context else None)
        final_rfp_id = rfp_id or (context.get("rfpId") if context else None)
        final_source = source or (context.get("source") if context else "agent_interaction")
        
        add_episodic_memory(
            user_sub=user_sub,
            content=content,
            context=memory_context,
            cognito_user_id=final_cognito_user_id,
            slack_user_id=final_slack_user_id,
            slack_channel_id=final_slack_channel_id,
            slack_thread_ts=final_slack_thread_ts,
            slack_team_id=final_slack_team_id,
            rfp_id=final_rfp_id,
            source=final_source,
        )
    except Exception as e:
        log.warning("episodic_memory_store_failed", user_sub=user_sub, error=str(e))
        # Non-critical, don't raise


def store_procedural_memory_from_tool_sequence(
    *,
    user_sub: str | None,
    tool_sequence: list[str],
    success: bool,
    outcome: str | None = None,
    context: dict[str, Any] | None = None,
    # Provenance fields
    cognito_user_id: str | None = None,
    slack_user_id: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    slack_team_id: str | None = None,
    rfp_id: str | None = None,
    source: str | None = None,
) -> None:
    """
    Store a procedural memory from a successful tool sequence with full provenance.
    
    This is called when a sequence of tools completes successfully,
    allowing the agent to learn effective workflows.
    
    Args:
        user_sub: User identifier (Cognito sub)
        tool_sequence: List of tool names used in order
        success: Whether the sequence was successful
        outcome: Description of the outcome
        context: Optional additional context (rfp_id, etc.)
        cognito_user_id: Cognito user identifier (for traceability - typically same as user_sub)
        slack_user_id: Slack user ID if memory originated from Slack
        slack_channel_id: Slack channel ID where memory originated
        slack_thread_ts: Slack thread timestamp where memory originated
        slack_team_id: Slack team ID
        rfp_id: RFP identifier if memory is related to an RFP
        source: Source system (e.g., "slack_agent", "slack_operator", "api")
    """
    if not user_sub or not tool_sequence:
        return
    
    try:
        workflow_name = " → ".join(tool_sequence)
        workflow_desc = f"Tool sequence: {workflow_name}"
        if outcome:
            workflow_desc += f"\nOutcome: {outcome}"
        
        memory_context = {
            "toolSequence": tool_sequence,
        }
        if context:
            memory_context.update(context)
        
        # Extract provenance from context if not explicitly provided
        final_cognito_user_id = cognito_user_id or user_sub
        final_slack_user_id = slack_user_id or (context.get("slackUserId") if context else None)
        final_slack_channel_id = slack_channel_id or (context.get("channelId") if context else None)
        final_slack_thread_ts = slack_thread_ts or (context.get("threadTs") if context else None)
        final_slack_team_id = slack_team_id or (context.get("slackTeamId") if context else None)
        final_rfp_id = rfp_id or (context.get("rfpId") if context else None)
        final_source = source or (context.get("source") if context else "tool_sequence")
        
        add_procedural_memory(
            user_sub=user_sub,
            workflow=workflow_desc,
            success=success,
            context=memory_context,
            cognito_user_id=final_cognito_user_id,
            slack_user_id=final_slack_user_id,
            slack_channel_id=final_slack_channel_id,
            slack_thread_ts=final_slack_thread_ts,
            slack_team_id=final_slack_team_id,
            rfp_id=final_rfp_id,
            source=final_source,
        )
    except Exception as e:
        log.warning("procedural_memory_store_failed", user_sub=user_sub, error=str(e))
        # Non-critical, don't raise
