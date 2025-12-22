from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...ai.context import clip_text
from ...observability.logging import get_logger
from ..core.agent_memory_db import (
    MemoryType,
    create_memory,
    list_memories_by_scope,
    update_memory,
)
from ..core.agent_memory_keywords import extract_keywords, extract_tags
from ..retrieval.agent_memory_opensearch import delete_memory_index, index_memory

log = get_logger("agent_memory_compression")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compress_old_memories(
    *,
    scope_id: str,
    memory_type: str = MemoryType.EPISODIC,
    days_old: int = 30,
    min_access_count: int = 0,
    max_memories_per_compression: int = 10,
    use_compaction_settings: bool = True,
) -> dict[str, Any]:
    """
    Compress old memories by summarizing them into a single compressed memory.
    
    Process:
    1. Find old memories (older than days_old, accessed fewer than min_access_count times)
    2. Group related memories
    3. Use AI to generate a summary
    4. Create new compressed memory
    5. Mark originals for deletion (via TTL)
    
    Args:
        scope_id: Scope to compress memories for
        memory_type: Type of memories to compress (default: EPISODIC)
        days_old: Minimum age in days for memories to be compressed
        min_access_count: Maximum access count for memories to be compressed
        max_memories_per_compression: Maximum number of memories to compress at once
    
    Returns:
        Dict with compression results (compressed_count, new_memory_id, etc.)
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
    
    # Get compaction settings if enabled
    settings = None
    if use_compaction_settings:
        try:
            from .agent_memory_compaction_settings import get_compaction_settings
            settings = get_compaction_settings(scope_id=scope_id)
        except Exception:
            pass  # Fall back to manual filtering
    
    # Get old memories
    all_memories, _ = list_memories_by_scope(
        scope_id=scope_id,
        memory_type=memory_type,
        limit=100,
    )
    
    # Filter: old and low access count, and low importance
    old_memories: list[dict[str, Any]] = []
    for mem in all_memories:
        created_at_str = mem.get("createdAt", "")
        if not created_at_str:
            continue
        
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            days_old_mem = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).days
            
            if settings:
                # Use compaction settings
                if not settings.should_compress(memory=mem, days_old=days_old_mem):
                    continue
            else:
                # Manual filtering (backward compatible)
                if created_at.replace(tzinfo=timezone.utc) >= cutoff_date.replace(tzinfo=timezone.utc):
                    continue  # Too recent
                
                access_count = mem.get("accessCount", 0)
                if access_count > min_access_count:
                    continue  # Too frequently accessed
                
                # Skip already compressed memories
                if mem.get("compressed", False):
                    continue
                
                # Check importance - skip compression if importance is high
                try:
                    from ..core.agent_memory_consolidation import calculate_importance_score
                    importance = calculate_importance_score(memory=mem, base_access_count=access_count)
                    if importance > 0.5:  # Skip compression if importance > 0.5
                        continue
                except Exception:
                    pass  # If importance calculation fails, continue with compression
        
        except Exception:
            continue
        
        old_memories.append(mem)
    
    if len(old_memories) < 2:
        return {
            "compressed_count": 0,
            "message": "Not enough old memories to compress",
        }
    
    # Limit to max_memories_per_compression
    memories_to_compress = old_memories[:max_memories_per_compression]
    
    # Group memories by similarity (simple grouping by shared keywords)
    # For now, we'll just compress all together
    memory_ids: list[str] = []
    for mem in memories_to_compress:
        mid = mem.get("memoryId")
        if mid and isinstance(mid, str):
            memory_ids.append(mid)
    
    # Build summary content from all memories
    memory_contents: list[str] = []
    for mem in memories_to_compress:
        content = mem.get("content", "")
        summary = mem.get("summary")
        created_at = mem.get("createdAt", "")
        
        if summary:
            memory_contents.append(f"[{created_at}] {summary}")
        elif content:
            # Use first 200 chars of content
            memory_contents.append(f"[{created_at}] {clip_text(content, max_chars=200)}")
    
    combined_content = "\n\n".join(memory_contents)
    
    # Generate summary using AI
    try:
        summary = _generate_memory_summary(combined_content, memory_type=memory_type)
    except Exception as e:
        log.warning("compression_summary_generation_failed", error=str(e))
        # Fallback: use simple truncation
        summary = clip_text(combined_content, max_chars=2000)
    
    # Extract keywords and tags from summary
    keywords = extract_keywords(summary, max_keywords=30)
    tags = extract_tags(summary)
    
    # Combine keywords/tags from all original memories
    all_keywords: set[str] = set(keywords)
    all_tags: set[str] = set(tags)
    for mem in memories_to_compress:
        all_keywords.update(mem.get("keywords", []))
        all_tags.update(mem.get("tags", []))
    
    # Create compressed memory
    now_ts = int(datetime.now(timezone.utc).timestamp())
    expires_at = now_ts + (180 * 24 * 60 * 60)  # 180 days from now
    
    # Extract provenance from first original memory (best effort)
    first_memory = memories_to_compress[0] if memories_to_compress else {}
    provenance_from_original = first_memory.get("metadata", {}).get("provenance", {}) if isinstance(first_memory.get("metadata"), dict) else {}
    
    # Helper function for type-safe string conversion
    def _safe_str_or_none(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value if value.strip() else None
        if isinstance(value, (int, float)):
            return str(value)
        return None
    
    # Preserve provenance from original memories (with type safety)
    cognito_user_id = _safe_str_or_none(first_memory.get("cognitoUserId") or provenance_from_original.get("cognitoUserId"))
    slack_user_id = _safe_str_or_none(first_memory.get("slackUserId") or provenance_from_original.get("slackUserId"))
    slack_channel_id = _safe_str_or_none(first_memory.get("slackChannelId") or provenance_from_original.get("slackChannelId"))
    slack_thread_ts = _safe_str_or_none(first_memory.get("slackThreadTs") or provenance_from_original.get("slackThreadTs"))
    slack_team_id = _safe_str_or_none(first_memory.get("slackTeamId") or provenance_from_original.get("slackTeamId"))
    rfp_id_prov = _safe_str_or_none(first_memory.get("rfpId") or provenance_from_original.get("rfpId"))
    source = str(first_memory.get("source") or "memory_compression")
    
    compressed_memory = create_memory(
        memory_type=memory_type,
        scope_id=scope_id,
        content=summary,
        tags=list(all_tags)[:25],
        keywords=list(all_keywords)[:50],
        summary=clip_text(summary, max_chars=500),
        compressed=True,
        original_memory_ids=memory_ids,
        expires_at=expires_at,
        cognito_user_id=cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        slack_team_id=slack_team_id,
        rfp_id=rfp_id_prov,
        source=source,
    )
    
    # Mark original memories for deletion via TTL
    # We'll set expires_at to now + 7 days to give time for any final access
    delete_ts = now_ts + (7 * 24 * 60 * 60)  # 7 days
    
    for mem in memories_to_compress:
        memory_id = mem.get("memoryId")
        created_at_raw = mem.get("createdAt")
        mem_type = mem.get("memoryType")
        mem_scope = mem.get("scopeId")
        
        # Ensure created_at_for_update is a string (it should be from DB, but check for type safety)
        created_at_for_update: str | None = None
        if isinstance(created_at_raw, str):
            created_at_for_update = created_at_raw
        elif isinstance(created_at_raw, datetime):
            created_at_for_update = created_at_raw.isoformat().replace("+00:00", "Z")
        
        if memory_id and created_at_for_update and mem_type and mem_scope:
            try:
                # Update memory to set expires_at for TTL deletion
                update_memory(
                    memory_id=str(memory_id),
                    memory_type=str(mem_type),
                    scope_id=str(mem_scope),
                    created_at=created_at_for_update,
                    expires_at=delete_ts,
                )
                # Also remove from OpenSearch index immediately
                delete_memory_index(memory_id)
            except Exception as e:
                log.warning("compression_memory_cleanup_failed", memory_id=memory_id, error=str(e))
    
    # Index the compressed memory
    try:
        index_memory(compressed_memory)
    except Exception:
        pass  # Non-critical
    
    result = {
        "compressed_count": len(memories_to_compress),
        "new_memory_id": compressed_memory.get("memoryId"),
        "original_memory_ids": memory_ids,
    }
    
    log.info(
        "memory_compression_completed",
        scope_id=scope_id,
        memory_type=memory_type,
        compressed_count=len(memories_to_compress),
        new_memory_id=compressed_memory.get("memoryId"),
    )
    
    return result


def _generate_memory_summary(content: str, memory_type: str) -> str:
    """
    Generate a summary of memories using AI.
    
    Args:
        content: Combined content from multiple memories
        memory_type: Type of memory being summarized
    
    Returns:
        Summarized content
    """
    from ...ai.verified_calls import call_text_verified
    
    prompt = f"""Summarize the following {memory_type.lower()} memories into a concise summary that preserves key information, decisions, and insights.

