"""
Agent interfaces and protocols.

Defines the core interfaces that all agents must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ...observability.logging import get_logger

log = get_logger("agent_interface")


@dataclass
class AgentRequest:
    """Request to an agent."""
    user_id: str
    message: str
    context: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class AgentResponse:
    """Response from an agent."""
    text: str
    blocks: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    errors: list[str] | None = None


@dataclass
class Capability:
    """Describes an agent capability."""
    name: str
    description: str
    required_context: list[str]
    optional_context: list[str]


class AgentInterface(ABC):
    """Base interface for all agents."""
    
    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique identifier for this agent."""
        pass
    
    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name for this agent."""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> list[Capability]:
        """Get list of capabilities this agent provides."""
        pass
    
    @abstractmethod
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Execute a request and return a response."""
        pass
