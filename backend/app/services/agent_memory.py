from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..ai.context import clip_text
from .user_profiles_repo import get_user_profile


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MemoryType:
    """Memory type constants."""
    EPISODIC = "episodic"  # Specific conversations, decisions, outcomes
    SEMANTIC = "semantic"  # User preferences, working patterns, domain knowledge
    PROCEDURAL = "procedural"  # Successful workflows, tool usage patterns


def get_user_memory(*, user_sub: str) -> dict[str, Any]:
    """
    Retrieve structured memory for a user.
    Returns a dict with episodic, semantic, and procedural memory.
    """
    profile = get_user_profile(user_sub=user_sub)
    if not profile:
        return {
            "episodic": [],
            "semantic": {},
            "procedural": [],
        }
    
    # Extract memory from user profile
    memory_summary = str(profile.get("aiMemorySummary") or "").strip()
    preferences = profile.get("aiPreferences")
    prefs = preferences if isinstance(preferences, dict) else {}
    
    # Semantic memory from preferences
    semantic: dict[str, Any] = {}
    for key, value in prefs.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            semantic[key] = value
    
    # Episodic and procedural memory would be stored separately in a future enhancement
    # For now, we parse the memory_summary for episodic memories
    episodic: list[dict[str, Any]] = []
    if memory_summary:
        # Simple parsing: treat memory_summary as a single episodic entry
        # In a full implementation, this would be stored as structured entries
        episodic.append({
            "content": memory_summary,
            "timestamp": profile.get("updatedAt") or _now_iso(),
            "type": MemoryType.EPISODIC,
        })
    
    return {
        "episodic": episodic,
        "semantic": semantic,
        "procedural": [],
    }


def add_episodic_memory(
    *,
    user_sub: str,
    content: str,
    context: dict[str, Any] | None = None,
) -> None:
    """
    Add an episodic memory (specific conversation, decision, outcome).
    This updates the user profile's aiMemorySummary.
    """
    profile = get_user_profile(user_sub=user_sub)
    if not profile:
        return
    
    # Update profile (this would need to be done via the profile update mechanism)
    # For now, this is a placeholder - actual implementation would update the profile
    # The actual update should be done via the user profile update endpoint/action
    # existing_memory = str(profile.get("aiMemorySummary") or "").strip()
    # new_memory = clip_text(content, max_chars=2000)
    # timestamp = _now_iso()
    # memory_entry = f"[{timestamp}] {new_memory}"
    # combined = f"{existing_memory}\n{memory_entry}" if existing_memory else memory_entry


def update_semantic_memory(
    *,
    user_sub: str,
    key: str,
    value: Any,
) -> None:
    """
    Update semantic memory (preferences, patterns, knowledge).
    This updates the user profile's aiPreferences.
    """
    # This would update the user profile's aiPreferences
    # Actual implementation would use the profile update mechanism
    pass


def add_procedural_memory(
    *,
    user_sub: str,
    workflow: str,
    success: bool,
    context: dict[str, Any] | None = None,
) -> None:
    """
    Add a procedural memory (successful workflow, tool usage pattern).
    This would be stored separately from the profile in a future enhancement.
    """
    # Future: Store procedural memories in a separate table/index
    # For now, this is a placeholder
    pass


def compress_memory(
    *,
    user_sub: str,
    days_old: int = 30,
) -> str:
    """
    Compress old memories by summarizing them.
    Returns a summary of old memories that can replace detailed entries.
    """
    memory = get_user_memory(user_sub=user_sub)
    episodic = memory.get("episodic", [])
    
    if not episodic:
        return ""
    
    # Filter old memories
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
    old_memories: list[dict[str, Any]] = []
    recent_memories: list[dict[str, Any]] = []
    
    for mem in episodic:
        if not isinstance(mem, dict):
            continue
        timestamp_str = str(mem.get("timestamp") or "")
        try:
            mem_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if mem_time < cutoff:
                old_memories.append(mem)
            else:
                recent_memories.append(mem)
        except Exception:
            # If we can't parse timestamp, keep it as recent
            recent_memories.append(mem)
    
    if not old_memories:
        return ""
    
    # Summarize old memories (in a full implementation, this would use AI)
    summary_parts: list[str] = []
    for mem in old_memories[:10]:  # Limit to 10 for summary
        content = str(mem.get("content") or "").strip()
        if content:
            summary_parts.append(clip_text(content, max_chars=200))
    
    if summary_parts:
        return f"Summary of older memories: {'; '.join(summary_parts)}"
    
    return ""


def search_memory(
    *,
    user_sub: str,
    query: str,
    memory_types: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Search user memory for relevant entries.
    Returns a list of matching memory entries.
    """
    memory = get_user_memory(user_sub=user_sub)
    query_lower = query.lower()
    results: list[dict[str, Any]] = []
    
    types_to_search = memory_types or [MemoryType.EPISODIC, MemoryType.SEMANTIC, MemoryType.PROCEDURAL]
    
    # Search episodic memory
    if MemoryType.EPISODIC in types_to_search:
        episodic = memory.get("episodic", [])
        for mem in episodic:
            if not isinstance(mem, dict):
                continue
            content = str(mem.get("content") or "").strip().lower()
            if query_lower in content:
                results.append({
                    "type": MemoryType.EPISODIC,
                    "content": mem.get("content"),
                    "timestamp": mem.get("timestamp"),
                })
                if len(results) >= limit:
                    break
    
    # Search semantic memory
    if MemoryType.SEMANTIC in types_to_search and len(results) < limit:
        semantic = memory.get("semantic", {})
        for key, value in semantic.items():
            key_lower = str(key).lower()
            value_str = str(value).lower()
            if query_lower in key_lower or query_lower in value_str:
                results.append({
                    "type": MemoryType.SEMANTIC,
                    "key": key,
                    "value": value,
                })
                if len(results) >= limit:
                    break
    
    return results[:limit]


def format_memory_for_context(
    *,
    user_sub: str,
    max_chars: int = 2000,
) -> str:
    """
    Format user memory for inclusion in agent context.
    Returns a formatted string optimized for prompts.
    """
    memory = get_user_memory(user_sub=user_sub)
    lines: list[str] = []
    
    # Semantic memory (preferences)
    semantic = memory.get("semantic", {})
    if semantic:
        lines.append("User preferences (semantic memory):")
        for key, value in list(semantic.items())[:10]:  # Limit to 10 keys
            lines.append(f"  - {key}: {value}")
        lines.append("")
    
    # Episodic memory (recent conversations/decisions)
    episodic = memory.get("episodic", [])
    if episodic:
        lines.append("Recent memories (episodic):")
        for mem in episodic[-5:]:  # Last 5 memories
            if isinstance(mem, dict):
                content = str(mem.get("content") or "").strip()
                if content:
                    lines.append(f"  - {clip_text(content, max_chars=300)}")
        lines.append("")
    
    formatted = "\n".join(lines).strip()
    return clip_text(formatted, max_chars=max_chars)
