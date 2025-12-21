from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..ai.context import clip_text
from .agent_events_repo import list_recent_events
from .agent_jobs_repo import list_jobs_by_scope
from .agent_journal_repo import list_recent_entries
from .agent_memory_retrieval import get_memories_for_context
from .external_context_service import format_external_context_for_prompt, get_external_context_for_query
from .opportunity_state_repo import get_state
from .rfps_repo import get_rfp_by_id, list_rfps


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_user_context(
    *,
    user_profile: dict[str, Any] | None,
    user_display_name: str | None = None,
    user_email: str | None = None,
    user_id: str | None = None,
) -> str:
    """
    Build user context from profile and provided information.
    Returns a formatted string for inclusion in system prompts.
    """
    prof = user_profile if isinstance(user_profile, dict) else {}
    preferred = str(prof.get("preferredName") or "").strip()
    full = str(prof.get("fullName") or "").strip()
    effective_name = preferred or full or (str(user_display_name or "").strip() if user_display_name else "")
    prefs = prof.get("aiPreferences") if isinstance(prof.get("aiPreferences"), dict) else {}
    mem = str(prof.get("aiMemorySummary") or "").strip()
    
    user_ctx_lines: list[str] = []
    user_sub = str(prof.get("_id") or prof.get("userSub") or "").strip()
    if user_sub:
        user_ctx_lines.append(f"- user_sub: {user_sub}")
    if effective_name:
        user_ctx_lines.append(f"- name: {effective_name}")
    if user_email:
        user_ctx_lines.append(f"- email: {str(user_email).strip().lower()}")
    if user_id:
        user_ctx_lines.append(f"- slack_user_id: {str(user_id).strip()}")
    
    # Profile completion status
    profile_completed_at = prof.get("profileCompletedAt")
    if profile_completed_at:
        user_ctx_lines.append(f"- profile_completed_at: {profile_completed_at}")
    onboarding_version = prof.get("onboardingVersion")
    if onboarding_version:
        user_ctx_lines.append(f"- onboarding_version: {onboarding_version}")
    
    # Timestamps
    created_at = prof.get("createdAt")
    if created_at:
        user_ctx_lines.append(f"- profile_created_at: {created_at}")
    updated_at = prof.get("updatedAt")
    if updated_at:
        user_ctx_lines.append(f"- profile_updated_at: {updated_at}")
    
    # Include resume information if available
    resume_assets = prof.get("resumeAssets")
    if isinstance(resume_assets, list) and resume_assets:
        resume_info: list[str] = []
        for asset in resume_assets[:5]:  # Limit to 5 most recent
            if not isinstance(asset, dict):
                continue
            file_name = str(asset.get("fileName") or "").strip()
            s3_key = str(asset.get("s3Key") or "").strip()
            uploaded_at = str(asset.get("uploadedAt") or "").strip()
            content_type = str(asset.get("contentType") or "").strip().lower()
            if file_name and s3_key:
                resume_entry = f"{file_name} (S3: {s3_key})"
                if content_type:
                    resume_entry += f" [{content_type}]"
                if uploaded_at:
                    resume_entry += f" uploaded {uploaded_at}"
                resume_info.append(resume_entry)
        if resume_info:
            user_ctx_lines.append(f"- resumes: {', '.join(resume_info)}")
    
    # Include job titles and certifications if available
    job_titles = prof.get("jobTitles")
    if isinstance(job_titles, list) and job_titles:
        titles_str = ", ".join([str(t) for t in job_titles[:5]])
        if titles_str:
            user_ctx_lines.append(f"- job_titles: {titles_str}")
    
    certs = prof.get("certifications")
    if isinstance(certs, list) and certs:
        certs_str = ", ".join([str(c) for c in certs[:10]])
        if certs_str:
            user_ctx_lines.append(f"- certifications: {certs_str}")
    
    # Include linked team member information if available
    linked_team_member_id = prof.get("linkedTeamMemberId")
    if linked_team_member_id:
        user_ctx_lines.append(f"- linked_team_member_id: {linked_team_member_id}")
        # Fetch and include team member details
        try:
            from . import content_repo
            team_member = content_repo.get_team_member_by_id(str(linked_team_member_id).strip())
            if team_member and isinstance(team_member, dict):
                tm_name = str(team_member.get("nameWithCredentials") or team_member.get("name") or "").strip()
                if tm_name:
                    user_ctx_lines.append(f"- team_member_name: {tm_name}")
                tm_position = str(team_member.get("position") or "").strip()
                if tm_position:
                    user_ctx_lines.append(f"- team_member_position: {tm_position}")
                tm_bio = str(team_member.get("biography") or "").strip()
                if tm_bio:
                    # Clip biography to reasonable length for context
                    bio_preview = tm_bio[:500] + "..." if len(tm_bio) > 500 else tm_bio
                    user_ctx_lines.append(f"- team_member_biography: {bio_preview}")
                # Include bio profiles (project-type-specific bios)
                bio_profiles = team_member.get("bioProfiles")
                if isinstance(bio_profiles, list) and bio_profiles:
                    for bp in bio_profiles[:3]:  # Limit to 3 most relevant
                        if isinstance(bp, dict):
                            bp_label = str(bp.get("label") or "").strip()
                            bp_project_types = bp.get("projectTypes")
                            if bp_label:
                                types_str = ""
                                if isinstance(bp_project_types, list) and bp_project_types:
                                    types_str = f" ({', '.join([str(t) for t in bp_project_types[:3]])})"
                                user_ctx_lines.append(f"- team_member_bio_profile: {bp_label}{types_str}")
        except Exception:
            # Best-effort: if fetching team member fails, continue without it
            pass
    
    if isinstance(prefs, dict) and prefs:
        # Keep this compact.
        try:
            import json
            user_ctx_lines.append(f"- preferences_json: {clip_text(json.dumps(prefs, ensure_ascii=False), max_chars=1200)}")
        except Exception:
            pass
    if mem:
        user_ctx_lines.append(f"- memory_summary: {clip_text(mem, max_chars=1200)}")
    
    return "\n".join(user_ctx_lines).strip()


