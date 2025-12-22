"""
User-specific agent context management.

This module provides persistent context management for each user's interactions
with the Slack operator agent, allowing the agent to maintain continuity
across conversations and build rich user-specific context over time.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..observability.logging import get_logger
from .agent_memory_retrieval import get_memories_for_context
from .agent_context_builder import build_user_context
from .identity_service import resolve_from_slack

log = get_logger("user_agent_context")


def build_user_agent_context(
    *,
    slack_user_id: str | None = None,
    user_sub: str | None = None,
    user_profile: dict[str, Any] | None = None,
    user_display_name: str | None = None,
    user_email: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
    current_query: str | None = None,
    rfp_id: str | None = None,
    include_recent_interactions: bool = True,
    include_preferences: bool = True,
    include_work_patterns: bool = True,
) -> str:
    """
    Build comprehensive user-specific agent context that ties together
    all interactions with this user.
    
    This creates a "user agent" that has robust context on the user,
    their preferences, past interactions, and work patterns.
    
    Args:
        slack_user_id: Slack user ID
        user_sub: Cognito user sub (if known)
        user_profile: User profile dict (if available)
        user_display_name: User display name
        user_email: User email
        channel_id: Current channel (for context)
        thread_ts: Current thread (for context)
        current_query: Current user query (for relevance filtering)
        rfp_id: Current RFP ID (if applicable)
        include_recent_interactions: Include recent conversation history
        include_preferences: Include user preferences and settings
        include_work_patterns: Include detected work patterns
    
    Returns:
        Formatted context string for inclusion in agent prompts
    """
    context_parts: list[str] = []
    
    # Resolve user identity if not fully provided
    if not user_sub and slack_user_id:
        try:
            identity = resolve_from_slack(slack_user_id=slack_user_id)
            user_sub = identity.user_sub
            if not user_profile:
                user_profile = identity.user_profile
            if not user_display_name:
                user_display_name = identity.display_name
            if not user_email:
                user_email = identity.email
        except Exception as e:
            log.warning("user_identity_resolution_failed", slack_user_id=slack_user_id, error=str(e))
    
    if not user_sub:
        # Can't build rich context without user_sub
        return ""
    
    # SECTION 1: User Identity and Profile
    user_ctx = build_user_context(
        user_profile=user_profile,
        user_display_name=user_display_name,
        user_email=user_email,
        user_id=slack_user_id,
    )
    if user_ctx:
        context_parts.append("=== USER_IDENTITY ===")
        context_parts.append(user_ctx)
        context_parts.append("")
    
    # SECTION 2: Recent Interactions (Query-Aware)
    if include_recent_interactions:
        try:
            # Get recent episodic memories (conversations) for this user
            # Use current_query for relevance filtering
            recent_memories = get_memories_for_context(
                user_sub=user_sub,
                rfp_id=rfp_id,
                query_text=current_query,
                memory_types=["EPISODIC"],
                limit=10,  # Get top 10 most relevant recent interactions
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
            
            if recent_memories:
                context_parts.append("=== RECENT_INTERACTIONS ===")
                context_parts.append("Recent conversations and interactions with this user:")
                context_parts.append("")
                
                for mem in recent_memories[:8]:  # Show top 8
                    content = mem.get("content", "")
                    summary = mem.get("summary", "")
                    metadata = mem.get("metadata", {})
                    created_at = mem.get("createdAt", "")
                    
                    # Extract key info
                    user_msg = metadata.get("userMessage", "")
                    agent_resp = metadata.get("agentResponse", "")
                    
                    if user_msg or agent_resp:
                        interaction_text = f"- User: {user_msg[:200] if user_msg else '(no message)'}"
                        if agent_resp:
                            interaction_text += f"\n  Agent: {agent_resp[:200]}"
                        if created_at:
                            # Format timestamp for readability
                            try:
                                if isinstance(created_at, (int, float)):
                                    # Unix timestamp
                                    dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
                                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                                elif isinstance(created_at, str):
                                    # ISO format string
                                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                                else:
                                    formatted_time = str(created_at)
                                interaction_text += f" [{formatted_time}]"
                            except Exception:
                                # Fallback to raw timestamp if parsing fails
                                interaction_text += f" [{created_at}]"
                        context_parts.append(interaction_text)
                    elif summary:
                        context_parts.append(f"- {summary[:300]}")
                    elif content:
                        context_parts.append(f"- {content[:300]}")
                
                context_parts.append("")
        except Exception as e:
            log.warning("recent_interactions_context_failed", user_sub=user_sub, error=str(e))
    
    # SECTION 3: User Preferences and Patterns
    if include_preferences:
        try:
            # Get semantic memories (preferences, facts about user)
            semantic_memories = get_memories_for_context(
                user_sub=user_sub,
                query_text=current_query,
                memory_types=["SEMANTIC"],
                limit=15,
            )
            
            if semantic_memories:
                context_parts.append("=== USER_PREFERENCES_AND_FACTS ===")
                context_parts.append("Known preferences, facts, and patterns about this user:")
                context_parts.append("")
                
                for mem in semantic_memories[:10]:
                    content = mem.get("content", "")
                    summary = mem.get("summary", "")
                    metadata = mem.get("metadata", {})
                    
                    # Semantic memories often have key-value structure
                    key = metadata.get("key", "")
                    value = metadata.get("value", "")
                    
                    if key and value:
                        context_parts.append(f"- {key}: {value}")
                    elif summary:
                        context_parts.append(f"- {summary}")
                    elif content:
                        context_parts.append(f"- {content[:200]}")
                
                context_parts.append("")
        except Exception as e:
            log.warning("preferences_context_failed", user_sub=user_sub, error=str(e))
    
    # SECTION 4: Work Patterns and Procedures
    if include_work_patterns:
        try:
            # Get procedural memories (how this user typically works)
            procedural_memories = get_memories_for_context(
                user_sub=user_sub,
                rfp_id=rfp_id,
                query_text=current_query,
                memory_types=["PROCEDURAL"],
                limit=8,
            )
            
            if procedural_memories:
                context_parts.append("=== WORK_PATTERNS ===")
                context_parts.append("How this user typically works (successful patterns):")
                context_parts.append("")
                
                for mem in procedural_memories[:5]:
                    summary = mem.get("summary", "")
                    metadata = mem.get("metadata", {})
                    tool_seq = metadata.get("toolSequence", [])
                    success = metadata.get("success", True)
                    
                    pattern_text = ""
                    if tool_seq and isinstance(tool_seq, list):
                        pattern_text = f"Pattern: {' → '.join([str(t) for t in tool_seq[:5]])}"
                        if not success:
                            pattern_text += " (unsuccessful - avoid)"
                    elif summary:
                        pattern_text = summary
                    
                    if pattern_text:
                        context_parts.append(f"- {pattern_text}")
                
                context_parts.append("")
        except Exception as e:
            log.warning("work_patterns_context_failed", user_sub=user_sub, error=str(e))
    
    # SECTION 5: Cross-Conversation Context
    # If this is a DM, include context from other channels/threads
    if channel_id and thread_ts:
        try:
            # Get memories from other channels/threads for this user
            cross_context_memories = get_memories_for_context(
                user_sub=user_sub,
                rfp_id=rfp_id,
                query_text=current_query,
                memory_types=["EPISODIC"],
                limit=5,
                channel_id=None,  # Don't filter by channel - get from other channels
                thread_ts=None,   # Don't filter by thread - get from other threads
            )
            
            # Filter out current channel/thread
            filtered_memories = []
            for mem in cross_context_memories:
                mem_metadata = mem.get("metadata", {})
                mem_channel = mem_metadata.get("channelId") or mem_metadata.get("slackChannelId")
                mem_thread = mem_metadata.get("threadTs") or mem_metadata.get("slackThreadTs")
                
                # Include if from different channel/thread
                if mem_channel != channel_id or mem_thread != thread_ts:
                    filtered_memories.append(mem)
            
            if filtered_memories:
                context_parts.append("=== RELATED_CONTEXT_FROM_OTHER_CONVERSATIONS ===")
                context_parts.append("Relevant context from other channels/threads:")
                context_parts.append("")
                
                for mem in filtered_memories[:3]:
                    summary = mem.get("summary", "")
                    metadata = mem.get("metadata", {})
                    user_msg = metadata.get("userMessage", "")
                    
                    if user_msg:
                        context_parts.append(f"- {user_msg[:200]}")
                    elif summary:
                        context_parts.append(f"- {summary[:200]}")
                
                context_parts.append("")
        except Exception as e:
            log.warning("cross_context_failed", user_sub=user_sub, error=str(e))
    
    # Add context generation timestamp
    if context_parts:
        context_parts.append("")
        context_parts.append("=== CONTEXT_GENERATED ===")
        context_parts.append(f"Generated at: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}")
        context_parts.append(f"Generation time (ms): {int(time.time() * 1000)}")
    
    return "\n".join(context_parts).strip()


def get_user_conversation_summary(
    *,
    user_sub: str,
    limit: int = 5,
) -> str:
    """
    Get a brief summary of recent conversations with a user.
    
    Useful for quick context when starting a new interaction.
    """
    try:
        memories = get_memories_for_context(
            user_sub=user_sub,
            memory_types=["EPISODIC"],
            limit=limit,
        )
        
        if not memories:
            return ""
        
        summary_parts: list[str] = []
        for mem in memories:
            metadata = mem.get("metadata", {})
            user_msg = metadata.get("userMessage", "")
            if user_msg:
                summary_parts.append(f"- {user_msg[:150]}")
        
        return "\n".join(summary_parts) if summary_parts else ""
    except Exception as e:
        log.warning("conversation_summary_failed", user_sub=user_sub, error=str(e))
        return ""
