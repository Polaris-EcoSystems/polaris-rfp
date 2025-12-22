from __future__ import annotations

from typing import Any

from .agent_memory import add_episodic_memory, add_procedural_memory, update_existing_memory
from .agent_memory_relationships import add_relationship, auto_detect_relationships
from .agent_message_history import link_message_to_memory, store_message
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
    # Autonomous decision support
    use_autonomous_decision: bool = False,
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
        use_autonomous_decision: If True, use autonomous decision making to determine if/how to store
    """
    if not user_sub:
        return  # Can't store without user identifier
    
    try:
        # If autonomous decision enabled, check if we should store
        if use_autonomous_decision:
            from .agent_memory_autonomous import should_store_memory_autonomous
            from .agent_memory import update_semantic_memory, add_procedural_memory as add_proc_memory
            from .agent_memory_db import MemoryType
            
            decision = should_store_memory_autonomous(
                user_message=user_message,
                agent_response=agent_response,
                context=context or {},
                user_sub=user_sub,
            )
            
            if decision:
                memory_type = decision.get("memoryType", "")
                content = decision.get("content", "")
                is_update = decision.get("isUpdate", False)
                update_memory_id = decision.get("updateMemoryId")
                
                # Extract provenance
                final_cognito_user_id = cognito_user_id or user_sub
                final_slack_user_id = slack_user_id or (context.get("slackUserId") if context else None)
                final_slack_channel_id = slack_channel_id or (context.get("channelId") if context else None)
                final_slack_thread_ts = slack_thread_ts or (context.get("threadTs") if context else None)
                final_slack_team_id = slack_team_id or (context.get("slackTeamId") if context else None)
                final_rfp_id = rfp_id or (context.get("rfpId") if context else None)
                final_source = source or (context.get("source") if context else "agent_interaction_autonomous")
                
                if is_update and update_memory_id:
                    # Update existing memory
                    try:
                        # Use metadata from decision if available
                        update_memory_type = decision.get("updateMemoryType", memory_type)
                        update_scope_id = decision.get("updateScopeId", f"USER#{user_sub}")
                        update_created_at = decision.get("updateCreatedAt", "")
                        
                        # If metadata not available, find the memory
                        if not update_created_at:
                            from .agent_memory_db import find_memory_by_id
                            existing_mem = find_memory_by_id(
                                memory_id=update_memory_id,
                                scope_ids=[update_scope_id],
                                memory_types=[update_memory_type] if update_memory_type else None,
                            )
                            if existing_mem:
                                update_memory_type = existing_mem.get("memoryType", memory_type)
                                update_scope_id = existing_mem.get("scopeId", update_scope_id)
                                update_created_at = existing_mem.get("createdAt", "")
                        
                        if update_created_at:
                            update_existing_memory(
                                memory_id=update_memory_id,
                                memory_type=update_memory_type,
                                scope_id=update_scope_id,
                                created_at=update_created_at,
                                content=content,
                                reason="Autonomous update from agent interaction",
                                user_sub=user_sub,
                            )
                            return
                    except Exception as e:
                        log.warning("autonomous_memory_update_failed", error=str(e), memory_id=update_memory_id)
                        # Fall through to create new memory
                
                # Create new memory based on decision
                if memory_type == MemoryType.SEMANTIC:
                    key = decision.get("key")
                    value = decision.get("value")
                    if key and value is not None:
                        update_semantic_memory(
                            user_sub=user_sub,
                            key=key,
                            value=value,
                            cognito_user_id=final_cognito_user_id,
                            slack_user_id=final_slack_user_id,
                            slack_channel_id=final_slack_channel_id,
                            slack_thread_ts=final_slack_thread_ts,
                            slack_team_id=final_slack_team_id,
                            rfp_id=final_rfp_id,
                            source=final_source,
                        )
                        return
                
                elif memory_type == MemoryType.PROCEDURAL:
                    add_proc_memory(
                        user_sub=user_sub,
                        workflow=content,
                        success=True,  # Assume success if agent decided to remember
                        context=context,
                        cognito_user_id=final_cognito_user_id,
                        slack_user_id=final_slack_user_id,
                        slack_channel_id=final_slack_channel_id,
                        slack_thread_ts=final_slack_thread_ts,
                        slack_team_id=final_slack_team_id,
                        rfp_id=final_rfp_id,
                        source=final_source,
                    )
                    return
                
                # Default to episodic if type not handled or if decision says EPISODIC
                if memory_type == MemoryType.EPISODIC or not memory_type:
                    # Fall through to standard episodic storage
                    pass
                else:
                    # Unknown type or decision said not to store
                    return
        
        # Standard episodic memory storage (default behavior)
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
        
        # Store messages in history
        user_msg_obj = None
        agent_msg_obj = None
        try:
            user_msg_obj = store_message(
                user_sub=user_sub,
                role="user",
                content=user_message,
                metadata={
                    "slackUserId": final_slack_user_id,
                    "slackChannelId": final_slack_channel_id,
                    "slackThreadTs": final_slack_thread_ts,
                    "slackTeamId": final_slack_team_id,
                    "rfpId": final_rfp_id,
                },
            )
            agent_msg_obj = store_message(
                user_sub=user_sub,
                role="assistant",
                content=agent_response,
                metadata={
                    "slackChannelId": final_slack_channel_id,
                    "slackThreadTs": final_slack_thread_ts,
                    "rfpId": final_rfp_id,
                },
            )
        except Exception as e:
            log.warning("message_history_store_failed", error=str(e), user_sub=user_sub)
            # Non-critical, continue
        
        memory = add_episodic_memory(
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
        
        # Link messages to memory
        if user_msg_obj and memory:
            try:
                link_message_to_memory(
                    message_id=user_msg_obj.get("messageId", ""),
                    user_sub=user_sub,
                    timestamp=user_msg_obj.get("timestamp", ""),
                    memory_id=memory.get("memoryId", ""),
                )
            except Exception:
                pass  # Non-critical
        
        if agent_msg_obj and memory:
            try:
                link_message_to_memory(
                    message_id=agent_msg_obj.get("messageId", ""),
                    user_sub=user_sub,
                    timestamp=agent_msg_obj.get("timestamp", ""),
                    memory_id=memory.get("memoryId", ""),
                )
            except Exception:
                pass  # Non-critical
        
        # Auto-create relationships to related memories
        try:
            relationships = auto_detect_relationships(memory=memory, user_sub=user_sub)
            for rel in relationships:
                add_relationship(
                    from_memory_id=memory.get("memoryId", ""),
                    from_memory_type=memory.get("memoryType", ""),
                    from_scope_id=memory.get("scopeId", ""),
                    from_created_at=memory.get("createdAt", ""),
                    to_memory_id=rel["to_memory_id"],
                    to_memory_type=rel["to_memory_type"],
                    to_scope_id=rel["to_scope_id"],
                    to_created_at=rel["to_created_at"],
                    relationship_type=rel["relationship_type"],
                    bidirectional=True,
                )
        except Exception as e:
            log.warning("auto_relationship_creation_failed", error=str(e), memory_id=memory.get("memoryId"))
            # Non-critical, continue
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