def build_thread_context(
    *,
    channel_id: str | None,
    thread_ts: str | None,
    limit: int = 100,
) -> str:
    """
    Build thread conversation history context.
    Returns a formatted string for inclusion in system prompts.
    """
    if not channel_id or not thread_ts:
        return ""
    
    try:
        from .agent_tools.slack_read import get_thread as slack_get_thread
        from .slack_web import get_user_info, slack_user_display_name
        
        result = slack_get_thread(channel=channel_id, thread_ts=thread_ts, limit=limit)
        if not result.get("ok"):
            return ""
        
        thread_messages = result.get("messages", [])
        if not thread_messages or not isinstance(thread_messages, list):
            return ""
        
        lines: list[str] = []
        for msg in thread_messages:
            if not isinstance(msg, dict):
                continue
            user_id_msg = str(msg.get("user") or "").strip()
            text = str(msg.get("text") or "").strip()
            if not text:
                continue
            user_name = "User"
            if user_id_msg:
                try:
                    user_info = get_user_info(user_id=user_id_msg)
                    user_name = slack_user_display_name(user_info) or user_id_msg
                except Exception:
                    user_name = user_id_msg
            lines.append(f"{user_name}: {text}")
        
        if not lines:
            return ""
        
        return "\n\nThread conversation history (for context - remember previous exchanges like channel names, permissions, preferences):\n" + "\n".join(lines) + "\n"
    except Exception:
        # Best-effort: if fetching fails, return empty string
        return ""


