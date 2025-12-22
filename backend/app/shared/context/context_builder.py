"""
Context builder for agents.

This will be implemented by consolidating existing context building logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ...agents.base.agent_interface import AgentRequest


class ContextBuilder(ABC):
    """Builds context for agent requests."""
    
    @abstractmethod
    def build(self, request: AgentRequest) -> str:
        """
        Build context string for the request.
        
        Args:
            request: Agent request with user_id, message, and context
        
        Returns:
            Context string for the agent
        """
        pass
    
    def build_with_metadata(self, request: AgentRequest) -> dict[str, Any]:
        """
        Build context with metadata.
        
        Args:
            request: Agent request
        
        Returns:
            Dict with 'context' (str) and optional metadata
        """
        return {
            "context": self.build(request),
            "request_id": request.request_id if hasattr(request, "request_id") else None,
        }
