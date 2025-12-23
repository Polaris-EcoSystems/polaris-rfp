"""
Enhanced context building for AI agent prompts.

This module provides advanced context enhancement including:
- Query-aware context retrieval
- Context prioritization and weighting
- Structured context formatting
- Smart context compression
- Relevance-based filtering
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...ai.context import clip_text
from .agent_context_builder import (
    build_memory_context,
    build_thread_context,
    build_user_context,
)
from ...memory.core.agent_memory_keywords import extract_keywords


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_query_keywords(query: str, max_keywords: int = 10) -> list[str]:
    """
    Extract keywords from user query for context-aware retrieval.
    
    Args:
        query: User's question/request
        max_keywords: Maximum number of keywords to extract
    
    Returns:
        List of extracted keywords
    """
    if not query or not isinstance(query, str):
        return []
    
    keywords = extract_keywords(query, max_keywords=max_keywords)
    return [str(kw).strip().lower() for kw in keywords if str(kw).strip()]


def build_structured_context(
    *,
    user_profile: dict[str, Any] | None = None,
    user_display_name: str | None = None,
    user_email: str | None = None,
    user_id: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
    rfp_id: str | None = None,
    user_query: str | None = None,
    max_total_chars: int = 50000,
    prioritize_recent: bool = True,
) -> str:
    """
    Build structured, prioritized context optimized for AI agent prompts.
    
    Uses query-aware retrieval when a user query is provided to fetch
    the most relevant context first.
    
    Args:
        user_profile: User profile dict
        user_display_name: User display name
        user_email: User email
        user_id: Slack user ID
        channel_id: Slack channel ID
        thread_ts: Slack thread timestamp
        rfp_id: RFP ID if known
        user_query: User's current question/request (for query-aware context)
        max_total_chars: Maximum total context length
        prioritize_recent: Whether to prioritize recent context
    
    Returns:
        Structured context string with clear sections and priorities
    """
    context_sections: list[dict[str, Any]] = []
    
    # Extract user_sub for scope
    user_sub: str | None = None
    if user_profile:
        user_sub = str(user_profile.get("_id") or user_profile.get("userSub") or "").strip() or None
    
    # Extract query keywords for semantic search
    query_keywords: list[str] = []
    if user_query:
        query_keywords = extract_query_keywords(user_query, max_keywords=10)
    
    # SECTION 1: USER IDENTITY (Highest Priority - Always Include)
    user_ctx = build_user_context(
        user_profile=user_profile,
        user_display_name=user_display_name,
        user_email=user_email,
        user_id=user_id,
    )
    if user_ctx:
        context_sections.append({
            "priority": 1,
            "title": "USER_IDENTITY",
            "content": user_ctx,
            "weight": 1.0,  # Always full weight
            "source": "user_profile",
        })
    
    # SECTION 2: CONVERSATION CONTEXT (High Priority - Recent Thread)
    thread_ctx = build_thread_context(
        channel_id=channel_id,
        thread_ts=thread_ts,
        limit=100,
    )
    if thread_ctx:
        context_sections.append({
            "priority": 2,
            "title": "CONVERSATION_HISTORY",
            "content": thread_ctx,
            "weight": 0.9,  # Very important
            "source": "slack_thread",
        })
    
    # SECTION 3: RELEVANT MEMORIES (Query-Aware)
    # Use query keywords to find most relevant memories
    memory_ctx = build_memory_context(
        user_sub=user_sub,
        rfp_id=rfp_id,
        query_text=user_query if user_query else None,  # Pass query for semantic search
        limit=15,  # Get more memories, we'll prioritize
    )
    if memory_ctx:
        # Boost weight if query keywords match memory topics
        weight = 0.85
        if query_keywords and memory_ctx:
            # Higher weight if query seems related
            weight = 0.95
        
        context_sections.append({
            "priority": 3,
            "title": "RELEVANT_MEMORIES",
            "content": memory_ctx,
            "weight": weight,
            "source": "agent_memory",
        })
    
    # SECTION 4: CURRENT RFP STATE (If RFP-scoped)
    if rfp_id:
        from .agent_context_builder import build_rfp_state_context
        rfp_ctx = build_rfp_state_context(rfp_id=rfp_id, journal_limit=10, events_limit=10)
        if rfp_ctx:
            # Boost weight if query mentions RFP-related terms
            weight = 0.8
            rfp_keywords = ["rfp", "opportunity", "proposal", "client", "project", "bid"]
            if query_keywords and any(kw in " ".join(query_keywords) for kw in rfp_keywords):
                weight = 0.9
            
            context_sections.append({
                "priority": 4,
                "title": "RFP_STATE",
                "content": rfp_ctx,
                "weight": weight,
                "source": "opportunity_state",
            })
            
            # SECTION 5: RELATED RFPs (Lower Priority)
            from .agent_context_builder import build_related_rfps_context
            related_ctx = build_related_rfps_context(rfp_id=rfp_id, limit=5)
            if related_ctx:
                context_sections.append({
                    "priority": 5,
                    "title": "RELATED_RFPS",
                    "content": related_ctx,
                    "weight": 0.5,  # Reference only
                    "source": "related_opportunities",
                })
            
            # SECTION 6: RECENT JOBS (Lower Priority)
            from .agent_context_builder import build_recent_jobs_context
            jobs_ctx = build_recent_jobs_context(rfp_id=rfp_id, limit=10)
            if jobs_ctx:
                context_sections.append({
                    "priority": 6,
                    "title": "RECENT_JOBS",
                    "content": jobs_ctx,
                    "weight": 0.6,
                    "source": "agent_jobs",
                })
            
            # SECTION 7: CROSS-THREAD CONTEXT (Lowest Priority)
            from .agent_context_builder import build_cross_thread_context
            cross_thread_ctx = build_cross_thread_context(
                rfp_id=rfp_id,
                current_channel_id=channel_id,
                current_thread_ts=thread_ts,
                limit=5,
            )
            if cross_thread_ctx:
                context_sections.append({
                    "priority": 7,
                    "title": "CROSS_THREAD_CONTEXT",
                    "content": cross_thread_ctx,
                    "weight": 0.4,  # Lowest priority
                    "source": "other_threads",
                })
    
    # Build structured output with clear sections
    output_parts: list[str] = []
    
    # Sort by priority (lower number = higher priority)
    context_sections.sort(key=lambda x: x["priority"])
    
    current_length = 0
    for section in context_sections:
        section_content = section["content"]
        section_title = section["title"]
        section_weight = section["weight"]
        
        # Estimate section length
        section_len = len(section_content) + len(section_title) + 50  # Overhead
        
        # Skip low-weight sections if we're running out of space
        remaining_space = max_total_chars - current_length
        if section_weight < 0.5 and remaining_space < 2000:
            continue  # Skip low-priority sections if space is tight
        
        # Truncate section if needed (apply weight-based truncation)
        if current_length + section_len > max_total_chars:
            available_space = max_total_chars - current_length - 200  # Reserve some buffer
            if available_space > 500:  # Only include if we have meaningful space
                # Apply weight-based truncation (higher weight = keep more)
                truncate_to = int(available_space * section_weight)
                section_content = clip_text(section_content, max_chars=truncate_to)
                section_content += "\n[Section truncated for length...]"
            else:
                continue  # Skip this section entirely
        
        # Format section with clear header
        output_parts.append(f"=== {section_title} ===")
        output_parts.append(f"[Priority: {section['priority']}, Source: {section['source']}, Weight: {section['weight']:.2f}]")
        output_parts.append("")
        output_parts.append(section_content)
        output_parts.append("")
        
        current_length += len("\n".join(output_parts[-4:]))
        
        # Stop if we've reached the limit
        if current_length >= max_total_chars:
            break
    
    # Add context metadata
    if query_keywords:
        output_parts.append("=== CONTEXT_METADATA ===")
        output_parts.append(f"Query keywords: {', '.join(query_keywords[:10])}")
        output_parts.append(f"Context sections included: {len([s for s in context_sections if s['content']])}")
        output_parts.append("")
    
    return "\n".join(output_parts).strip()


def build_query_aware_context(
    *,
    user_query: str,
    user_profile: dict[str, Any] | None = None,
    user_display_name: str | None = None,
    user_email: str | None = None,
    user_id: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
    rfp_id: str | None = None,
    max_total_chars: int = 50000,
) -> str:
    """
    Build context specifically optimized for the user's query.
    
    This is a convenience wrapper around build_structured_context
    that emphasizes query-aware retrieval.
    
    Args:
        user_query: User's question/request
        user_profile: User profile dict
        user_display_name: User display name
        user_email: User email
        user_id: Slack user ID
        channel_id: Slack channel ID
        thread_ts: Slack thread timestamp
        rfp_id: RFP ID if known
        max_total_chars: Maximum total context length
    
    Returns:
        Query-optimized context string
    """
    return build_structured_context(
        user_profile=user_profile,
        user_display_name=user_display_name,
        user_email=user_email,
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        rfp_id=rfp_id,
        user_query=user_query,
        max_total_chars=max_total_chars,
        prioritize_recent=True,
    )


def summarize_context_for_prompt(
    *,
    context: str,
    max_summary_chars: int = 500,
) -> str:
    """
    Create a brief summary of context for inclusion in prompts when
    full context would be too long.
    
    Args:
        context: Full context string
        max_summary_chars: Maximum length for summary
    
    Returns:
        Brief summary of context
    """
    if not context or len(context) <= max_summary_chars:
        return context
    
    # Extract section titles to create a summary
    lines = context.split("\n")
    sections: list[str] = []
    current_section = None
    
    for line in lines:
        if line.startswith("===") and line.endswith("==="):
            current_section = line.strip("= ").strip()
            sections.append(current_section)
    
    if sections:
        summary = f"Context available with {len(sections)} sections: {', '.join(sections[:5])}"
        if len(sections) > 5:
            summary += f", and {len(sections) - 5} more"
        return summary
    
    # Fallback: truncate and add note
    return clip_text(context, max_chars=max_summary_chars) + "\n\n[Full context available but truncated for brevity]"
