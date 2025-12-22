"""
Personalized user agent implementation.

Each user gets their own agent instance with personalized memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base.agent import Agent
from ..base.agent_interface import AgentRequest, AgentResponse, Capability
from ...observability.logging import get_logger
if TYPE_CHECKING:
    from ...memory.core.memory_manager import MemoryManager
    from ...tools.registry.tool_registry import ToolRegistry
    from ...shared.context.context_builder import ContextBuilder
else:
    MemoryManager = None
    ToolRegistry = None
    ContextBuilder = None

log = get_logger("user_agent")


class UserAgent(Agent):
    """
    Personalized agent for a specific user.
    
    Each user gets their own UserAgent instance with:
    - User-specific memory
    - Access to all tools via tool agents
    - Personalized context building
    """
    
    def __init__(
        self,
        *,
        user_id: str,
        user_sub: str | None = None,
        memory: Any | None = None,
        tools: Any | None = None,
        context_builder: Any | None = None,
        orchestrator: Any | None = None,  # AgentOrchestrator - avoid circular import
    ):
        """
        Initialize user agent.
        
        Args:
            user_id: User identifier (Slack user ID or similar)
            user_sub: Cognito user sub (for memory scope)
            memory: Memory manager (will create if not provided)
            tools: Tool registry (will get global if not provided)
            context_builder: Context builder (optional)
            orchestrator: Agent orchestrator for invoking tool agents
        """
        agent_id = f"user_agent_{user_id}"
        agent_name = f"User Agent ({user_id})"
        
        # Create memory manager if not provided
        if memory is None:
            from ...memory.core.memory_manager import MemoryManager
            memory = MemoryManager(user_sub=user_sub or user_id)
        
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            memory=memory,
            tools=tools,
            context_builder=context_builder,
        )
        
        self.user_id = user_id
        self.user_sub = user_sub or user_id
        self._orchestrator = orchestrator
    
    def get_capabilities(self) -> list[Capability]:
        """Get capabilities of this user agent."""
        return [
            Capability(
                name="answer_question",
                description="Answer general questions using user's memory and context",
                required_context=["user_id"],
                optional_context=["channel_id", "thread_ts", "rfp_id"],
            ),
            Capability(
                name="conversational_query",
                description="Handle conversational queries with personalized context",
                required_context=["user_id"],
                optional_context=["channel_id", "thread_ts"],
            ),
            Capability(
                name="invoke_tool",
                description="Invoke tool agents for specific tasks",
                required_context=["user_id", "tool_name"],
                optional_context=["tool_args"],
            ),
            Capability(
                name="invoke_skill",
                description="Invoke skill agents for complex workflows",
                required_context=["user_id", "skill_id"],
                optional_context=["skill_args"],
            ),
        ]
    
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Execute a user request.
        
        The user agent:
        1. Builds personalized context
        2. Determines if tool/skill agents are needed
        3. Invokes orchestrator if needed
        4. Returns response
        """
        try:
            # Build personalized context
            context = self.build_context(request)
            
            # For now, return a simple response
            # TODO: Integrate with actual agent execution logic
            return AgentResponse(
                text=f"User agent for {self.user_id} received: {request.message}",
                metadata={"user_id": self.user_id, "context_length": len(context)},
            )
        except Exception as e:
            log.error("user_agent_execution_failed", error=str(e), user_id=self.user_id)
            return AgentResponse(
                text="I encountered an error processing your request.",
                errors=[str(e)],
            )
    
    def invoke_tool_agent(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """
        Invoke a tool agent via orchestrator.
        
        Args:
            tool_name: Name of tool agent to invoke
            args: Arguments for the tool
        
        Returns:
            Result from tool agent
        """
        if not self._orchestrator:
            raise ValueError("Orchestrator not available")
        
        # TODO: Implement orchestrator invocation
        return {"ok": False, "error": "orchestrator_not_implemented"}
    
    def invoke_skill_agent(self, skill_id: str, args: dict[str, Any]) -> dict[str, Any]:
        """
        Invoke a skill agent via orchestrator.
        
        Args:
            skill_id: ID of skill to execute
            args: Arguments for the skill
        
        Returns:
            Result from skill agent
        """
        if not self._orchestrator:
            raise ValueError("Orchestrator not available")
        
        # TODO: Implement orchestrator invocation
        return {"ok": False, "error": "orchestrator_not_implemented"}
