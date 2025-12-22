"""
Factory for creating user agents.

Manages user agent instances and persistence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .user_agent import UserAgent
from ...observability.logging import get_logger
if TYPE_CHECKING:
    from ...memory.core.memory_manager import MemoryManager
    from ...tools.registry.tool_registry import ToolRegistry
    from ...shared.context.context_builder import ContextBuilder
else:
    MemoryManager = None
    ToolRegistry = None
    ContextBuilder = None

log = get_logger("user_agent_factory")


class UserAgentFactory:
    """
    Factory for creating and managing user agents.
    
    Handles:
    - Creating new user agents
    - Loading existing user agents
    - Caching agent instances
    """
    
    def __init__(self):
        """Initialize factory."""
        self._agents: dict[str, UserAgent] = {}
        self._tool_registry: ToolRegistry | None = None
        self._context_builder: ContextBuilder | None = None
        self._orchestrator: Any | None = None
    
    def set_tool_registry(self, registry: Any) -> None:
        """Set the global tool registry."""
        self._tool_registry = registry
    
    def set_context_builder(self, builder: Any) -> None:
        """Set the context builder."""
        self._context_builder = builder
    
    def set_orchestrator(self, orchestrator: Any) -> None:
        """Set the agent orchestrator."""
        self._orchestrator = orchestrator
    
    def get_or_create_agent(
        self,
        *,
        user_id: str,
        user_sub: str | None = None,
    ) -> UserAgent:
        """
        Get or create a user agent for a user.
        
        Args:
            user_id: User identifier
            user_sub: Cognito user sub (optional)
        
        Returns:
            UserAgent instance
        """
        # Check cache first
        cache_key = user_sub or user_id
        if cache_key in self._agents:
            return self._agents[cache_key]
        
        # Create new agent
        from ...memory.core.memory_manager import MemoryManager
        memory = MemoryManager(user_sub=user_sub or user_id)
        
        agent = UserAgent(
            user_id=user_id,
            user_sub=user_sub,
            memory=memory,
            tools=self._tool_registry,
            context_builder=self._context_builder,
            orchestrator=self._orchestrator,
        )
        
        # Cache it
        self._agents[cache_key] = agent
        
        log.info("user_agent_created", user_id=user_id, user_sub=user_sub)
        
        return agent
    
    def get_agent(self, user_id: str, user_sub: str | None = None) -> UserAgent | None:
        """
        Get existing agent from cache.
        
        Args:
            user_id: User identifier
            user_sub: Cognito user sub (optional)
        
        Returns:
            UserAgent instance or None if not found
        """
        cache_key = user_sub or user_id
        return self._agents.get(cache_key)
    
    def clear_cache(self) -> None:
        """Clear agent cache."""
        self._agents.clear()


# Global factory instance
_factory: UserAgentFactory | None = None


def get_factory() -> UserAgentFactory:
    """Get the global user agent factory."""
    global _factory
    if _factory is None:
        _factory = UserAgentFactory()
    return _factory
