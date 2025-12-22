"""
Agent registry - moved from services.

This is the enhanced agent registry for the new architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ...observability.logging import get_logger

log = get_logger("agent_registry")


@dataclass
class AgentCapability:
    """
    Describes what an agent can do.
    """
    name: str  # Capability name (e.g., "answer_question", "update_rfp")
    description: str
    required_context: list[str] = field(default_factory=list)  # e.g., ["rfp_id", "user_identity"]
    optional_context: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] | None = None  # JSON schema for input validation
    output_schema: dict[str, Any] | None = None  # JSON schema for output


@dataclass
class RegisteredAgent:
    """
    Information about a registered agent.
    """
    agent_id: str  # Unique identifier (e.g., "slack_agent", "operator_agent")
    name: str  # Human-readable name
    description: str
    capabilities: list[AgentCapability] = field(default_factory=list)
    handler: Callable[..., Any] | None = None  # Function to call the agent (accepts any signature)
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    """
    Central registry for all agents and their capabilities.
    
    This is a singleton that should be initialized at startup.
    """
    
    _instance: AgentRegistry | None = None
    _agents: dict[str, RegisteredAgent]
    
    def __new__(cls) -> AgentRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents = {}
            cls._instance._initialize_default_agents()
        return cls._instance
    
    def _initialize_default_agents(self) -> None:
        """Register default agents at startup."""
        # Import handlers lazily to avoid circular imports
        try:
            from ...services import slack_agent
            from ...services import slack_operator_agent
            
            # Slack Agent - Conversational Q&A
            self.register_agent(
                agent_id="slack_agent",
                name="Slack Conversational Agent",
                description="Handles conversational questions and general queries in Slack",
                capabilities=[
                    AgentCapability(
                        name="answer_question",
                        description="Answer general questions and provide information",
                        required_context=["user_identity"],
                        optional_context=["channel_id", "thread_ts"],
                    ),
                    AgentCapability(
                        name="conversational_query",
                        description="Handle conversational queries without RFP context",
                        required_context=["user_identity"],
                        optional_context=["channel_id", "thread_ts"],
                    ),
                ],
                handler=slack_agent.run_slack_agent_question,
            )
            
            # Operator Agent - RFP operations
            self.register_agent(
                agent_id="operator_agent",
                name="Slack Operator Agent",
                description="Handles RFP-specific operations and state management",
                capabilities=[
                    AgentCapability(
                        name="update_rfp",
                        description="Update RFP state and opportunity data",
                        required_context=["user_identity", "rfp_id"],
                        optional_context=["channel_id", "thread_ts"],
                    ),
                    AgentCapability(
                        name="analyze_rfp",
                        description="Analyze RFP and provide insights",
                        required_context=["user_identity", "rfp_id"],
                        optional_context=["channel_id", "thread_ts"],
                    ),
                    AgentCapability(
                        name="manage_opportunity_state",
                        description="Manage opportunity state and journal entries",
                        required_context=["user_identity", "rfp_id"],
                        optional_context=["channel_id", "thread_ts"],
                    ),
                    AgentCapability(
                        name="schedule_job",
                        description="Schedule agent jobs for later execution",
                        required_context=["user_identity"],
                        optional_context=["rfp_id", "channel_id", "thread_ts"],
                    ),
                ],
                handler=slack_operator_agent.run_slack_operator_for_mention,
            )
        except ImportError as e:
            # If imports fail, register without handlers (handlers can be set later)
            log.warning("agent_handler_import_failed", error=str(e))
            
            # Register agents without handlers
            self.register_agent(
                agent_id="slack_agent",
                name="Slack Conversational Agent",
                description="Handles conversational questions and general queries in Slack",
                capabilities=[
                    AgentCapability(
                        name="answer_question",
                        description="Answer general questions and provide information",
                        required_context=["user_identity"],
                        optional_context=["channel_id", "thread_ts"],
                    ),
                ],
            )
            
            self.register_agent(
                agent_id="operator_agent",
                name="Slack Operator Agent",
                description="Handles RFP-specific operations and state management",
                capabilities=[
                    AgentCapability(
                        name="update_rfp",
                        description="Update RFP state and opportunity data",
                        required_context=["user_identity", "rfp_id"],
                        optional_context=["channel_id", "thread_ts"],
                    ),
                ],
            )
        
        log.info("agent_registry_initialized", agent_count=len(self._agents))
    
    def register_agent(
        self,
        *,
        agent_id: str,
        name: str,
        description: str,
        capabilities: list[AgentCapability] | None = None,
        handler: Callable[..., Any] | None = None,
        version: str = "1.0.0",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register an agent with the registry."""
        if agent_id in self._agents:
            log.warning("agent_already_registered", agent_id=agent_id, overwriting=True)
        
        self._agents[agent_id] = RegisteredAgent(
            agent_id=agent_id,
            name=name,
            description=description,
            capabilities=capabilities or [],
            handler=handler,
            version=version,
            metadata=metadata or {},
        )
        
        log.info("agent_registered", agent_id=agent_id, name=name, capability_count=len(capabilities or []))
    
    def get_agent(self, agent_id: str) -> RegisteredAgent | None:
        """Get agent by ID."""
        return self._agents.get(agent_id)
    
    def list_agents(self) -> list[RegisteredAgent]:
        """List all registered agents."""
        return list(self._agents.values())
    
    def find_agents_by_capability(self, capability_name: str) -> list[RegisteredAgent]:
        """Find all agents that have a specific capability."""
        matching: list[RegisteredAgent] = []
        for agent in self._agents.values():
            for cap in agent.capabilities:
                if cap.name == capability_name:
                    matching.append(agent)
                    break
        return matching
    
    def find_agent_for_intent(
        self,
        intent: str,
        *,
        required_context: list[str] | None = None,
        available_context: dict[str, Any] | None = None,
    ) -> RegisteredAgent | None:
        """
        Find the best agent for a given intent and available context.
        
        Returns the first agent that:
        1. Has a capability matching the intent
        2. Has all required context available
        """
        required = set(required_context or [])
        available = set((available_context or {}).keys())
        
        # First, try exact intent match
        for agent in self._agents.values():
            for cap in agent.capabilities:
                if cap.name == intent:
                    # Check if required context is available
                    cap_required = set(cap.required_context)
                    # Also check if any explicitly required context is available
                    if cap_required.issubset(available) and required.issubset(available):
                        return agent
        
        # If no exact match, try capability name matching
        for agent in self._agents.values():
            for cap in agent.capabilities:
                if intent.startswith(cap.name) or cap.name in intent:
                    cap_required = set(cap.required_context)
                    # Also check if any explicitly required context is available
                    if cap_required.issubset(available) and required.issubset(available):
                        return agent
        
        return None
    
    def get_capability_info(self, capability_name: str) -> AgentCapability | None:
        """Get information about a specific capability."""
        for agent in self._agents.values():
            for cap in agent.capabilities:
                if cap.name == capability_name:
                    return cap
        return None


# Singleton instance
def get_registry() -> AgentRegistry:
    """Get the singleton agent registry instance."""
    return AgentRegistry()
