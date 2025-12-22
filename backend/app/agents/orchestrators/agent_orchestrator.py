"""
Agent orchestrator for routing and coordinating multiple agents.

Routes requests from user agents to appropriate tool/skill agents.
"""

from __future__ import annotations

from typing import Any

from ...agents.base.agent_interface import AgentRequest, AgentResponse
from ...agents.tools.tool_agent import ToolAgent
from ...observability.logging import get_logger

log = get_logger("agent_orchestrator")


class AgentOrchestrator:
    """
    Orchestrates multi-agent interactions.
    
    Routes requests from user agents to appropriate tool/skill agents
    and aggregates results.
    """
    
    def __init__(self):
        """Initialize orchestrator."""
        self._tool_agents: dict[str, ToolAgent] = {}
        self._skill_agents: dict[str, Any] = {}  # Skill agents - TODO: implement
    
    def register_tool_agent(self, category: str, agent: ToolAgent) -> None:
        """
        Register a tool agent for a category.
        
        Args:
            category: Tool category (e.g., "aws", "slack", "rfp")
            agent: Tool agent instance
        """
        self._tool_agents[category] = agent
        log.info("tool_agent_registered", category=category, agent_id=agent.agent_id)
    
    def get_tool_agent(self, category: str) -> ToolAgent | None:
        """
        Get tool agent for a category.
        
        Args:
            category: Tool category
        
        Returns:
            Tool agent or None if not found
        """
        return self._tool_agents.get(category)
    
    async def invoke_tool_agent(
        self,
        *,
        category: str,
        tool_name: str,
        tool_args: dict[str, Any],
        user_id: str,
    ) -> AgentResponse:
        """
        Invoke a tool agent.
        
        Args:
            category: Tool category
            tool_name: Name of tool to execute
            tool_args: Arguments for tool
            user_id: User identifier for context
        
        Returns:
            Tool execution result
        """
        agent = self.get_tool_agent(category)
        if not agent:
            return {"ok": False, "error": f"Tool agent for category {category} not found"}
        
        # Create request
        request = AgentRequest(
            user_id=user_id,
            message=f"Execute tool {tool_name}",
            context={
                "tool_name": tool_name,
                "tool_args": tool_args,
            },
        )
        
        # Execute
        response: AgentResponse = await agent.execute(request)
        
        if response.errors:
            return AgentResponse(
                text="Tool execution failed",
                errors=response.errors,
                metadata={"category": category, "tool_name": tool_name},
            )
        
        return AgentResponse(
            text=f"Tool {tool_name} executed successfully",
            metadata={"category": category, "tool_name": tool_name, "result": response.metadata.get("result", {})},
        )
    
    async def invoke_skill_agent(
        self,
        *,
        skill_id: str,
        skill_args: dict[str, Any],
        user_id: str,
    ) -> AgentResponse:
        """
        Invoke a skill agent.
        
        Args:
            skill_id: Skill identifier
            skill_args: Arguments for skill
            user_id: User identifier for context
        
        Returns:
            Skill execution result
        """
        # TODO: Implement skill agent invocation
        return AgentResponse(
            text="Skill agents not yet implemented",
            errors=["skill_agents_not_implemented"],
            metadata={"skill_id": skill_id},
        )
