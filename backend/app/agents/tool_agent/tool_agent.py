"""
Base tool agent class.

Tool agents are specialized agents for executing specific tool categories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base.agent import Agent
from ..base.agent_interface import AgentRequest, AgentResponse, Capability
from ...observability.logging import get_logger
if TYPE_CHECKING:
    from ...tools.registry.tool_registry import ToolRegistry
else:
    ToolRegistry = None

log = get_logger("tool_agent")


class ToolAgent(Agent):
    """
    Base class for tool agents.
    
    Tool agents execute tools from a specific category.
    """
    
    def __init__(
        self,
        *,
        agent_id: str,
        agent_name: str,
        tool_category: str,
        tools: Any | None = None,
    ):
        """
        Initialize tool agent.
        
        Args:
            agent_id: Unique identifier
            agent_name: Human-readable name
            tool_category: Category of tools this agent handles
            tools: Tool registry
        """
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            tools=tools,
        )
        self.tool_category = tool_category
    
    def get_capabilities(self) -> list[Capability]:
        """Get capabilities for this tool agent."""
        return [
            Capability(
                name=f"execute_{self.tool_category}_tools",
                description=f"Execute tools from {self.tool_category} category",
                required_context=["tool_name", "tool_args"],
                optional_context=[],
            ),
        ]
    
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Execute a tool request.
        
        Args:
            request: Agent request with tool_name and tool_args in payload
        
        Returns:
            Agent response with tool execution result
        """
        try:
            payload = request.context or {}
            tool_name = payload.get("tool_name", "")
            tool_args = payload.get("tool_args", {})
            
            if not tool_name:
                return AgentResponse(
                    text="Tool name is required",
                    errors=["missing_tool_name"],
                )
            
            if not self.tools:
                return AgentResponse(
                    text="Tool registry not available",
                    errors=["no_tool_registry"],
                )
            
            # Get tool from registry
            tool_info = self.tools.get_tool(tool_name)
            if not tool_info:
                return AgentResponse(
                    text=f"Tool {tool_name} not found",
                    errors=[f"tool_not_found: {tool_name}"],
                )
            
            tool_def, tool_fn = tool_info
            
            # Execute tool
            result = tool_fn(tool_args)
            
            return AgentResponse(
                text=f"Tool {tool_name} executed successfully",
                metadata={"tool_name": tool_name, "result": result},
            )
        except Exception as e:
            log.error("tool_agent_execution_failed", error=str(e), agent_id=self.agent_id)
            return AgentResponse(
                text=f"Error executing tool: {str(e)}",
                errors=[str(e)],
            )
