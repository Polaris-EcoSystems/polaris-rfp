"""
Agent Message Protocol - Standardized format for agent-to-agent communication.

This module defines the message format and protocol for agent communication,
enabling reliable handoffs, tracking, and context preservation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ....observability.logging import get_logger

log = get_logger("agent_message")


@dataclass(frozen=True)
class UserIdentity:
    """
    Immutable user identity object representing a user across platforms.
    
    This consolidates identity information from Slack, Cognito, and the web app.
    """
    # Primary identifiers
    user_sub: str | None = None  # Cognito user sub (primary)
    slack_user_id: str | None = None
    slack_team_id: str | None = None
    slack_enterprise_id: str | None = None
    email: str | None = None
    
    # Profile information
    display_name: str | None = None
    user_profile: dict[str, Any] | None = None
    slack_user: dict[str, Any] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_sub": self.user_sub,
            "slack_user_id": self.slack_user_id,
            "slack_team_id": self.slack_team_id,
            "slack_enterprise_id": self.slack_enterprise_id,
            "email": self.email,
            "display_name": self.display_name,
            "user_profile": self.user_profile,
            "slack_user": self.slack_user,
        }


@dataclass(frozen=True)
class AgentMessage:
    """
    Standardized message format for agent-to-agent communication.
    
    All agent handoffs should use this format to ensure:
    - Consistent context preservation
    - Reliable tracking and debugging
    - Support for retry and resumption
    """
    # Required fields (must come before fields with defaults)
    intent: str  # What the user wants (e.g., "answer_question", "update_rfp")
    
    # Message identification (fields with defaults)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = None  # Links related requests
    parent_request_id: str | None = None  # For handoff chains
    
    # User context (immutable)
    user_identity: UserIdentity | None = None
    
    # Payload and context information
    payload: dict[str, Any] = field(default_factory=dict)
    
    # Context information
    channel_id: str | None = None
    thread_ts: str | None = None
    rfp_id: str | None = None
    
    # Metadata
    source_agent: str | None = None  # Which agent created this message
    target_agent: str | None = None  # Which agent should handle this
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "parent_request_id": self.parent_request_id,
            "user_identity": self.user_identity.to_dict() if self.user_identity else None,
            "intent": self.intent,
            "payload": self.payload,
            "channel_id": self.channel_id,
            "thread_ts": self.thread_ts,
            "rfp_id": self.rfp_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMessage:
        """Create from dictionary."""
        user_identity = None
        if data.get("user_identity"):
            user_identity = UserIdentity(**data["user_identity"])
        
        return cls(
            intent=data.get("intent", ""),
            request_id=data.get("request_id", str(uuid.uuid4())),
            correlation_id=data.get("correlation_id"),
            parent_request_id=data.get("parent_request_id"),
            user_identity=user_identity,
            payload=data.get("payload", {}),
            channel_id=data.get("channel_id"),
            thread_ts=data.get("thread_ts"),
            rfp_id=data.get("rfp_id"),
            source_agent=data.get("source_agent"),
            target_agent=data.get("target_agent"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
        )
    
    def create_handoff(self, target_agent: str, intent: str | None = None, payload: dict[str, Any] | None = None) -> AgentMessage:
        """
        Create a handoff message to another agent.
        
        Preserves user context and creates a parent-child relationship.
        """
        return AgentMessage(
            intent=intent or self.intent,
            request_id=str(uuid.uuid4()),
            correlation_id=self.correlation_id or self.request_id,
            parent_request_id=self.request_id,
            user_identity=self.user_identity,
            payload=payload or self.payload,
            channel_id=self.channel_id,
            thread_ts=self.thread_ts,
            rfp_id=self.rfp_id,
            source_agent=self.source_agent or "unknown",
            target_agent=target_agent,
            metadata={**self.metadata, "handoff_from": self.source_agent},
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )


@dataclass(frozen=True)
class AgentResponse:
    """
    Standardized response format from agents.
    """
    request_id: str
    success: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    handoff_to: str | None = None  # If agent wants to hand off to another agent
    handoff_message: AgentMessage | None = None  # Message for handoff
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "handoff_to": self.handoff_to,
            "handoff_message": self.handoff_message.to_dict() if self.handoff_message else None,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }
