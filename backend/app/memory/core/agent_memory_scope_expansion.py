"""
Contextual scope expansion for memory retrieval.

Automatically expands memory scopes based on context to enable cross-scope
memory sharing, similar to how human teams naturally share relevant knowledge.
"""

from __future__ import annotations

from typing import Any

from ...observability.logging import get_logger

log = get_logger("agent_memory_scope_expansion")


def expand_scopes_contextually(
    *,
    primary_scope_id: str | None = None,
    rfp_id: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
    user_sub: str | None = None,
    tenant_id: str | None = None,
    query_text: str | None = None,
    context: dict[str, Any] | None = None,
) -> list[str]:
    """
    Expand memory scopes contextually based on the query context.
    
    Similar to how human teams naturally share relevant knowledge in conversations,
    this function automatically expands scopes to include related contexts.
    
    Args:
        primary_scope_id: Primary scope ID (e.g., "USER#{sub}", "RFP#{id}")
        rfp_id: RFP identifier (for RFP-related queries)
        channel_id: Slack channel ID (for channel-related queries)
        thread_ts: Slack thread timestamp (for thread-specific queries)
        user_sub: User identifier (Cognito sub)
        tenant_id: Tenant identifier
        query_text: Optional query text for context
        context: Optional additional context dict
    
    Returns:
        List of expanded scope IDs to query
    """
    expanded_scopes: list[str] = []
    
    # Add primary scope if provided
    if primary_scope_id:
        expanded_scopes.append(primary_scope_id)
    
    context = context or {}
    
    # Determine expansion strategy based on primary scope type
    if primary_scope_id:
        if primary_scope_id.startswith("RFP#"):
            # RFP scope expansion: include participants, channels, tenant
            expanded_scopes.extend(_expand_rfp_scope(
                rfp_id=rfp_id or primary_scope_id.replace("RFP#", ""),
                context=context,
            ))
        
        elif primary_scope_id.startswith("USER#"):
            # User scope expansion: include tenant, related RFPs, channels
            expanded_scopes.extend(_expand_user_scope(
                user_sub=user_sub or primary_scope_id.replace("USER#", ""),
                context=context,
            ))
        
        elif primary_scope_id.startswith("CHANNEL#"):
            # Channel scope expansion: include participants, threads, related RFPs
            expanded_scopes.extend(_expand_channel_scope(
                channel_id=channel_id or primary_scope_id.replace("CHANNEL#", ""),
                thread_ts=thread_ts,
                context=context,
            ))
        
        elif primary_scope_id.startswith("THREAD#"):
            # Thread scope expansion: include channel, participants, related RFPs
            expanded_scopes.extend(_expand_thread_scope(
                primary_scope_id=primary_scope_id,
                channel_id=channel_id,
                context=context,
            ))
    
    # Fallback: determine scope from individual parameters
    if not primary_scope_id:
        if rfp_id:
            expanded_scopes.append(f"RFP#{rfp_id}")
            expanded_scopes.extend(_expand_rfp_scope(rfp_id=rfp_id, context=context))
        
        if channel_id:
            expanded_scopes.append(f"CHANNEL#{channel_id}")
            if thread_ts:
                expanded_scopes.append(f"THREAD#{channel_id}#{thread_ts}")
            expanded_scopes.extend(_expand_channel_scope(channel_id=channel_id, thread_ts=thread_ts, context=context))
        
        if user_sub:
            expanded_scopes.append(f"USER#{user_sub}")
            expanded_scopes.extend(_expand_user_scope(user_sub=user_sub, context=context))
        
        if tenant_id:
            expanded_scopes.append(f"TENANT#{tenant_id}")
    
    # Always include GLOBAL scope for external context and diagnostics
    expanded_scopes.append("GLOBAL")
    
    # Deduplicate while preserving order
    seen = set()
    deduplicated: list[str] = []
    for scope in expanded_scopes:
        if scope and scope not in seen:
            seen.add(scope)
            deduplicated.append(scope)
    
    log.debug(
        "scopes_expanded",
        primary_scope=primary_scope_id,
        expanded_count=len(deduplicated),
        scopes=deduplicated[:10],  # Log first 10 to avoid log bloat
    )
    
    return deduplicated


def _expand_rfp_scope(*, rfp_id: str, context: dict[str, Any]) -> list[str]:
    """Expand RFP scope to include participants, channels, tenant."""
    expanded: list[str] = []
    
    # Try to get RFP participants from context
    participants = context.get("rfp_participants") or context.get("participants")
    if isinstance(participants, list):
        for participant_id in participants:
            if participant_id:
                expanded.append(f"USER#{participant_id}")
    
    # Try to get RFP channels from context
    channels = context.get("rfp_channels") or context.get("channels")
    if isinstance(channels, list):
        for channel_id in channels:
            if channel_id:
                expanded.append(f"CHANNEL#{channel_id}")
    
    # Include tenant scope if available
    tenant_id = context.get("tenant_id")
    if tenant_id:
        expanded.append(f"TENANT#{tenant_id}")
    
    return expanded


def _expand_user_scope(*, user_sub: str, context: dict[str, Any]) -> list[str]:
    """Expand user scope to include tenant, related RFPs, channels."""
    expanded: list[str] = []
    
    # Include tenant scope
    tenant_id = context.get("tenant_id")
    if tenant_id:
        expanded.append(f"TENANT#{tenant_id}")
    
    # Try to get user's RFPs from context
    user_rfps = context.get("user_rfps") or context.get("rfps")
    if isinstance(user_rfps, list):
        for rfp_id in user_rfps[:10]:  # Limit to avoid too many scopes
            if rfp_id:
                expanded.append(f"RFP#{rfp_id}")
    
    # Try to get user's active channels from context
    user_channels = context.get("user_channels") or context.get("channels")
    if isinstance(user_channels, list):
        for channel_id in user_channels[:10]:  # Limit
            if channel_id:
                expanded.append(f"CHANNEL#{channel_id}")
    
    return expanded


def _expand_channel_scope(*, channel_id: str, thread_ts: str | None = None, context: dict[str, Any]) -> list[str]:
    """Expand channel scope to include participants, threads, related RFPs."""
    expanded: list[str] = []
    
    # Include thread scope if provided
    if thread_ts:
        expanded.append(f"THREAD#{channel_id}#{thread_ts}")
    
    # Try to get channel members from context
    members = context.get("channel_members") or context.get("members")
    if isinstance(members, list):
        for member_id in members[:20]:  # Limit to avoid too many scopes
            if member_id:
                expanded.append(f"USER#{member_id}")
    
    # Try to get related RFPs from context
    related_rfps = context.get("related_rfps") or context.get("rfps")
    if isinstance(related_rfps, list):
        for rfp_id in related_rfps[:10]:  # Limit
            if rfp_id:
                expanded.append(f"RFP#{rfp_id}")
    
    return expanded


def _expand_thread_scope(*, primary_scope_id: str, channel_id: str | None = None, context: dict[str, Any]) -> list[str]:
    """Expand thread scope to include channel, participants, related RFPs."""
    expanded: list[str] = []
    
    # Parse channel from thread scope if not provided
    if not channel_id and "#" in primary_scope_id:
        parts = primary_scope_id.split("#")
        if len(parts) >= 2:
            channel_id = parts[1]
    
    if channel_id:
        expanded.append(f"CHANNEL#{channel_id}")
        expanded.extend(_expand_channel_scope(channel_id=channel_id, context=context))
    
    return expanded
