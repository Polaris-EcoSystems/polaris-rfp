"""
Base agent class with common functionality.

All agents inherit from this base class.
"""

from __future__ import annotations

from typing import Any

from .agent_interface import AgentInterface, AgentRequest, AgentResponse, Capability
from ...observability.logging import get_logger

# Type-only imports to avoid circular dependencies
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...memory.core.memory_interface import AgentMemory
    from ...tools.registry.tool_registry import ToolRegistry
    from ...shared.context.context_builder import ContextBuilder
else:
    # Runtime imports
    AgentMemory = None  # Will be imported when needed
    ToolRegistry = None
    ContextBuilder = None


def get_agent_capability_prompt() -> str:
    """
    Get the capability discovery prompt section for agents.
    
    This should be included in agent system prompts to enable
    capability discovery and introspection.
    """
    try:
        from ...shared.introspection.prompt_helper import get_capability_prompt_section
        return get_capability_prompt_section()
    except Exception:
        return "Capability introspection system not available."

log = get_logger("agent_base")


class Agent(AgentInterface):
    """
    Base agent class with memory, tools, and execution.
    
    All agents should inherit from this class and implement
    the execute method.
    """
    
    def __init__(
        self,
        *,
        agent_id: str,
        agent_name: str,
        memory: Any | None = None,
        tools: Any | None = None,
        context_builder: Any | None = None,
    ):
        """
        Initialize agent.
        
        Args:
            agent_id: Unique identifier for this agent
            agent_name: Human-readable name
            memory: Memory interface (optional)
            tools: Tool registry (optional)
            context_builder: Context builder (optional)
        """
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._memory = memory
        self._tools = tools
        self._context_builder = context_builder
    
    @property
    def agent_id(self) -> str:
        """Unique identifier for this agent."""
        return self._agent_id
    
    @property
    def agent_name(self) -> str:
        """Human-readable name for this agent."""
        return self._agent_name
    
    @property
    def memory(self) -> Any | None:
        """Memory interface for this agent."""
        return self._memory
    
    @property
    def tools(self) -> Any | None:
        """Tool registry for this agent."""
        return self._tools
    
    @property
    def context_builder(self) -> Any | None:
        """Context builder for this agent."""
        return self._context_builder
    
    def get_capabilities(self) -> list[Capability]:
        """
        Get list of capabilities this agent provides.
        
        Override in subclasses to return specific capabilities.
        """
        return []
    
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Execute a request and return a response.
        
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement execute()")
    
    def build_context(self, request: AgentRequest) -> str:
        """
        Build context for the agent request.
        
        Uses the context builder if available.
        """
        if self._context_builder:
            return self._context_builder.build(request)
        return ""