def build_rfp_state_context(
    *,
    rfp_id: str,
    journal_limit: int = 10,
    events_limit: int = 10,
) -> str:
    """
    Build RFP state context from OpportunityState, journal entries, and events.
    Returns a formatted string for inclusion in system prompts.
    """
    if not rfp_id:
        return ""
    
    try:
        state = get_state(rfp_id=rfp_id)
        journal = list_recent_entries(rfp_id=rfp_id, limit=journal_limit)
        events = list_recent_events(rfp_id=rfp_id, limit=events_limit)
        
        lines: list[str] = []
        lines.append(f"RFP State Context for {rfp_id}:")
        lines.append("")
        
        # State summary
        if state:
            stage = state.get("stage")
            if stage:
                lines.append(f"- Stage: {stage}")
            summary = state.get("summary")
            if summary:
                lines.append(f"- Summary: {clip_text(str(summary), max_chars=800)}")
            due_dates = state.get("dueDates")
            if isinstance(due_dates, dict) and due_dates:
                lines.append(f"- Due dates: {clip_text(str(due_dates), max_chars=400)}")
            proposal_ids = state.get("proposalIds")
            if isinstance(proposal_ids, list) and proposal_ids:
                lines.append(f"- Proposals: {', '.join([str(p) for p in proposal_ids[:5]])}")
        
        # Recent journal entries
        if journal:
            lines.append("")
            lines.append("Recent journal entries:")
            for entry in journal[:journal_limit]:
                if not isinstance(entry, dict):
                    continue
                what_changed = str(entry.get("whatChanged") or "").strip()
                why = str(entry.get("why") or "").strip()
                created_at = str(entry.get("createdAt") or "").strip()
                if what_changed or why:
                    entry_text = f"  - {created_at}: {what_changed}"
                    if why:
                        entry_text += f" (why: {why})"
                    lines.append(clip_text(entry_text, max_chars=300))
        
        # Recent events
        if events:
            lines.append("")
            lines.append("Recent events:")
            for event in events[:events_limit]:
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type") or "").strip()
                tool = str(event.get("tool") or "").strip()
                created_at = str(event.get("createdAt") or "").strip()
                if event_type or tool:
                    event_text = f"  - {created_at}: {event_type}"
                    if tool:
                        event_text += f" (tool: {tool})"
                    lines.append(event_text)
        
        return "\n".join(lines)
    except Exception:
        # Best-effort: if fetching fails, return empty string
        return ""