Focus on:
- Important decisions and outcomes
- Key patterns or learnings
- Relevant context and details
- What worked well or didn't work

Original memories:
{clip_text(content, max_chars=8000)}

Provide a clear, structured summary:"""

    try:
        summary, _meta = call_text_verified(
            purpose="generate_content",  # Use generic content generation purpose
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes memories concisely while preserving important information."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.3,
            timeout_s=30,
            retries=2,
        )
        
        return clip_text(summary.strip(), max_chars=2000)
    except Exception as e:
        log.error("ai_summary_generation_failed", error=str(e))
        raise


def run_compression_job(
    *,
    scope_ids: list[str] | None = None,
    memory_types: list[str] | None = None,
    days_old: int = 30,
) -> dict[str, Any]:
    """
    Run compression for multiple scopes and memory types.
    
    This is designed to be called as a scheduled job.
    
    Args:
        scope_ids: List of scope IDs to compress (None = compress all scopes with old memories)
        memory_types: List of memory types to compress (None = EPISODIC only)
        days_old: Minimum age for compression
    
    Returns:
        Summary of compression results
    """
    if memory_types is None:
        memory_types = [MemoryType.EPISODIC]
    
    results: list[dict[str, Any]] = []
    
    # For now, we'll just compress for provided scope_ids
    # In a full implementation, you might query for all scopes with old memories
    if scope_ids:
        for scope_id in scope_ids:
            for mem_type in memory_types:
                try:
                    result = compress_old_memories(
                        scope_id=scope_id,
                        memory_type=mem_type,
                        days_old=days_old,
                    )
                    results.append({
                        "scope_id": scope_id,
                        "memory_type": mem_type,
                        **result,
                    })
                except Exception as e:
                    log.error("compression_failed", scope_id=scope_id, memory_type=mem_type, error=str(e))
                    results.append({
                        "scope_id": scope_id,
                        "memory_type": mem_type,
                        "error": str(e),
                    })
    
    total_compressed = sum(r.get("compressed_count", 0) for r in results)
    
    return {
        "total_compressed": total_compressed,
        "results": results,
    }
