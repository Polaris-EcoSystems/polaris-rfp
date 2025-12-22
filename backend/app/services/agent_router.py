"""
Agent Router - Routes requests to appropriate agents based on intent and context.

This service uses the Agent Registry to find the best agent for a given request
and handles agent handoffs with standardized message format.
"""

from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger
from .agent_message import AgentMessage, AgentResponse, UserIdentity
from .agent_registry import get_registry

log = get_logger("agent_router")


class AgentRouter:
    """
    Routes agent requests to the appropriate agent based on intent and available context.
    
    This is the central routing service that:
    1. Analyzes the request intent
    2. Determines required context
    3. Finds the best agent using the registry
    4. Handles agent handoffs
    5. Tracks routing decisions for debugging
    """
    
    def __init__(self) -> None:
        self.registry = get_registry()
    
    def route(
        self,
        *,
        intent: str,
        user_identity: UserIdentity | None = None,
        payload: dict[str, Any] | None = None,
        channel_id: str | None = None,
        thread_ts: str | None = None,
        rfp_id: str | None = None,
        source_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> AgentMessage:
        """
        Route a request to the appropriate agent.
        
        Creates an AgentMessage and determines which agent should handle it.
        
        Args:
            intent: What the user wants (e.g., "answer_question", "update_rfp")
            user_identity: Resolved user identity
            payload: Request payload/data
            channel_id: Slack channel ID (if applicable)
            thread_ts: Slack thread timestamp (if applicable)
            rfp_id: RFP ID (if applicable)
            source_agent: Which agent is making this request (for handoffs)
            correlation_id: Correlation ID for tracking related requests
        
        Returns:
            AgentMessage with target_agent set
        """
        # Build available context
        available_context: dict[str, Any] = {}
        if user_identity:
            available_context["user_identity"] = user_identity
            if user_identity.user_sub:
                available_context["user_sub"] = user_identity.user_sub
            if user_identity.email:
                available_context["email"] = user_identity.email
            if user_identity.slack_user_id:
                available_context["slack_user_id"] = user_identity.slack_user_id
        if channel_id:
            available_context["channel_id"] = channel_id
        if thread_ts:
            available_context["thread_ts"] = thread_ts
        if rfp_id:
            available_context["rfp_id"] = rfp_id
        
        # Find the best agent
        agent = self.registry.find_agent_for_intent(
            intent=intent,
            available_context=available_context,
        )
        
        if not agent:
            log.warning(
                "no_agent_found",
                intent=intent,
                available_context_keys=list(available_context.keys()),
            )
            # Default to operator_agent if no match found (it's the most capable)
            agent = self.registry.get_agent("operator_agent")
            if not agent:
                raise ValueError(f"No agent found for intent: {intent}")
        
        # Create message
        message = AgentMessage(
            intent=intent,
            user_identity=user_identity,
            payload=payload or {},
            channel_id=channel_id,
            thread_ts=thread_ts,
            rfp_id=rfp_id,
            source_agent=source_agent,
            target_agent=agent.agent_id,
            correlation_id=correlation_id,
        )
        
        log.info(
            "agent_routed",
            intent=intent,
            target_agent=agent.agent_id,
            request_id=message.request_id,
            has_user_identity=user_identity is not None,
            has_rfp_id=rfp_id is not None,
        )
        
        return message
    
    def route_from_slack_mention(
        self,
        *,
        question: str,
        slack_user_id: str | None,
        channel_id: str,
        thread_ts: str,
        rfp_id: str | None = None,
        correlation_id: str | None = None,
    ) -> AgentMessage:
        """
        Route a Slack mention to the appropriate agent.
        
        This is a convenience method that:
        1. Resolves user identity from Slack
        2. Determines intent from the question
        3. Routes to appropriate agent
        
        Args:
            question: User's question/message
            slack_user_id: Slack user ID
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp
            rfp_id: RFP ID (if known)
            correlation_id: Correlation ID
        
        Returns:
            AgentMessage ready to be handled
        """
        from .identity_service import resolve_from_slack
        
        # Resolve user identity
        user_identity = None
        if slack_user_id:
            try:
                user_identity = resolve_from_slack(slack_user_id=slack_user_id)
            except Exception as e:
                log.warning("identity_resolution_failed", slack_user_id=slack_user_id, error=str(e))
        
        # Determine intent from question
        # This is a simple heuristic - can be enhanced with ML classification
        intent = self._determine_intent_from_question(question, rfp_id=rfp_id)
        
        # Route to agent
        return self.route(
            intent=intent,
            user_identity=user_identity,
            payload={"question": question},
            channel_id=channel_id,
            thread_ts=thread_ts,
            rfp_id=rfp_id,
            correlation_id=correlation_id,
        )
    
    def _determine_intent_from_question(self, question: str, rfp_id: str | None = None) -> str:
        """
        Determine intent from user question.
        
        This is a simple keyword-based classifier. Can be enhanced with ML.
        """
        q_lower = question.lower().strip()
        
        # RFP-specific operations
        if rfp_id or any(keyword in q_lower for keyword in ["rfp", "opportunity", "proposal", "update", "analyze"]):
            if any(keyword in q_lower for keyword in ["update", "change", "modify", "set"]):
                return "update_rfp"
            if any(keyword in q_lower for keyword in ["analyze", "analysis", "insight", "summary"]):
                return "analyze_rfp"
            if any(keyword in q_lower for keyword in ["schedule", "job", "task"]):
                return "schedule_job"
            return "manage_opportunity_state"
        
        # General questions
        return "answer_question"
    
    def handle_handoff(
        self,
        *,
        from_agent: str,
        to_agent: str,
        message: AgentMessage,
        new_intent: str | None = None,
        new_payload: dict[str, Any] | None = None,
    ) -> AgentMessage:
        """
        Handle an agent-to-agent handoff.
        
        Creates a new message with parent relationship preserved.
        """
        handoff_message = message.create_handoff(
            target_agent=to_agent,
            intent=new_intent,
            payload=new_payload,
        )
        
        log.info(
            "agent_handoff",
            from_agent=from_agent,
            to_agent=to_agent,
            request_id=message.request_id,
            handoff_request_id=handoff_message.request_id,
        )
        
        return handoff_message
    
    def create_response(
        self,
        *,
        message: AgentMessage,
        success: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        handoff_to: str | None = None,
        handoff_message: AgentMessage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentResponse:
        """
        Create a standardized agent response.
        
        This is a convenience method for creating AgentResponse objects
        that are properly linked to the original message.
        """
        return AgentResponse(
            request_id=message.request_id,
            success=success,
            result=result or {},
            error=error,
            handoff_to=handoff_to,
            handoff_message=handoff_message,
            metadata=metadata or {},
        )


# Singleton instance
_router: AgentRouter | None = None


def get_router() -> AgentRouter:
    """Get the singleton agent router instance."""
    global _router
    if _router is None:
        _router = AgentRouter()
    return _router