def find_related_rfps(
    *,
    rfp_id: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Find related RFPs by similar client name or project type.
    Returns a list of related RFP summaries.
    """
    if not rfp_id:
        return []
    
    try:
        current_rfp = get_rfp_by_id(rfp_id)
        if not current_rfp or not isinstance(current_rfp, dict):
            return []
        
        client_name = str(current_rfp.get("clientName") or "").strip().lower()
        project_type = str(current_rfp.get("projectType") or "").strip().lower()
        
        if not client_name and not project_type:
            return []
        
        # Get recent RFPs
        resp = list_rfps(page=1, limit=100, next_token=None)
        all_rfps = (resp or {}).get("data") if isinstance(resp, dict) else []
        if not isinstance(all_rfps, list):
            return []
        
        related: list[dict[str, Any]] = []
        for rfp in all_rfps:
            if not isinstance(rfp, dict):
                continue
            rfp_id_candidate = str(rfp.get("_id") or "").strip()
            if rfp_id_candidate == rfp_id:
                continue
            
            rfp_client = str(rfp.get("clientName") or "").strip().lower()
            rfp_type = str(rfp.get("projectType") or "").strip().lower()
            
            # Match by client name (exact or partial) or project type
            matches = False
            if client_name and rfp_client:
                if client_name in rfp_client or rfp_client in client_name:
                    matches = True
            if project_type and rfp_type and not matches:
                if project_type == rfp_type:
                    matches = True
            
            if matches:
                related.append({
                    "rfpId": rfp_id_candidate,
                    "title": str(rfp.get("title") or "RFP").strip(),
                    "clientName": rfp_client,
                    "projectType": rfp_type,
                    "submissionDeadline": str(rfp.get("submissionDeadline") or "").strip(),
                })
                if len(related) >= limit:
                    break
        
        return related
    except Exception:
        # Best-effort: if fetching fails, return empty list
        return []


def build_related_rfps_context(
    *,
    rfp_id: str,
    limit: int = 5,
) -> str:
    """
    Build context about related RFPs.
    Returns a formatted string for inclusion in system prompts.
    """
    related = find_related_rfps(rfp_id=rfp_id, limit=limit)
    if not related:
        return ""
    
    lines: list[str] = []
    lines.append("Related RFPs (for pattern recognition and learnings):")
    for rfp in related:
        rfp_id_rel = str(rfp.get("rfpId") or "").strip()
        title = str(rfp.get("title") or "RFP").strip()
        client = str(rfp.get("clientName") or "").strip()
        lines.append(f"  - {rfp_id_rel}: {title} (client: {client})")
    
    return "\n".join(lines)


def build_recent_jobs_context(
    *,
    rfp_id: str | None,
    limit: int = 10,
) -> str:
    """
    Build context about recent agent jobs for the RFP.
    Returns a formatted string for inclusion in system prompts.
    """
    if not rfp_id:
        return ""
    
    try:
        recent_jobs = list_jobs_by_scope(scope={"rfpId": rfp_id}, limit=limit, status=None)
        if not recent_jobs:
            return ""
        
        lines: list[str] = []
        lines.append("Recent agent jobs for this RFP:")
        for job in recent_jobs[:limit]:
            jid = str(job.get("jobId") or "").strip()
            jtype = str(job.get("jobType") or "").strip()
            status = str(job.get("status") or "").strip()
            due_at = str(job.get("dueAt") or "").strip()
            lines.append(f"  - {jid}: {jtype} ({status}) due {due_at}")
        
        return "\n".join(lines)
    except Exception:
        # Best-effort: if fetching fails, return empty string
        return ""


def build_cross_thread_context(
    *,
    rfp_id: str,
    current_channel_id: str | None = None,
    current_thread_ts: str | None = None,
    limit: int = 5,
) -> str:
    """
    Build context about other threads mentioning the same RFP.
    Returns a formatted string for inclusion in system prompts.
    """
    if not rfp_id:
        return ""
    
    try:
        # Find thread bindings for this RFP
        # Note: This is a simplified implementation - in practice, you might want
        # to query a more sophisticated index of thread bindings
        # For now, we'll use the events to find cross-thread references
        
        # Look for events that mention this RFP from different threads
        events = list_recent_events(rfp_id=rfp_id, limit=50)
        thread_refs: dict[str, dict[str, Any]] = {}
        
        for event in events:
            if not isinstance(event, dict):
                continue
            # Look for correlation_id or channel/thread info in payload
            payload = event.get("payload")
            if isinstance(payload, dict):
                channel = payload.get("channelId")
                thread = payload.get("threadTs")
                if channel and thread:
                    thread_key = f"{channel}#{thread}"
                    if thread_key not in thread_refs:
                        thread_refs[thread_key] = {
                            "channel": channel,
                            "thread": thread,
                            "lastSeen": str(event.get("createdAt") or "").strip(),
                        }
        
        if not thread_refs:
            return ""
        
        # Filter out current thread
        if current_channel_id and current_thread_ts:
            current_key = f"{current_channel_id}#{current_thread_ts}"
            thread_refs.pop(current_key, None)
        
        if not thread_refs:
            return ""
        
        lines: list[str] = []
        lines.append("Other threads mentioning this RFP:")
        for thread_info in list(thread_refs.values())[:limit]:
            channel = str(thread_info.get("channel") or "").strip()
            thread = str(thread_info.get("thread") or "").strip()
            last_seen = str(thread_info.get("lastSeen") or "").strip()
            lines.append(f"  - Channel {channel}, thread {thread} (last seen: {last_seen})")
        
        return "\n".join(lines)
    except Exception:
        # Best-effort: if fetching fails, return empty string
        return ""


def build_memory_context(
    *,
    user_sub: str | None = None,
    rfp_id: str | None = None,
    tenant_id: str | None = None,
    query_text: str | None = None,
    limit: int = 10,
    channel_id: str | None = None,
    thread_ts: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Build memory context from the new structured memory system.
    
    Args:
        user_sub: User identifier
        rfp_id: RFP identifier
        tenant_id: Tenant identifier
        query_text: Optional search query to filter memories
        limit: Maximum number of memories to include
    
    Returns:
        Formatted memory context string
    """
    try:
        # Build context dict for scope expansion
        expansion_context: dict[str, Any] = {}
        if rfp_id:
            # Try to get RFP participants and channels from opportunity state
            try:
                from .opportunity_state_repo import get_state
                rfp_state = get_state(rfp_id=rfp_id)
                if rfp_state:
                    # Extract participants, channels from state if available
                    expansion_context["rfp_id"] = rfp_id
            except Exception:
                pass
        
        if channel_id:
            expansion_context["channel_id"] = channel_id
            if thread_ts:
                expansion_context["thread_ts"] = thread_ts
        
        memories = get_memories_for_context(
            user_sub=user_sub,
            rfp_id=rfp_id,
            tenant_id=tenant_id,
            query_text=query_text,
            limit=limit,
            channel_id=channel_id,
            thread_ts=thread_ts,
            context=expansion_context or context,
            expand_scopes=True,  # Enable contextual scope expansion
        )
        
        # Pass token budget tracker to retrieval if available
        # (Currently handled in get_memories_for_context via retrieve_relevant_memories)
        
        if not memories:
            return ""
        
        lines: list[str] = []
        lines.append("Relevant agent memories:")
        if query_text:
            lines.append(f"[Retrieved based on query: {query_text[:100]}]")
        lines.append("")
        
        # Group memories by type for better organization
        by_type: dict[str, list[dict[str, Any]]] = {}
        for mem in memories[:limit]:
            mem_type = str(mem.get("memoryType", "")).upper()
            if mem_type not in by_type:
                by_type[mem_type] = []
            by_type[mem_type].append(mem)
        
        # Format by type (all memory types)
        type_order = [
            "EPISODIC",
            "SEMANTIC",
            "PROCEDURAL",
            "COLLABORATION_CONTEXT",
            "TEMPORAL_EVENT",
            "DIAGNOSTICS",
            "EXTERNAL_CONTEXT",
        ]
        for mem_type in type_order:
            if mem_type not in by_type:
                continue
            type_label = mem_type.lower().replace("_", " ").title()
            lines.append(f"{type_label} memories:")
            for mem in by_type[mem_type][:10]:  # Limit per type
                summary = mem.get("summary") or mem.get("content", "")
                created_at = mem.get("createdAt", "")
                tags = mem.get("tags", [])
                
                # Format: summary (created: date) [tags]
                line = f"  - {clip_text(summary, max_chars=200)}"
                if created_at:
                    # Extract date part from ISO timestamp
                    date_part = created_at.split("T")[0] if "T" in created_at else created_at[:10]
                    line += f" ({date_part})"
                if tags and isinstance(tags, list):
                    tag_str = ", ".join([str(t) for t in tags[:3]])
                    if tag_str:
                        line += f" [{tag_str}]"
                lines.append(line)
            lines.append("")
        
        return "\n".join(lines).strip()
    except Exception:
        # Best-effort: if memory retrieval fails, return empty string
        return ""


def build_comprehensive_context(
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
    token_budget_tracker: Any | None = None,  # TokenBudgetTracker
) -> str:
    """
    Build comprehensive multi-layer context from all available sources.
    
    Context layers (in priority order):
    1. User profile and preferences
    2. Thread conversation history
    3. Relevant agent memories (new structured memory system) - uses query-aware retrieval if user_query provided
    4. RFP state (OpportunityState, journal, events)
    5. Related RFPs
    6. Recent agent jobs
    7. Cross-thread context
    
    Args:
        user_query: Optional user query/question for query-aware context retrieval
        (other args same as before)
    
    Returns a formatted string optimized for inclusion in system prompts.
    """
    context_parts: list[str] = []
    
    # Extract user_sub from profile
    user_sub: str | None = None
    if user_profile:
        user_sub = str(user_profile.get("_id") or user_profile.get("userSub") or "").strip() or None
    
    # 1. User context (highest priority)
    user_ctx = build_user_context(
        user_profile=user_profile,
        user_display_name=user_display_name,
        user_email=user_email,
        user_id=user_id,
    )
    if user_ctx:
        context_parts.append("User context:")
        context_parts.append(user_ctx)
        context_parts.append("")
    
    # 2. Thread context
    thread_ctx = build_thread_context(
        channel_id=channel_id,
        thread_ts=thread_ts,
        limit=100,
    )
    if thread_ctx:
        context_parts.append(thread_ctx)
        context_parts.append("")
    
    # 3. Agent memories (new structured memory system)
    # Use user_query if provided, otherwise extract from thread context
    query_text: str | None = user_query
    if not query_text and thread_ctx:
        # Extract key terms from recent thread messages for memory search
        # Get last few messages from thread context to extract keywords
        try:
            thread_lines = thread_ctx.split("\n")
            # Extract user messages (lines that might contain questions/requests)
            recent_messages = [line for line in thread_lines[-20:] if ":" in line and not line.strip().startswith("-")]
            if recent_messages:
                # Use last few messages as query context for memory search
                query_text = " ".join(recent_messages[-3:])[:200]  # Last 3 messages, truncated
        except Exception:
            pass  # Fallback to scope-only search
    
    memory_ctx = build_memory_context(
        user_sub=user_sub,
        rfp_id=rfp_id,
        query_text=query_text,
        limit=15,  # Get more memories for better relevance
    )
    if memory_ctx:
        context_parts.append(memory_ctx)
        context_parts.append("")
    
    # 4. RFP state context (if RFP is known)
    if rfp_id:
        rfp_ctx = build_rfp_state_context(rfp_id=rfp_id, journal_limit=10, events_limit=10)
        if rfp_ctx:
            context_parts.append(rfp_ctx)
            context_parts.append("")
        
        # 5. Related RFPs
        related_ctx = build_related_rfps_context(rfp_id=rfp_id, limit=5)
        if related_ctx:
            context_parts.append(related_ctx)
            context_parts.append("")
        
        # 6. Recent jobs
        jobs_ctx = build_recent_jobs_context(rfp_id=rfp_id, limit=10)
        if jobs_ctx:
            context_parts.append(jobs_ctx)
            context_parts.append("")
        
        # 7. Cross-thread context
        cross_thread_ctx = build_cross_thread_context(
            rfp_id=rfp_id,
            current_channel_id=channel_id,
            current_thread_ts=thread_ts,
            limit=5,
        )
        if cross_thread_ctx:
            context_parts.append(cross_thread_ctx)
            context_parts.append("")
    
    # Add external context if query provided (real-world context)
    external_ctx_text = ""
    if user_query:
        try:
            external_ctx = get_external_context_for_query(
                query=user_query,
                limit_per_type=3,  # Limit to avoid token bloat
            )
            if external_ctx.get("ok"):
                external_ctx_text = format_external_context_for_prompt(
                    external_context=external_ctx,
                    max_chars=1500,  # Limit external context size
                )
                if external_ctx_text:
                    context_parts.append(external_ctx_text)
                    context_parts.append("")
        except Exception:
            # Non-critical: external context fetch failures shouldn't break context building
            pass
    
    # Add token budget awareness if tracker provided
    if token_budget_tracker:
        budget_status = token_budget_tracker.get_budget_status_message()
        context_parts.append("")
        context_parts.append("=== TOKEN_BUDGET_STATUS ===")
        context_parts.append(budget_status)
        context_parts.append("")
        context_parts.append("IMPORTANT: Continue working on the problem until the budget is exhausted.")
        context_parts.append("If you have an answer but budget remains: validate/verify, generate additional insights, explore alternatives.")
        context_parts.append("When budget is critical (≤10% remaining), prioritize providing final answer.")
        context_parts.append("")
    
    # Combine all context
    full_context = "\n".join(context_parts).strip()
    
    # Apply smart truncation with priority preservation
    if len(full_context) > max_total_chars:
        # Priority order: user context > thread context > memory context > RFP context > others
        # Calculate space needed for high-priority sections
        high_priority_sections = []
        high_priority_sections.append(user_ctx)
        high_priority_sections.append(thread_ctx)
        high_priority_sections.append(memory_ctx)
        
        high_priority_len = sum(len(s) + 50 for s in high_priority_sections if s)  # +50 overhead per section
        remaining_space = max_total_chars - high_priority_len - 300  # Reserve buffer
        
        if remaining_space > 1000:  # Only include lower-priority sections if we have space
            # Context is fine as-is
            return full_context
        else:
            # Truncate lower-priority sections
            # Build truncated version with high-priority sections full, others truncated
            truncated_parts = []
            if user_ctx:
                truncated_parts.append("User context:")
                truncated_parts.append(user_ctx)
                truncated_parts.append("")
            if thread_ctx:
                truncated_parts.append(thread_ctx)
                truncated_parts.append("")
            if memory_ctx:
                truncated_parts.append(memory_ctx)
                truncated_parts.append("")
            
            # Add truncated lower-priority sections if space allows
            remaining_for_low_priority = max_total_chars - sum(len(s) + 20 for s in truncated_parts)
            if remaining_for_low_priority > 500:
                # Add other sections with truncation
                other_context = "\n".join(context_parts[3:])  # Skip first 3 (already included)
                if other_context:
                    truncated_other = clip_text(other_context, max_chars=remaining_for_low_priority - 100)
                    truncated_parts.append(truncated_other)
                    if len(other_context) > len(truncated_other):
                        truncated_parts.append("\n[Additional context truncated for length...]")
            
            return "\n".join(truncated_parts).strip()
    
    return full_context

