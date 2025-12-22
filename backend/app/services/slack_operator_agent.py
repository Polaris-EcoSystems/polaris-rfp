from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field

from ..ai.client import AiNotConfigured, _client
from ..ai.context import normalize_ws
from ..ai.tuning import tuning_for
from ..observability.logging import get_logger
from ..settings import settings
from .agent_events_repo import append_event, list_recent_events
from ..repositories.rfp.agent_journal_repo import append_entry, list_recent_entries
from .agent_jobs_repo import (
    create_job as create_agent_job,
    get_job as get_agent_job,
    list_recent_jobs,
    list_jobs_by_scope,
    list_jobs_by_type,
    claim_due_jobs,
)
from .agent_policy import sanitize_opportunity_patch
from .change_proposals_repo import create_change_proposal
from ..repositories.rfp.opportunity_state_repo import ensure_state_exists, get_state, patch_state
from .slack_thread_bindings_repo import get_binding as get_thread_binding, set_binding as set_thread_binding
from .slack_reply_tools import ask_clarifying_question, post_summary
from ..tools.categories.slack.slack_read import get_thread as slack_get_thread
from .slack_web import get_user_info, slack_user_display_name
from .slack_formatting_guide import SLACK_FORMATTING_GUIDE

# Reuse proven OpenAI tool-call plumbing from slack_agent to avoid divergence.
from . import slack_agent as _sa


log = get_logger("slack_operator_agent")


def _detect_and_store_collaboration(
    *,
    channel_id: str,
    thread_ts: str | None,
    current_user_id: str,
    current_slack_user_id: str | None,
    rfp_id: str | None,
    slack_team_id: str | None,
    user_message: str,
    agent_response: str,
) -> None:
    """
    Detect collaboration patterns from thread participants and store COLLABORATION_CONTEXT memory.
    
    Checks if multiple users have interacted in the thread/channel and creates a collaboration memory.
    """
    if not thread_ts:
        return  # Need thread to detect collaboration
    
    try:
        # Get thread messages to find participants
        result = slack_get_thread(channel=channel_id, thread_ts=thread_ts, limit=50)
        if not result.get("ok"):
            return
        
        messages = result.get("messages", [])
        if not isinstance(messages, list) or len(messages) < 2:
            return  # Need at least 2 messages for collaboration
        
        # Extract unique user IDs from thread (excluding bot messages)
        participant_slack_ids: set[str] = set()
        participant_cognito_ids: set[str] = set()
        
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            msg_user = str(msg.get("user") or "").strip()
            if not msg_user:
                continue
            
            # Skip bot messages (typically start with 'B' in Slack)
            if msg_user.startswith("B"):
                continue
            
            participant_slack_ids.add(msg_user)
            
            # Try to resolve to cognito user ID
            try:
                from .identity_service import resolve_from_slack
                user_identity = resolve_from_slack(slack_user_id=msg_user)
                if user_identity.user_sub:
                    participant_cognito_ids.add(user_identity.user_sub)
            except Exception:
                pass  # Can't resolve, use slack ID only
        
        # Add current user
        participant_cognito_ids.add(current_user_id)
        if current_slack_user_id:
            participant_slack_ids.add(current_slack_user_id)
        
        # Only create collaboration memory if we have 2+ unique participants
        if len(participant_cognito_ids) < 2 and len(participant_slack_ids) < 2:
            return
        
        # Determine collaboration type based on message content
        collaboration_type: str | None = None
        msg_lower = (user_message + " " + agent_response).lower()
        if any(term in msg_lower for term in ["review", "feedback", "approve", "comment"]):
            collaboration_type = "review"
        elif any(term in msg_lower for term in ["decision", "decide", "choose", "select"]):
            collaboration_type = "decision_making"
        elif any(term in msg_lower for term in ["design", "plan", "architecture"]):
            collaboration_type = "design_session"
        elif any(term in msg_lower for term in ["code", "implement", "develop"]):
            collaboration_type = "code_collaboration"
        else:
            collaboration_type = "discussion"
        
        # Create collaboration context memory
        from ..memory.core.agent_memory_collaboration import add_collaboration_context_memory
        
        participant_list = list(participant_cognito_ids) if participant_cognito_ids else list(participant_slack_ids)
        content = f"Collaboration in thread: {user_message[:200]}"
        if agent_response:
            content += f"\nAgent response: {agent_response[:200]}"
        
        add_collaboration_context_memory(
            participant_user_ids=participant_list,
            content=content,
            collaboration_type=collaboration_type,
            success=True,  # Assume success if agent responded
            context={
                "channelId": channel_id,
                "threadTs": thread_ts,
                "messageCount": len(messages),
            },
            cognito_user_id=current_user_id,
            slack_user_id=current_slack_user_id,
            slack_channel_id=channel_id,
            slack_thread_ts=thread_ts,
            slack_team_id=slack_team_id,
            rfp_id=rfp_id,
            source="slack_operator",
        )
        
        log.info(
            "collaboration_memory_created",
            participant_count=len(participant_list),
            collaboration_type=collaboration_type,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )
    except Exception as e:
        log.warning("collaboration_detection_error", error=str(e))


def _detect_and_store_temporal_events(
    *,
    user_message: str,
    user_sub: str,
    rfp_id: str | None,
    channel_id: str | None,
    thread_ts: str | None,
    cognito_user_id: str | None,
    slack_user_id: str | None,
    slack_team_id: str | None,
) -> None:
    """
    Detect temporal events (deadlines, meetings, milestones) from user message and store TEMPORAL_EVENT memory.
    
    Uses regex patterns to find dates and temporal references.
    """
    from datetime import datetime, timedelta, timezone
    import re
    
    msg_lower = user_message.lower()
    
    # Patterns for temporal references
    temporal_keywords = [
        "deadline", "due", "due date", "by", "before", "after", "on",
        "meeting", "call", "standup", "review", "milestone", "deliverable",
        "submit", "submission", "presentation", "demo", "launch", "release",
    ]
    
    # Check if message contains temporal keywords
    has_temporal_keyword = any(keyword in msg_lower for keyword in temporal_keywords)
    if not has_temporal_keyword:
        return  # No temporal references found
    
    # Try to extract dates using various patterns
    date_patterns = [
        # MM/DD/YYYY or M/D/YYYY
        r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',
        # YYYY-MM-DD
        r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',
        # "January 15, 2024" or "Jan 15, 2024"
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})\b',
        # "15 January 2024"
        r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b',
        # Relative dates: "tomorrow", "next week", "in 3 days"
        r'\b(tomorrow|next week|next month|in (\d+) days?|in (\d+) weeks?)\b',
    ]
    
    event_date: datetime | None = None
    event_type: str | None = None
    
    # Determine event type from keywords
    if any(term in msg_lower for term in ["deadline", "due", "due date", "submit", "submission"]):
        event_type = "deadline"
    elif any(term in msg_lower for term in ["meeting", "call", "standup"]):
        event_type = "meeting"
    elif any(term in msg_lower for term in ["milestone", "deliverable"]):
        event_type = "milestone"
    elif any(term in msg_lower for term in ["review", "demo", "presentation"]):
        event_type = "review"
    else:
        event_type = "event"
    
    # Try to parse dates
    for pattern in date_patterns:
        matches = re.finditer(pattern, user_message, re.IGNORECASE)
        for match in matches:
            try:
                groups = match.groups()
                if len(groups) == 3:
                    # Try MM/DD/YYYY format
                    try:
                        month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                        # Check if it's MM/DD or DD/MM (US vs international)
                        if month > 12:
                            # Likely DD/MM/YYYY
                            day, month = month, day
                        event_date = datetime(year, month, day, tzinfo=timezone.utc)
                        break
                    except (ValueError, TypeError):
                        pass
            except Exception:
                continue
    
    # If no explicit date found, try relative dates
    if not event_date:
        now = datetime.now(timezone.utc)
        if "tomorrow" in msg_lower:
            event_date = now + timedelta(days=1)
        elif "next week" in msg_lower:
            event_date = now + timedelta(weeks=1)
        elif "next month" in msg_lower:
            event_date = now + timedelta(days=30)
        else:
            # Look for "in X days/weeks"
            relative_match = re.search(r'in (\d+) (days?|weeks?)', msg_lower)
            if relative_match:
                try:
                    amount = int(relative_match.group(1))
                    unit = relative_match.group(2)
                    if "week" in unit:
                        event_date = now + timedelta(weeks=amount)
                    else:
                        event_date = now + timedelta(days=amount)
                except (ValueError, TypeError):
                    pass
    
    # Only create temporal event if we found a date or strong temporal reference
    if not event_date and not any(strong_term in msg_lower for strong_term in ["deadline", "due date", "meeting"]):
        return  # Not enough temporal information
    
    # Use current time + 7 days as default if no date found but has strong temporal keyword
    if not event_date:
        event_date = datetime.now(timezone.utc) + timedelta(days=7)
    
    # Determine scope
    scope_id = f"RFP#{rfp_id}" if rfp_id else f"USER#{user_sub}"
    
    # Create temporal event memory
    from ..memory.core.agent_memory_temporal import add_temporal_event_memory
    
    event_at_iso = event_date.isoformat().replace("+00:00", "Z")
    content = f"Temporal event mentioned: {user_message[:300]}"
    
    add_temporal_event_memory(
        scope_id=scope_id,
        content=content,
        event_at=event_at_iso,
        event_type=event_type,
        rfp_id=rfp_id,
        metadata={
            "extractedFrom": user_message[:200],
            "confidence": "medium" if event_date else "low",
        },
        cognito_user_id=cognito_user_id,
        slack_user_id=slack_user_id,
        slack_channel_id=channel_id,
        slack_thread_ts=thread_ts,
        slack_team_id=slack_team_id,
        source="slack_operator",
    )
    
    log.info(
        "temporal_event_memory_created",
        event_type=event_type,
        event_at=event_at_iso,
        scope_id=scope_id,
    )


def _link_memories_after_interaction(
    *,
    user_sub: str,
    rfp_id: str | None,
    channel_id: str | None,
    thread_ts: str | None,
) -> None:
    """
    Link memories after an interaction to create relationship graph.
    
    Links:
    - Episodic memory → RFP memory (if rfp_id present)
    - Episodic memory → User memories
    - Episodic memory → Collaboration context (if collaboration detected)
    - Episodic memory → Temporal events (if temporal events detected)
    """
    try:
        from ..memory.core.agent_memory_db import list_memories_by_scope, get_memory
        from ..memory.relationships.agent_memory_relationships import add_relationship
        
        # Get the most recent episodic memory for this user
        scope_id = f"USER#{user_sub}"
        memories, _ = list_memories_by_scope(
            scope_id=scope_id,
            memory_type="EPISODIC",
            limit=1,
        )
        
        if not memories:
            return  # No episodic memory to link
        
        episodic_memory = memories[0]
        episodic_id = episodic_memory.get("memoryId")
        episodic_type = episodic_memory.get("memoryType")
        episodic_scope = episodic_memory.get("scopeId")
        episodic_created = episodic_memory.get("createdAt")
        
        if not all([episodic_id, episodic_type, episodic_scope, episodic_created]):
            return
        
        # Verify episodic memory exists using get_memory (ensures we have valid memory before linking)
        if (isinstance(episodic_id, str) and isinstance(episodic_type, str) and 
            isinstance(episodic_scope, str) and isinstance(episodic_created, str)):
            verified_episodic = get_memory(
                memory_id=episodic_id,
                memory_type=episodic_type,
                scope_id=episodic_scope,
                created_at=episodic_created,
            )
            if not verified_episodic:
                return  # Memory doesn't exist or couldn't be fetched
        else:
            return  # Invalid memory identifiers
        
        # Link to RFP if present
        if rfp_id:
            rfp_scope = f"RFP#{rfp_id}"
            rfp_memories, _ = list_memories_by_scope(
                scope_id=rfp_scope,
                memory_type="EPISODIC",  # Try to find related RFP episodic memories
                limit=1,
            )
            if rfp_memories:
                rfp_mem = rfp_memories[0]
                rfp_mem_id = rfp_mem.get("memoryId")
                rfp_mem_type = rfp_mem.get("memoryType")
                rfp_mem_scope = rfp_mem.get("scopeId")
                rfp_mem_created = rfp_mem.get("createdAt")
                
                if all([rfp_mem_id, rfp_mem_type, rfp_mem_scope, rfp_mem_created]):
                    # Verify RFP memory exists using get_memory before linking
                    if (isinstance(rfp_mem_id, str) and isinstance(rfp_mem_type, str) and
                        isinstance(rfp_mem_scope, str) and isinstance(rfp_mem_created, str) and
                        isinstance(episodic_id, str) and isinstance(episodic_type, str) and 
                        isinstance(episodic_scope, str) and isinstance(episodic_created, str)):
                        # Type narrowing: all values are confirmed to be str at this point
                        verified_rfp_mem = get_memory(
                            memory_id=str(rfp_mem_id),
                            memory_type=str(rfp_mem_type),
                            scope_id=str(rfp_mem_scope),
                            created_at=str(rfp_mem_created),
                        )
                        if verified_rfp_mem:
                            add_relationship(
                                from_memory_id=str(episodic_id),
                                from_memory_type=str(episodic_type),
                                from_scope_id=str(episodic_scope),
                                from_created_at=str(episodic_created),
                                to_memory_id=str(rfp_mem_id),
                                to_memory_type=str(rfp_mem_type),
                                to_scope_id=str(rfp_mem_scope),
                                to_created_at=str(rfp_mem_created),
                                relationship_type="part_of",
                                bidirectional=True,
                            )
        
        # Link to collaboration context if present
        if channel_id and thread_ts:
            # Try to find recent collaboration memories
            # (This is a simplified approach - full implementation would query by participants)
            try:
                from ..memory.core.agent_memory_db import list_memories_by_type
                collab_memories, _ = list_memories_by_type(
                    memory_type="COLLABORATION_CONTEXT",
                    scope_id=None,  # Search across scopes
                    limit=5,
                )
                # Find collaboration memory with matching channel/thread
                for collab_mem in collab_memories:
                    metadata = collab_mem.get("metadata", {})
                    if (metadata.get("channelId") == channel_id and 
                        metadata.get("threadTs") == thread_ts):
                        collab_id = collab_mem.get("memoryId")
                        collab_type = collab_mem.get("memoryType")
                        collab_scope = collab_mem.get("scopeId")
                        collab_created = collab_mem.get("createdAt")
                        
                        if all([collab_id, collab_type, collab_scope, collab_created]):
                            if (isinstance(episodic_id, str) and isinstance(episodic_type, str) and 
                                isinstance(episodic_scope, str) and isinstance(episodic_created, str) and
                                isinstance(collab_id, str) and isinstance(collab_type, str) and
                                isinstance(collab_scope, str) and isinstance(collab_created, str)):
                                add_relationship(
                                    from_memory_id=episodic_id,
                                    from_memory_type=episodic_type,
                                    from_scope_id=episodic_scope,
                                    from_created_at=episodic_created,
                                    to_memory_id=collab_id,
                                    to_memory_type=collab_type,
                                    to_scope_id=collab_scope,
                                    to_created_at=collab_created,
                                    relationship_type="part_of",
                                    bidirectional=True,
                                )
                                break
            except Exception:
                pass  # Non-critical
        
        # Link to temporal events if present
        try:
            from ..memory.core.agent_memory_temporal import get_upcoming_events
            temporal_events = get_upcoming_events(
                user_sub=user_sub,
                rfp_id=rfp_id,
                days_ahead=7,
                limit=1,
            )
            if temporal_events:
                temp_mem = temporal_events[0]
                temp_id = temp_mem.get("memoryId")
                temp_type = temp_mem.get("memoryType")
                temp_scope = temp_mem.get("scopeId")
                temp_created = temp_mem.get("createdAt")
                
                if all([temp_id, temp_type, temp_scope, temp_created]):
                    if (isinstance(episodic_id, str) and isinstance(episodic_type, str) and 
                        isinstance(episodic_scope, str) and isinstance(episodic_created, str) and
                        isinstance(temp_id, str) and isinstance(temp_type, str) and
                        isinstance(temp_scope, str) and isinstance(temp_created, str)):
                        add_relationship(
                            from_memory_id=episodic_id,
                            from_memory_type=episodic_type,
                            from_scope_id=episodic_scope,
                            from_created_at=episodic_created,
                            to_memory_id=temp_id,
                            to_memory_type=temp_type,
                            to_scope_id=temp_scope,
                            to_created_at=temp_created,
                            relationship_type="temporal_sequence",
                            bidirectional=True,
                        )
        except Exception:
            pass  # Non-critical
        
        log.info("memory_relationships_created", episodic_id=episodic_id)
    except Exception as e:
        log.warning("memory_linking_error", error=str(e))


# Slack bot token scopes - capabilities the agent has
SLACK_BOT_SCOPES = """
You have full org-wide Slack permissions. Key capabilities:
- Read/write messages: Can read and send messages in all channels (public/private/DMs) you're in, including channels you're not a member of (chat:write.public)
- Channel management: Join, create, manage public/private channels; invite members; set topics/descriptions
- Direct messages: Start DMs and group DMs with any user; read/write DM history
- Files: Read, upload, edit, delete files shared in channels/DMs
- User access: Read user profiles, email addresses, workspace info
- Search: Search files, public channels, and users across the workspace
- Other capabilities: Manage bookmarks, pins, reactions, reminders, workflows, triggers, user groups, canvases, lists, calls, etc.

You do NOT need permission to access channels - you have full org-wide access. You can identify channels by name or ID, and can read messages even if you haven't been explicitly invited. You should never claim you lack permissions or need to be invited.
"""


# Agent Jobs System Documentation
AGENT_JOBS_SYSTEM_DOCS = """
Agent Jobs System Architecture:
- Jobs are executed by NorthStar Job Runner, an ECS task that runs every 4 hours
- Jobs are queued with a `due_at` ISO timestamp (e.g., "2024-01-15T10:30:00Z")
- Jobs execute asynchronously; results are stored in the job record after completion
- Jobs can be scoped to an RFP (via scope.rfpId) or be global (no rfpId in scope)
- Use `agent_job_list` to see scheduled/running/completed jobs, `agent_job_get` to see details by ID
- Jobs run in the background; check status using job query tools
"""


AGENT_JOB_TYPES_DOCS = """
Available Job Types (use with schedule_job tool):

RFP/Opportunity Management:
- `opportunity_maintenance` / `perch_refresh` - Sync RFP state from platform (stage, dueDates, proposalIds, contractingCaseId)
  * Scope: REQUIRED (scope.rfpId)
  * Payload: {} (no payload needed)
  * Behavior: Fetches current state from platform and updates OpportunityState

- `opportunity_compact` / `memory_compact` - Compact journal entries for an RFP to reduce storage
  * Scope: REQUIRED (scope.rfpId)
  * Payload: {"journalLimit": 25} (optional, default 25)
  * Behavior: Keeps only the most recent N journal entries

Agent Operations:
- `agent_daily_digest` - Generate and send daily Slack reports
  * Scope: Global (use {} or {"env": "production"})
  * Payload: {"hours": 24} (optional, default 24)
  * Behavior: Generates digest, sends to configured Slack channel, reschedules itself

- `agent_perch_time` / `telemetry_self_improve` - Run self-improvement/analysis tasks
  * Scope: Global
  * Payload: {"hours": 6, "rescheduleMinutes": 60} (optional)
  * Behavior: Analyzes telemetry/logs, extracts patterns from completed jobs, updates procedural memory with successful workflows and failure patterns, may reschedule itself

Notifications:
- `slack_nudge` - Send a Slack notification message
  * Scope: REQUIRED (scope.rfpId)
  * Payload: {"channel": "C123456", "threadTs": "1234567890.123456", "text": "Message text"}
  * Behavior: Posts message to specified Slack channel/thread

Self-Modification Pipeline (GitHub PR automation):
- `self_modify_open_pr` - Open a GitHub PR for a change proposal
  * Scope: Optional (scope.rfpId)
  * Payload: {"proposalId": "cp_...", "_actorSlackUserId": "U123", "channelId": "C123", "threadTs": "123.456", "rfpId": "rfp_..."}
  * Behavior: Creates GitHub PR from change proposal, posts result to Slack

- `self_modify_check_pr` - Check status of GitHub PR checks
  * Scope: Optional (scope.rfpId)
  * Payload: {"pr": "123" or "https://github.com/.../pull/123", "channelId": "C123", "threadTs": "123.456", "rfpId": "rfp_..."}
  * Behavior: Checks PR status, reports to Slack

- `self_modify_verify_ecs` - Verify ECS service rollout completed successfully
  * Scope: Optional (scope.rfpId)
  * Payload: {"timeoutSeconds": 600, "pollSeconds": 10, "channelId": "C123", "threadTs": "123.456", "rfpId": "rfp_..."}
  * Behavior: Polls ECS service until stable or timeout, reports to Slack

AI Agent Workloads:
- `ai_agent_ask` - Run an AI agent question workload (sandboxed)
  * Scope: Optional
  * Payload: {"question": "...", "userId": "U123", "userDisplayName": "...", "userEmail": "...", "userProfile": {...}, "channelId": "C123", "threadTs": "123.456", "maxSteps": 6}
  * Behavior: Runs agent question processing, stores result in job

- `ai_agent_analyze` - AI analysis workload (placeholder for future expansion)
  * Scope: Optional
  * Payload: {"analysisType": "..."}
  * Behavior: Currently returns "not_implemented"

- `ai_agent_analyze_rfps` - Long-running: Deep analysis across multiple RFPs (supports checkpoint/resume)
  * Scope: Optional (can include rfpId for context)
  * Payload: {"rfpIds": ["rfp_...", "rfp_..."], "analysisType": "..."}
  * Behavior: Analyzes multiple RFPs, checkpoints progress, can resume across job runner cycles
  * Note: Automatically checkpoints before ECS task timeout, resumes on next run

- `ai_agent_monitor_conditions` - Watch for conditions and take action (long-running)
  * Scope: Optional
  * Payload: {"conditions": [...], "actions": [...], "checkIntervalMinutes": 15}
  * Behavior: Monitors conditions, takes action when met, checkpoints state

- `ai_agent_solve_problem` - Multi-step problem resolution (long-running)
  * Scope: Optional
  * Payload: {"problem": "...", "constraints": {...}, "maxSteps": 50}
  * Behavior: Breaks problem into steps, solves iteratively, checkpoints progress

- `ai_agent_maintain_data` - Data cleanup and synchronization (long-running)
  * Scope: Optional
  * Payload: {"operation": "...", "targets": [...]}
  * Behavior: Performs maintenance operations, checkpoints progress

- `ai_agent_execute` - Universal job executor (can handle any user request)
  * Scope: Optional (can include rfpId for context)
  * Payload: {"request": "User's request/goal", "context": {...}, "execution_plan": {...}}
  * Behavior: Uses AI to plan and execute any user request. Automatically plans execution steps, handles failures with self-healing, and learns from outcomes. Supports checkpointing for long-running operations.
  * Examples:
    - "Find me a web development RFP in the next 24 hours"
    - "Search state/local procurement portals for website redesign opportunities"
    - "Download and upload RFP PDFs matching specific criteria"
  * Note: This is an open-ended job type that can handle virtually any request using available tools
"""


AGENT_TOOL_CATEGORIES_DOCS = """
Tool Categories Overview:

RFP/Proposal Browsing:
- list_rfps, search_rfps, get_rfp - Browse and search RFPs
- list_proposals, get_proposal - Browse proposals
- list_tasks - View workflow tasks

Opportunity State Management:
- opportunity_load - Load OpportunityState + journal + events for an RFP
- opportunity_patch - Update OpportunityState (durable artifact)
- journal_append - Add journal entry (decision narrative)
- event_append - Add event log entry (tool calls, decisions)

Slack Operations:
- slack_get_thread - Fetch thread conversation history
- slack_list_recent_messages - List recent channel messages
- slack_post_summary - Post summary to Slack thread (use after state updates)
- slack_ask_clarifying_question - Ask blocking clarifying question (rare)
- slack_send_dm - Send a direct message to a Slack user by their user ID (use when user asks to DM someone)

Agent Jobs:
- schedule_job - Schedule a job for later execution (dueAt ISO time)
- agent_job_list - List jobs with filtering (status, jobType, rfpId)
- agent_job_get - Get job details by ID
- agent_job_query_due - Query due/overdue queued jobs
- job_plan - Plan a job execution for a user request (returns execution plan before scheduling)

Infrastructure/AWS Tools:
- dynamodb_* - Query/describe DynamoDB tables
- s3_* - S3 operations (head, presign)
- telemetry_* - CloudWatch Logs Insights queries
- logs_discover_for_ecs - Discover log groups for an ECS service (self-introspection)
- logs_list_available - List available log groups (self-introspection, uses pre-loaded config)
- ecs_metadata_introspect - Self-discover ECS task/cluster/service info
- infrastructure_config_summary - Get complete infrastructure configuration (pre-loaded at startup: GitHub repos, ECS, log groups, DynamoDB, S3, SQS, Cognito, Secrets)
- github_discover_config - Discover GitHub repo configuration (uses pre-loaded config)
- browser_* - Browser automation (Playwright)
- github_* - GitHub API operations
- aws_ecs_* - ECS service operations

Action Proposal:
- propose_action - Propose platform action for user confirmation (does not execute)
"""


@dataclass(frozen=True)
class SlackOperatorResult:
    did_post: bool
    text: str | None = None
    meta: dict[str, Any] | None = None


# Template-based metaprompts are generated inline in _match_metaprompt_template
# (Pydantic models can't be in module-level dicts, so we create them on-demand)


def _match_metaprompt_template(question: str, rfp_id: str | None) -> MetapromptAnalysis | None:
    """Check if question matches a known template pattern."""
    q_lower = question.lower().strip()
    
    # Check for update status patterns
    if any(phrase in q_lower for phrase in ["update status", "change status", "set status"]) and rfp_id:
        return MetapromptAnalysis(
            intent="update_rfp_state",
            complexity="simple",
            required_tools=["opportunity_load", "opportunity_patch", "journal_append"],
            likely_steps=3,
            missing_info=[],
            confidence=0.95,
            reasoning="User wants to update RFP status. Requires: opportunity_load → opportunity_patch → journal_append",
        )
    
    # Check for query patterns
    if any(phrase in q_lower for phrase in ["what is", "tell me about", "show me", "what's the"]) and ("rfp" in q_lower or "proposal" in q_lower):
        return MetapromptAnalysis(
            intent="query",
            complexity="simple",
            required_tools=["get_rfp"],
            likely_steps=1,
            missing_info=[],
            confidence=0.90,
            reasoning="User wants information about an RFP. Read-only operation, no RFP scope needed if general query",
        )
    
    # Check for create/upload new RFP patterns
    if any(phrase in q_lower for phrase in ["upload", "create new", "new rfp", "brand new"]) and ("rfp" in q_lower or "opportunity" in q_lower):
        return MetapromptAnalysis(
            intent="create_rfp",
            complexity="moderate",
            required_tools=["slack_get_thread", "rfp_create_from_slack_file"],
            likely_steps=2,
            missing_info=[],
            confidence=0.90,
            reasoning="User wants to create new RFP from file. No RFP scope needed - this creates a NEW RFP",
        )
    
    # Check for schedule job patterns
    if any(phrase in q_lower for phrase in ["schedule job", "queue job", "run job"]) and not rfp_id:
        return MetapromptAnalysis(
            intent="schedule_job",
            complexity="simple",
            required_tools=["schedule_job"],
            likely_steps=1,
            missing_info=[],
            confidence=0.90,
            reasoning="User wants to schedule a job. Global operation, no RFP scope needed unless RFP ID provided",
        )
    
    return None


def _generate_structured_metaprompt(
    *,
    question: str,
    rfp_id: str | None,
    user_id: str | None,
    comprehensive_ctx: str | None,
    model: str,
    client: Any,
) -> MetapromptAnalysis:
    """
    Generate structured metaprompt analysis using GPT-5.2.
    
    Returns structured analysis with intent, complexity, required tools, etc.
    Uses templates for common patterns (fast path), falls back to LLM, then keyword-based.
    """
    if not question or not question.strip():
        return MetapromptAnalysis(
            intent="unknown",
            complexity="simple",
            required_tools=[],
            likely_steps=1,
            missing_info=[],
            confidence=0.0,
            reasoning="Empty question provided",
        )
    
    # Try template-based matching first (fast, no LLM call)
    template_match = _match_metaprompt_template(question, rfp_id)
    if template_match:
        log.info("metaprompt_template_matched", intent=template_match.intent, question=question[:50])
        return template_match
    
    try:
        metaprompt_system = "\n".join([
            "You are analyzing a user's request to generate structured analysis that will guide an AI agent.",
            "Your job is to determine:",
            "1. User's intent (e.g., 'update_rfp_state', 'query_rfp_info', 'schedule_job', 'create_rfp', 'get_help')",
            "2. Complexity level: 'simple' (1-3 steps), 'moderate' (4-6 steps), or 'complex' (7+ steps or multi-turn)",
            "3. Required tools (e.g., 'opportunity_load', 'opportunity_patch', 'journal_append', 'get_rfp', 'schedule_job')",
            "4. Estimated steps needed",
            "5. Missing information that might be needed (e.g., 'rfp_id', 'user_email', 'channel_id')",
            "",
            "Context available:",
            f"- RFP scope: {rfp_id or 'none (global operations allowed)'}",
            f"- User ID: {user_id or 'unknown'}",
            f"- Available context: {'Yes (comprehensive context provided)' if comprehensive_ctx else 'Limited'}",
            "",
            "User's question:",
            question,
            "",
            "Provide structured analysis as JSON.",
        ])
        
        from ..ai.client import call_json, AiUpstreamError, AiNotConfigured
        
        try:
            analysis, _ = call_json(
                purpose="metaprompt_analysis",
                response_model=MetapromptAnalysis,
                messages=[
                    {"role": "system", "content": metaprompt_system},
                    {"role": "user", "content": "Analyze this request and provide structured analysis."},
                ],
                temperature=0.3,
                max_tokens=400,
                retries=1,
                timeout_s=10,
            )
            return analysis
        except (AiUpstreamError, AiNotConfigured) as e:
            log.warning("structured_metaprompt_failed", error=str(e), question=question[:100])
            return _generate_fallback_structured_metaprompt(question=question, rfp_id=rfp_id)
    except Exception as e:
        log.warning("structured_metaprompt_exception", error=str(e), question=question[:100])
        return _generate_fallback_structured_metaprompt(question=question, rfp_id=rfp_id)


def _generate_fallback_structured_metaprompt(*, question: str, rfp_id: str | None) -> MetapromptAnalysis:
    """Generate keyword-based fallback structured metaprompt when LLM call fails."""
    if not question:
        return MetapromptAnalysis(
            intent="unknown",
            complexity="simple",
            required_tools=[],
            likely_steps=1,
            missing_info=[],
            confidence=0.3,
            reasoning="Empty question - fallback analysis",
        )
    
    q_lower = question.lower()
    
    # Determine intent
    intent = "query"
    if any(term in q_lower for term in ["update", "change", "modify", "patch", "set"]):
        if any(term in q_lower for term in ["rfp", "opportunity", "state", "journal"]):
            intent = "update_rfp_state"
        else:
            intent = "update"
    elif any(term in q_lower for term in ["create", "add", "new", "upload"]):
        if "rfp" in q_lower or "opportunity" in q_lower:
            intent = "create_rfp"
        else:
            intent = "create"
    elif any(term in q_lower for term in ["schedule", "queue", "run", "job"]):
        intent = "schedule_job"
    elif any(term in q_lower for term in ["what", "who", "when", "where", "how", "tell me", "show me", "list"]):
        intent = "query"
    
    # Determine complexity
    complexity = "simple"
    if any(term in q_lower for term in ["and", "also", "then", "after", "multiple", "several", "all"]):
        complexity = "moderate"
    if any(term in q_lower for term in ["analyze", "compare", "evaluate", "review", "comprehensive"]):
        complexity = "complex"
    
    # Determine likely tools
    required_tools: list[str] = []
    if any(term in q_lower for term in ["opportunity", "journal", "state", "patch"]):
        required_tools.append("opportunity_load")
        if any(term in q_lower for term in ["update", "change", "modify", "patch"]):
            required_tools.append("opportunity_patch")
            required_tools.append("journal_append")
    if "rfp" in q_lower or "proposal" in q_lower:
        if intent != "create_rfp":
            required_tools.append("get_rfp")
    if "job" in q_lower or "schedule" in q_lower:
        required_tools.append("schedule_job")
    
    # Estimate steps
    likely_steps = 2 if complexity == "simple" else (4 if complexity == "moderate" else 6)
    
    # Missing info
    missing_info: list[str] = []
    if ("rfp" in q_lower or "opportunity" in q_lower) and not rfp_id:
        missing_info.append("rfp_id")
    
    return MetapromptAnalysis(
        intent=intent,
        complexity=complexity,
        required_tools=required_tools,
        likely_steps=likely_steps,
        missing_info=missing_info,
        confidence=0.5,  # Lower confidence for fallback
        reasoning=f"Keyword-based fallback analysis: intent={intent}, complexity={complexity}",
    )


def _generate_metaprompt(
    *,
    question: str,
    rfp_id: str | None,
    user_id: str | None,
    comprehensive_ctx: str | None,
    model: str,
    client: Any,
) -> str:
    """
    Generate a metaprompt by analyzing the user's request (legacy string format).
    
    Now uses structured analysis internally and formats as text for backward compatibility.
    """
    analysis = _generate_structured_metaprompt(
        question=question,
        rfp_id=rfp_id,
        user_id=user_id,
        comprehensive_ctx=comprehensive_ctx,
        model=model,
        client=client,
    )
    
    # Format structured analysis as readable text
    parts: list[str] = []
    parts.append(f"Intent: {analysis.intent} (complexity: {analysis.complexity})")
    if analysis.required_tools:
        parts.append(f"Likely tools: {', '.join(analysis.required_tools)}")
    if analysis.missing_info:
        parts.append(f"May need: {', '.join(analysis.missing_info)}")
    parts.append(f"Estimated steps: {analysis.likely_steps}")
    if analysis.reasoning:
        parts.append(f"Analysis: {analysis.reasoning}")
    
    return ". ".join(parts) + "."
    """
    Generate a metaprompt by analyzing the user's request.
    
    The metaprompt helps the agent:
    1. Understand what the user is really asking for
    2. Determine the type of operation (query, action, multi-step workflow)
    3. Identify relevant tools and skills needed
    4. Assess complexity and whether multi-turn loops are needed
    5. Identify what information might be missing
    
    Returns a formatted metaprompt string for inclusion in the system prompt.
    """
    if not question or not question.strip():
        return ""
    
    try:
        metaprompt_system = "\n".join([
            "You are analyzing a user's request to generate a metaprompt that will guide an AI agent.",
            "Your job is to think deeply about what the user is asking and determine:",
            "1. What is the user's true intent/goal?",
            "2. What type of operation is this? (query, action, multi-step workflow, information gathering, etc.)",
            "3. What tools/skills are most relevant? (RFP browsing, state management, job scheduling, team member lookup, etc.)",
            "4. Is this a simple request (can be answered in 1-2 steps) or complex (requires multi-turn iteration)?",
            "5. What information might be needed that isn't immediately available?",
            "6. Are there team members, RFPs, or other entities that should be considered?",
            "",
            "Context available:",
            f"- RFP scope: {rfp_id or 'none (global operations allowed)'}",
            f"- User ID: {user_id or 'unknown'}",
            f"- Available context: {'Yes (comprehensive context provided)' if comprehensive_ctx else 'Limited'}",
            "",
            "User's question:",
            question,
            "",
            "Generate a concise metaprompt (2-4 sentences) that captures your analysis.",
            "Format it as a thinking/analysis section that will guide the agent's approach.",
        ])
        
        # Use a quick, low-cost call to generate the metaprompt
        # Make it resilient to failures - metaprompt is helpful but not critical
        from ..ai.client import call_text, AiUpstreamError, AiNotConfigured
        
        try:
            metaprompt_text, _ = call_text(
                purpose="metaprompt_generation",
                messages=[
                    {"role": "system", "content": metaprompt_system},
                    {"role": "user", "content": "Analyze this request and generate the metaprompt."},
                ],
                temperature=0.3,
                max_tokens=300,
                retries=1,  # Quick retry, but don't spend too much time on this
                timeout_s=10,  # Short timeout since it's non-critical
            )
            
            return metaprompt_text.strip() if metaprompt_text else ""
        except (AiUpstreamError, AiNotConfigured) as e:
            # API errors - log and provide simple fallback metaprompt
            log.warning("metaprompt_generation_failed", error=str(e), question=question[:100], error_type=type(e).__name__)
            # Provide a simple keyword-based fallback metaprompt
            return _generate_fallback_metaprompt(question=question, rfp_id=rfp_id)
    except Exception as e:
        # Catch-all for any other unexpected errors
        log.warning("metaprompt_generation_failed", error=str(e), question=question[:100], error_type=type(e).__name__)
        # Provide a simple keyword-based fallback metaprompt
        return _generate_fallback_metaprompt(question=question, rfp_id=rfp_id)


def _generate_fallback_metaprompt(*, question: str, rfp_id: str | None) -> str:
    """
    Generate a simple keyword-based fallback metaprompt when LLM call fails.
    
    This provides basic analysis without requiring an API call.
    """
    if not question:
        return ""
    
    q_lower = question.lower()
    analysis_parts: list[str] = []
    
    # Determine operation type
    if any(term in q_lower for term in ["what", "who", "when", "where", "how", "tell me", "show me", "list"]):
        analysis_parts.append("This appears to be an information query")
    elif any(term in q_lower for term in ["create", "add", "update", "change", "modify", "schedule", "run"]):
        analysis_parts.append("This appears to be an action request")
    elif any(term in q_lower for term in ["find", "search", "look for", "discover"]):
        analysis_parts.append("This appears to be a search/discovery request")
    else:
        analysis_parts.append("This appears to be a general request")
    
    # Assess complexity
    if any(term in q_lower for term in ["and", "also", "then", "after", "multiple", "several"]):
        analysis_parts.append("that may require multiple steps")
    else:
        analysis_parts.append("that can likely be handled in a few steps")
    
    # RFP awareness
    if rfp_id:
        analysis_parts.append("within an RFP context")
    else:
        analysis_parts.append("potentially requiring global operations")
    
    return ". ".join(analysis_parts) + "."


def _generate_tool_recommendations(
    *,
    analysis: MetapromptAnalysis,
    rfp_id: str | None,
    procedural_memories: list[dict[str, Any]] | None = None,
) -> str:
    """
    Generate tool recommendations based on structured metaprompt analysis.
    
    Returns formatted string with recommended tools and reasoning.
    """
    recommendations: list[str] = []
    
    # Use required_tools from analysis as primary recommendations
    if analysis.required_tools:
        recommendations.append("Recommended tools based on analysis:")
        for tool in analysis.required_tools[:5]:  # Limit to top 5
            recommendations.append(f"  - {tool}")
    
    # Add protocol recommendations for RFP-scoped operations
    if rfp_id and any(tool in analysis.required_tools for tool in ["opportunity_patch", "journal_append", "event_append"]):
        if "opportunity_load" not in analysis.required_tools:
            recommendations.append("  - opportunity_load (required before RFP write operations)")
    
    # Add recommendations based on procedural memory patterns if available
    if procedural_memories:
        # Extract common tool sequences from successful patterns
        common_tools: set[str] = set()
        for mem in procedural_memories[:3]:  # Top 3 patterns
            metadata = mem.get("metadata", {})
            tool_seq = metadata.get("toolSequence", [])
            if tool_seq and isinstance(tool_seq, list):
                common_tools.update(tool_seq[:3])  # First 3 tools from each pattern
        
        if common_tools and common_tools != set(analysis.required_tools):
            additional = common_tools - set(analysis.required_tools)
            if additional:
                recommendations.append("\nTools commonly used for similar requests:")
                for tool in list(additional)[:3]:
                    recommendations.append(f"  - {tool} (from successful patterns)")
    
    if not recommendations:
        return ""
    
    return "\n".join(recommendations)


def _extract_relevant_tool_categories_from_analysis(analysis: MetapromptAnalysis) -> str:
    """
    Extract relevant tool categories from structured metaprompt analysis.
    
    Returns a formatted string listing relevant tool categories.
    """
    relevant_categories: list[str] = []
    
    # Use structured analysis to determine categories
    intent_lower = analysis.intent.lower()
    required_tools_lower = [t.lower() for t in analysis.required_tools]
    
    # RFP/Proposal operations
    if any(tool in required_tools_lower for tool in ["opportunity_load", "opportunity_patch", "journal_append", "event_append", "get_rfp"]):
        relevant_categories.append("- Opportunity State Management (opportunity_load, opportunity_patch, journal_append, event_append)")
        relevant_categories.append("- RFP/Proposal Browsing (list_rfps, search_rfps, get_rfp, list_proposals)")
    elif any(term in intent_lower for term in ["rfp", "opportunity", "proposal"]):
        relevant_categories.append("- RFP/Proposal Browsing (list_rfps, search_rfps, get_rfp, list_proposals)")
    
    # Job operations
    if any(tool in required_tools_lower for tool in ["schedule_job", "agent_job"]):
        relevant_categories.append("- Agent Jobs (schedule_job, agent_job_list, agent_job_get, job_plan)")
    elif "job" in intent_lower or "schedule" in intent_lower:
        relevant_categories.append("- Agent Jobs (schedule_job, agent_job_list, agent_job_get, job_plan)")
    
    # Team member operations
    if any(tool in required_tools_lower for tool in ["get_team_member", "list_team_members"]):
        relevant_categories.append("- Team Member Lookup (get_team_member, list_team_members)")
    
    # Slack operations
    if any(tool in required_tools_lower for tool in ["slack_get_thread", "slack_post_summary", "slack_send_dm"]):
        relevant_categories.append("- Slack Operations (slack_get_thread, slack_list_recent_messages, slack_post_summary, slack_send_dm)")
    
    # File/RFP creation
    if "create_rfp" in intent_lower or "rfp_create_from_slack_file" in required_tools_lower:
        relevant_categories.append("- RFP Creation (rfp_create_from_slack_file, slack_get_thread)")
    
    # Query operations
    if analysis.intent == "query" or "get_" in str(required_tools_lower):
        relevant_categories.append("- Read Tools (all read tools from READ_TOOLS registry)")
    
    # Complexity-based guidance
    if analysis.complexity == "complex":
        relevant_categories.append("- Multi-step workflows may be needed - plan carefully and iterate")
    
    if not relevant_categories:
        return "- All tool categories may be relevant"
    
    return "\n".join(relevant_categories)


def _extract_relevant_tool_categories(metaprompt: str) -> str:
    """
    Extract relevant tool categories from text metaprompt (legacy fallback).
    
    Returns a formatted string listing relevant tool categories.
    """
    if not metaprompt:
        return ""
    
    # Simple keyword-based extraction (could be enhanced with LLM call if needed)
    metaprompt_lower = metaprompt.lower()
    
    relevant_categories: list[str] = []
    
    # Check for different operation types
    if any(phrase in metaprompt_lower for phrase in ["rfp", "opportunity", "proposal"]):
        relevant_categories.append("- RFP/Proposal Browsing (list_rfps, search_rfps, get_rfp, list_proposals)")
        relevant_categories.append("- Opportunity State Management (opportunity_load, opportunity_patch, journal_append)")
    
    if any(phrase in metaprompt_lower for phrase in ["job", "schedule", "queue", "background"]):
        relevant_categories.append("- Agent Jobs (schedule_job, agent_job_list, agent_job_get, job_plan)")
    
    if any(phrase in metaprompt_lower for phrase in ["team", "member", "biography", "bio", "capability"]):
        relevant_categories.append("- Team Member Lookup (get_team_member, list_team_members)")
    
    if any(phrase in metaprompt_lower for phrase in ["slack", "message", "thread", "channel"]):
        relevant_categories.append("- Slack Operations (slack_get_thread, slack_list_recent_messages, slack_post_summary)")
    
    if any(phrase in metaprompt_lower for phrase in ["read", "query", "search", "find", "lookup"]):
        relevant_categories.append("- Read Tools (all read tools from READ_TOOLS registry)")
    
    if any(phrase in metaprompt_lower for phrase in ["complex", "multi-step", "workflow", "iterative"]):
        relevant_categories.append("- Multi-step workflows may be needed - plan carefully and iterate")
    
    if not relevant_categories:
        return "- All tool categories may be relevant"
    
    return "\n".join(relevant_categories)


def _extract_rfp_id(text: str) -> str | None:
    t = str(text or "")
    m = re.search(r"\b(rfp_[a-zA-Z0-9-]{6,})\b", t)
    if not m:
        return None
    return str(m.group(1)).strip() or None


def _extract_user_id_from_mention(text: str) -> str | None:
    """
    Extract Slack user ID from a mention in text (e.g., <@U123456> or @Wes).
    Returns the user ID if found, None otherwise.
    """
    t = str(text or "").strip()
    if not t:
        return None
    
    # Try to extract from Slack mention format: <@U123456> or <@W123456>
    mention_match = re.search(r"<@([UW][A-Z0-9]+)>", t)
    if mention_match:
        return str(mention_match.group(1)).strip() or None
    
    # If no mention format found, try to look up by name (requires Slack API call)
    # This is a best-effort lookup - the agent should prefer explicit user IDs
    return None


@dataclass(frozen=True)
class RfpScopeRequirement:
    """Result of RFP scope requirement analysis."""
    requires_rfp: bool | None  # True, False, or None
    confidence: float  # 0.0 to 1.0
    indicators: list[str]  # Which phrases/patterns matched
    reasoning: str  # Brief explanation


class MetapromptAnalysis(BaseModel):
    """Structured analysis of user request."""
    intent: str = Field(description="User's intent, e.g., 'update_rfp_state', 'query', 'schedule_job', 'create_rfp'")
    complexity: str = Field(description="Request complexity: 'simple', 'moderate', or 'complex'")
    required_tools: list[str] = Field(default_factory=list, description="Likely tools needed (e.g., 'opportunity_load', 'opportunity_patch')")
    likely_steps: int = Field(default=3, description="Estimated number of tool call steps needed")
    missing_info: list[str] = Field(default_factory=list, description="Information that might be needed (e.g., 'rfp_id', 'user_email')")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence in this analysis (0.0 to 1.0)")
    reasoning: str = Field(description="Brief explanation of the analysis")


def _classify_rfp_scope_intent_with_ml(
    question: str,
    thread_context: str | None = None,
    has_thread_rfp_binding: bool = False,
    model: str | None = None,
    client: Any | None = None,
) -> RfpScopeRequirement | None:
    """
    Use GPT-5.2 to classify RFP scope intent (optional ML enhancement).
    
    Returns RfpScopeRequirement if successful, None if should fall back to keyword-based.
    """
    if not model or not client:
        return None  # Fall back to keyword-based
    
    try:
        from ..ai.client import call_json, AiUpstreamError, AiNotConfigured
        
        class RfpScopeIntent(BaseModel):
            requires_rfp: bool | None = Field(description="True if requires RFP scope, False if global, None if unclear")
            confidence: float = Field(ge=0.0, le=1.0, description="Confidence 0.0 to 1.0")
            reasoning: str = Field(description="Brief explanation")
        
        prompt = f"""Analyze this user question to determine if it requires RFP scope.

Question: {question}

Context:
- Thread is bound to RFP: {has_thread_rfp_binding}
- Thread context: {thread_context[:200] if thread_context else "None"}

RFP-scoped operations include: opportunity_load, opportunity_patch, journal_append, event_append
Global operations include: schedule_job, agent_job_*, read queries, create new RFP

Determine if this question requires RFP scope (True/False/None) and confidence."""
        
        result, _ = call_json(
            purpose="rfp_scope_intent_classification",
            response_model=RfpScopeIntent,
            messages=[
                {"role": "system", "content": "You classify user questions to determine if they require RFP scope."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,  # Low temperature for classification
            max_tokens=200,
            retries=1,
            timeout_s=5,
        )
        
        return RfpScopeRequirement(
            requires_rfp=result.requires_rfp,
            confidence=result.confidence,
            indicators=["ml_classification"],
            reasoning=result.reasoning,
        )
    except (AiUpstreamError, AiNotConfigured) as e:
        # API errors - log and fall back to keyword-based classification (ML is optional enhancement)
        log.info("ml_rfp_scope_classification_failed", error=str(e), error_type=type(e).__name__)
        return None
    except Exception as e:
        # Other unexpected errors - log and fall back to keyword-based classification
        log.warning("ml_rfp_scope_classification_exception", error=str(e), error_type=type(e).__name__)
        return None


def _operations_requiring_rfp_scope(
    question: str,
    thread_context: str | None = None,
    has_thread_rfp_binding: bool = False,
    use_ml_classification: bool = False,
    model: str | None = None,
    client: Any | None = None,
) -> RfpScopeRequirement:
    """
    Detect if the user's question requires an RFP scope with confidence scoring.
    
    Args:
        question: User's question text
        thread_context: Optional thread conversation history for context-aware detection
        has_thread_rfp_binding: Whether thread is bound to an RFP
    
    Returns:
        RfpScopeRequirement with requires_rfp (True/False/None), confidence, indicators, and reasoning
    """
    q_lower = str(question or "").lower().strip()
    indicators: list[str] = []
    confidence_scores: list[float] = []
    
    # Context-aware adjustment: if thread is bound to RFP, ambiguous queries likely need scope
    context_boost = 0.15 if has_thread_rfp_binding else 0.0
    
    # Explicit indicators that this is NOT about an existing RFP (creating/uploading new RFPs)
    false_indicators = [
        ("isn't about an existing rfp", 0.98),
        ("is not about an existing rfp", 0.98),
        ("not about a specific rfp", 0.95),
        ("not about an rfp", 0.95),
        ("not tied to an rfp", 0.95),
        ("new rfp", 0.90),
        ("brand new", 0.90),
        ("it's new", 0.85),
        ("it is new", 0.85),
        ("upload the file", 0.85),
        ("upload this", 0.85),
        ("upload it", 0.85),
        ("can you upload", 0.85),
        ("upload as", 0.85),
        ("search for", 0.80),
        ("find a new", 0.80),
        ("north star", 0.95),
        ("runner job", 0.95),
        ("schedule a job", 0.90),
        ("create a job", 0.90),
        ("queue a job", 0.90),
    ]
    
    for phrase, conf in false_indicators:
        if phrase in q_lower:
            indicators.append(f"false_indicator:{phrase}")
            confidence_scores.append(conf)
            return RfpScopeRequirement(
                requires_rfp=False,
                confidence=conf,
                indicators=indicators,
                reasoning=f"Question explicitly indicates global operation or new RFP creation: '{phrase}'"
            )
    
    # Questions about the bot itself, its capabilities, tools, or general help
    capability_indicators = [
        ("what tools", 0.95), ("what skills", 0.95), ("what capabilities", 0.95),
        ("what can you", 0.95), ("what are you", 0.95), ("how can you", 0.95),
        ("what do you", 0.90), ("available to you", 0.90), ("available tools", 0.95),
        ("your capabilities", 0.95), ("your skills", 0.95), ("your tools", 0.95),
        ("help me", 0.85), ("how do you", 0.90), ("what memories", 0.95),
        ("types of memories", 0.95), ("what types", 0.90),
    ]
    
    for phrase, conf in capability_indicators:
        if phrase in q_lower:
            indicators.append(f"capability_query:{phrase}")
            confidence_scores.append(conf)
            return RfpScopeRequirement(
                requires_rfp=False,
                confidence=conf,
                indicators=indicators,
                reasoning=f"Question is about bot capabilities/help, not RFP operations: '{phrase}'"
            )
    
    # Operations that typically don't require RFP scope
    job_phrases = ["schedule job", "agent job", "job list", "job status", "query jobs", "runner"]
    if any(phrase in q_lower for phrase in job_phrases):
        # But check if they mention an RFP - if so, it might be scoped
        rfp_id_in_text = _extract_rfp_id(question)
        if rfp_id_in_text:
            indicators.append(f"job_with_rfp:{rfp_id_in_text}")
            return RfpScopeRequirement(
                requires_rfp=True,
                confidence=0.85,
                indicators=indicators,
                reasoning=f"Job operation mentions RFP ID {rfp_id_in_text}, likely RFP-scoped"
            )
        indicators.append("job_operation:global")
        return RfpScopeRequirement(
            requires_rfp=False,
            confidence=0.90,
            indicators=indicators,
            reasoning="Job operation without RFP ID, global operation"
        )
    
    # Operations that clearly require RFP scope (high confidence)
    # Only match specific phrases that unambiguously indicate RFP-scoped write operations
    true_indicators = [
        ("journal entry", 0.95), ("add to journal", 0.95), ("append journal", 0.95),
        ("opportunity state", 0.95), ("update opportunity", 0.95), ("patch opportunity", 0.95),
        ("update the opportunity", 0.95), ("update opportunity state", 0.95),
        ("patch the opportunity", 0.95), ("update rfp", 0.95), ("update the rfp", 0.95),
    ]
    
    for phrase, conf in true_indicators:
        if phrase in q_lower:
            indicators.append(f"true_indicator:{phrase}")
            confidence_scores.append(conf)
            return RfpScopeRequirement(
                requires_rfp=True,
                confidence=conf,
                indicators=indicators,
                reasoning=f"Question explicitly mentions RFP-scoped write operation: '{phrase}'"
            )
    
    # Check if question mentions RFP-related terms that suggest RFP context (ambiguous case)
    rfp_terms = ["rfp", "proposal", "opportunity", "bid"]
    if any(term in q_lower for term in rfp_terms):
        # Context-aware: if thread is bound to RFP, ambiguous queries likely need scope
        if has_thread_rfp_binding:
            indicators.append(f"rfp_term_in_bound_thread:{[t for t in rfp_terms if t in q_lower]}")
            return RfpScopeRequirement(
                requires_rfp=True,
                confidence=0.60 + context_boost,  # Lower confidence, but context suggests RFP scope
                indicators=indicators,
                reasoning="Question mentions RFP-related terms and thread is bound to RFP, likely needs scope"
            )
        
        # But only if it's asking about a specific RFP, not general questions
        general_query_phrases = ["what is", "tell me about", "show me", "list", "search"]
        if any(phrase in q_lower for phrase in general_query_phrases):
            indicators.append(f"general_query_with_rfp_term:{[t for t in rfp_terms if t in q_lower]}")
            return RfpScopeRequirement(
                requires_rfp=False,
                confidence=0.80,
                indicators=indicators,
                reasoning="General query about RFPs, doesn't require specific RFP scope"
            )
        
        # Otherwise might need RFP scope (unclear)
        indicators.append(f"ambiguous_rfp_term:{[t for t in rfp_terms if t in q_lower]}")
        return RfpScopeRequirement(
            requires_rfp=None,
            confidence=0.50,  # Unclear - let conversational agent try first
            indicators=indicators,
            reasoning="Question mentions RFP-related terms but intent is unclear, delegation recommended"
        )
    
    # Default: treat as general question (don't require RFP binding)
    # Only ask for RFP binding if the question clearly requires RFP-scoped operations
    if has_thread_rfp_binding:
        # Thread is bound to RFP but question doesn't mention RFP terms
        # Could be pronoun/anaphora reference ("what's the status?" in RFP thread)
        return RfpScopeRequirement(
            requires_rfp=None,  # Unclear, but thread context suggests might need it
            confidence=0.40 + context_boost,
            indicators=["default_with_rfp_thread_binding"],
            reasoning="No clear RFP indicators in question, but thread is bound to RFP - may be referencing it implicitly"
        )
    
    return RfpScopeRequirement(
        requires_rfp=False,
        confidence=0.85,
        indicators=["default:no_rfp_indicators"],
        reasoning="No RFP-related indicators found, treating as general question"
    )


def _fetch_thread_history(*, channel_id: str, thread_ts: str, limit: int = 50) -> str:
    """
    Fetch thread messages and format them as a readable conversation history.
    Returns a formatted string suitable for inclusion in system prompts.
    """
    try:
        result = slack_get_thread(channel=channel_id, thread_ts=thread_ts, limit=limit)
        if not result.get("ok"):
            return ""
        
        messages = result.get("messages", [])
        if not messages or not isinstance(messages, list):
            return ""
        
        # Format messages in chronological order
        lines: list[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            user_id = str(msg.get("user") or "").strip()
            text = str(msg.get("text") or "").strip()
            
            if not text:
                continue
            
            # Get user display name (cache-friendly, so safe to call)
            user_name = "User"
            if user_id:
                try:
                    user_info = get_user_info(user_id=user_id)
                    user_name = slack_user_display_name(user_info) or user_id
                except Exception:
                    user_name = user_id
            
            # Format: "User: message text"
            lines.append(f"{user_name}: {text}")
        
        if not lines:
            return ""
        
        return "\n".join(lines)
    except Exception:
        # Best-effort: if fetching fails, return empty string (don't break the agent)
        log.warning("thread_history_fetch_failed", channel=channel_id, thread_ts=thread_ts)
        return ""


def _validate_tool_result(*, tool_name: str, result: dict[str, Any]) -> str | None:
    """
    Validate tool result structure before passing to next step.
    
    Returns error message if validation fails, None if valid.
    """
    if not isinstance(result, dict):
        return f"Tool result is not a dict, got {type(result).__name__}"
    
    # All tools should return an "ok" field
    if "ok" not in result:
        return "Tool result missing 'ok' field"
    
    # Check for common required fields based on tool type
    if tool_name == "opportunity_load":
        if result.get("ok") and "opportunity" not in result:
            return "opportunity_load missing 'opportunity' field in success result"
    elif tool_name == "get_rfp":
        if result.get("ok") and "rfpId" not in result:
            return "get_rfp missing 'rfpId' field in success result"
    elif tool_name in ("opportunity_patch", "journal_append", "event_append"):
        if result.get("ok") and "rfpId" not in result:
            return f"{tool_name} missing 'rfpId' field in success result"
    elif tool_name == "rfp_create_from_slack_file":
        if result.get("ok") and "rfpId" not in result:
            return "rfp_create_from_slack_file missing 'rfpId' field in success result"
    
    # Check for error details when ok=False
    if not result.get("ok") and "error" not in result:
        return "Tool result indicates failure but missing 'error' field"
    
    return None


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return _sa._tool_def(name, description, parameters)


ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


def _opportunity_load_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    ensure_state_exists(rfp_id=rid)
    return {
        "ok": True,
        "rfpId": rid,
        "opportunity": get_state(rfp_id=rid),
        "journal": list_recent_entries(rfp_id=rid, limit=int(args.get("journalLimit") or 10)),
        "events": list_recent_events(rfp_id=rid, limit=int(args.get("eventsLimit") or 10)),
    }


def _opportunity_patch_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    p = args.get("patch")
    patch_obj = p if isinstance(p, dict) else {}
    actor = {
        "kind": "slack_operator_agent",
        "slackUserId": str(args.get("slackUserId") or "").strip() or None,
    }
    patch_obj, policy_checks = sanitize_opportunity_patch(patch=patch_obj, actor=actor)
    updated = patch_state(
        rfp_id=rid,
        patch=patch_obj,
        updated_by_user_sub=None,
        create_snapshot=bool(args.get("createSnapshot") is True),
    )
    if policy_checks:
        try:
            append_event(
                rfp_id=rid,
                type="policy_check",
                payload={"tool": "opportunity_patch"},
                tool="opportunity_patch",
                policy_checks=policy_checks,
                created_by="slack_operator_agent",
                correlation_id=str(args.get("correlationId") or "").strip() or None,
            )
        except Exception:
            pass
    return {"ok": True, "rfpId": rid, "opportunity": updated, "policyChecks": policy_checks}


def _journal_append_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    entry = append_entry(
        rfp_id=rid,
        topics=args.get("topics") if isinstance(args.get("topics"), list) else None,
        user_stated=str(args.get("userStated") or "").strip() or None,
        agent_intent=str(args.get("agentIntent") or "").strip() or None,
        what_changed=str(args.get("whatChanged") or "").strip() or None,
        why=str(args.get("why") or "").strip() or None,
        assumptions=args.get("assumptions") if isinstance(args.get("assumptions"), list) else None,
        sources=args.get("sources") if isinstance(args.get("sources"), list) else None,
        created_by_user_sub=None,
        meta=args.get("meta") if isinstance(args.get("meta"), dict) else None,
    )
    return {"ok": True, "entry": entry}


def _event_append_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    ev = append_event(
        rfp_id=rid,
        type=str(args.get("type") or "").strip() or "event",
        payload=args.get("payload") if isinstance(args.get("payload"), dict) else {},
        tool=str(args.get("tool") or "").strip() or None,
        inputs_redacted=args.get("inputsRedacted") if isinstance(args.get("inputsRedacted"), dict) else None,
        outputs_redacted=args.get("outputsRedacted") if isinstance(args.get("outputsRedacted"), dict) else None,
        policy_checks=args.get("policyChecks") if isinstance(args.get("policyChecks"), list) else None,
        confidence_flags=args.get("confidenceFlags") if isinstance(args.get("confidenceFlags"), list) else None,
        downstream_effects=args.get("downstreamEffects") if isinstance(args.get("downstreamEffects"), list) else None,
        created_by=str(args.get("createdBy") or "").strip() or None,
        correlation_id=str(args.get("correlationId") or "").strip() or None,
    )
    return {"ok": True, "event": ev}


def _schedule_job_tool(args: dict[str, Any]) -> dict[str, Any]:
    due_at = str(args.get("dueAt") or "").strip()
    job_type = str(args.get("jobType") or "").strip() or "unknown"
    raw_scope = args.get("scope")
    scope: dict[str, Any] = raw_scope if isinstance(raw_scope, dict) else {}
    raw_payload = args.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    raw_depends_on = args.get("dependsOn")
    depends_on = [str(d).strip() for d in raw_depends_on] if isinstance(raw_depends_on, list) else None
    job = create_agent_job(
        job_type=job_type,
        scope=scope,
        due_at=due_at,
        payload=payload,
        requested_by_user_sub=None,
        depends_on=depends_on,
    )
    return {"ok": True, "job": job}


def _agent_job_list_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(50, int(args.get("limit") or 25)))
    status = str(args.get("status") or "").strip() or None
    job_type = str(args.get("jobType") or "").strip() or None
    rfp_id = str(args.get("rfpId") or "").strip() or None
    
    jobs: list[dict[str, Any]] = []
    
    try:
        if rfp_id:
            # Filter by scope (rfpId)
            scope_filter = {"rfpId": rfp_id}
            jobs = list_jobs_by_scope(scope=scope_filter, limit=limit, status=status)
        elif job_type:
            # Filter by job type
            jobs = list_jobs_by_type(job_type=job_type, limit=limit, status=status)
        else:
            # List all recent jobs
            jobs = list_recent_jobs(limit=limit, status=status)
    except Exception as e:
        return {"ok": False, "error": str(e) or "job_list_failed"}
    
    # Slim payload for each job to avoid bloating response
    slim_jobs: list[dict[str, Any]] = []
    for job in jobs:
        slim: dict[str, Any] = {
            "jobId": job.get("jobId"),
            "jobType": job.get("jobType"),
            "status": job.get("status"),
            "dueAt": job.get("dueAt"),
            "createdAt": job.get("createdAt"),
            "scope": job.get("scope"),
        }
        # Include payload preview (first few keys)
        payload = job.get("payload")
        if isinstance(payload, dict):
            slim["payloadPreview"] = {k: payload.get(k) for k in list(payload.keys())[:5]}
        if "result" in job:
            slim["result"] = job.get("result")
        if "error" in job:
            slim["error"] = job.get("error")
        slim_jobs.append(slim)
    
    return {"ok": True, "jobs": slim_jobs, "count": len(slim_jobs)}


def _agent_job_get_tool(args: dict[str, Any]) -> dict[str, Any]:
    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        return {"ok": False, "error": "missing_jobId"}
    
    try:
        job = get_agent_job(job_id=job_id)
        if not job:
            return {"ok": False, "error": "job_not_found", "jobId": job_id}
        return {"ok": True, "job": job}
    except Exception as e:
        return {"ok": False, "error": str(e) or "job_get_failed"}


def _job_plan_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Plan a job execution for a user request."""
    from .agent_job_planner import plan_job_execution
    
    request = str(args.get("request") or "").strip()
    if not request:
        return {"ok": False, "error": "missing_request"}
    
    context = args.get("context") if isinstance(args.get("context"), dict) else {}
    rfp_id = str(args.get("rfpId") or "").strip() or None
    
    try:
        result = plan_job_execution(
            request=request,
            context=context,
            rfp_id=rfp_id,
        )
        return result
    except Exception as e:
        return {"ok": False, "error": str(e) or "planning_failed"}


def _agent_job_query_due_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(50, int(args.get("limit") or 25)))
    before_iso = str(args.get("beforeIso") or "").strip() or None
    
    try:
        now_iso = before_iso
        due_jobs = claim_due_jobs(now_iso=now_iso, limit=limit)
        
        # Format results
        slim_jobs: list[dict[str, Any]] = []
        for job in due_jobs:
            slim: dict[str, Any] = {
                "jobId": job.get("jobId"),
                "jobType": job.get("jobType"),
                "status": job.get("status"),
                "dueAt": job.get("dueAt"),
                "createdAt": job.get("createdAt"),
                "scope": job.get("scope"),
            }
            payload = job.get("payload")
            if isinstance(payload, dict):
                slim["payloadPreview"] = {k: payload.get(k) for k in list(payload.keys())[:5]}
            slim_jobs.append(slim)
        
        return {"ok": True, "jobs": slim_jobs, "count": len(slim_jobs)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "job_query_due_failed"}

def _create_change_proposal_tool(args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or "").strip()
    summary = str(args.get("summary") or "").strip()
    patch = str(args.get("patch") or "")
    rfp_id = str(args.get("rfpId") or "").strip() or None
    raw_files = args.get("filesTouched")
    files: list[Any] = raw_files if isinstance(raw_files, list) else []
    cp = create_change_proposal(
        title=title or "Change proposal",
        summary=summary or "",
        patch=patch,
        files_touched=[str(x).strip() for x in files if str(x).strip()],
        rfp_id=rfp_id,
        created_by_slack_user_id=str(args.get("createdBySlackUserId") or "").strip() or None,
        meta=args.get("meta") if isinstance(args.get("meta"), dict) else None,
    )
    return {"ok": True, "proposal": {k: v for k, v in cp.items() if k != "patch"}}


def _slack_post_summary_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    ch = str(args.get("channel") or "").strip()
    thread_ts = str(args.get("threadTs") or "").strip() or None
    text = str(args.get("text") or "").strip()
    blocks = args.get("blocks") if isinstance(args.get("blocks"), list) else None
    corr = str(args.get("correlationId") or "").strip() or None
    if not rid or not ch:
        return {"ok": False, "error": "missing_rfp_or_channel"}
    res = post_summary(rfp_id=rid, channel=ch, thread_ts=thread_ts, text=text, blocks=blocks, correlation_id=corr)
    return {"ok": bool(res.get("ok")), "slack": res}


def _slack_ask_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    ch = str(args.get("channel") or "").strip()
    thread_ts = str(args.get("threadTs") or "").strip() or None
    q = str(args.get("question") or "").strip()
    corr = str(args.get("correlationId") or "").strip() or None
    if not rid or not ch:
        return {"ok": False, "error": "missing_rfp_or_channel"}
    res = ask_clarifying_question(rfp_id=rid, channel=ch, thread_ts=thread_ts, question=q, correlation_id=corr)
    return {"ok": bool(res.get("ok")), "slack": res}


def _slack_send_dm_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Send a direct message to a Slack user."""
    from .slack_web import open_dm_channel, chat_post_message_result, get_user_info, lookup_user_id_by_email
    from .identity_service import resolve_from_slack
    
    user_id = str(args.get("userId") or "").strip()
    text = str(args.get("text") or "").strip()
    blocks = args.get("blocks") if isinstance(args.get("blocks"), list) else None
    
    if not user_id or not text:
        return {"ok": False, "error": "missing_user_id_or_text"}
    
    # If user_id looks like a name (not starting with U/W), try to resolve it
    resolved_user_id = user_id
    if not user_id.startswith(("U", "W")):
        # Try to find user by name - check if it's a mention format first
        mention_id = _extract_user_id_from_mention(user_id)
        if mention_id:
            resolved_user_id = mention_id
        else:
            # Try to resolve by email if it looks like an email address
            if "@" in user_id:
                looked_up_id = lookup_user_id_by_email(user_id)
                if looked_up_id:
                    resolved_user_id = looked_up_id
                else:
                    return {"ok": False, "error": "user_not_found_by_email", "hint": f"Could not find Slack user with email: {user_id}"}
            else:
                return {"ok": False, "error": "user_id_must_be_slack_user_id", "hint": "Use Slack user ID format (e.g., U123456), mention format <@U123456>, or email address"}
    
    # Validate the resolved user ID by getting user info
    user_info = get_user_info(user_id=resolved_user_id)
    if not user_info:
        return {"ok": False, "error": "user_not_found", "userId": resolved_user_id, "hint": "Could not find Slack user with the provided identifier"}
    
    # Get additional platform context about the target user (for logging/auditing)
    target_user_ctx = None
    try:
        target_user_identity = resolve_from_slack(slack_user_id=resolved_user_id)
    except Exception:
        # Non-fatal: continue even if platform context resolution fails
        pass
    
    # Open or get DM channel for the user
    dm_channel = open_dm_channel(user_id=resolved_user_id)
    if not dm_channel:
        return {"ok": False, "error": "failed_to_open_dm_channel", "userId": resolved_user_id}
    
    # Send message to DM channel
    res = chat_post_message_result(
        text=text,
        channel=dm_channel,
        blocks=blocks,
        unfurl_links=False,
    )
    
    # Build response with user context information if available
    response = {
        "ok": bool(res.get("ok")),
        "slack": res,
        "dmChannel": dm_channel,
        "userId": resolved_user_id,
    }
    
    # Include user context information if available (for logging/auditing)
    if target_user_ctx:
        if target_user_identity and target_user_identity.email:
            response["userEmail"] = target_user_identity.email
        if target_user_identity and target_user_identity.display_name:
            response["userDisplayName"] = target_user_identity.display_name
    
    return response


def _rfp_create_from_slack_file_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new RFP from a Slack file URL."""
    file_url = str(args.get("fileUrl") or "").strip()
    file_name = str(args.get("fileName") or "upload.pdf").strip() or "upload.pdf"
    channel_id = str(args.get("channelId") or "").strip()
    thread_ts = str(args.get("threadTs") or "").strip() or None
    
    if not file_url:
        return {"ok": False, "error": "missing_file_url"}
    
    try:
        from .slack_web import download_slack_file
        from .rfp_analyzer import analyze_rfp
        from ..repositories.rfp.rfps_repo import create_rfp_from_analysis
        
        def _rfp_url(rfp_id: str) -> str:
            from ..settings import settings
            base = str(settings.frontend_base_url or "").rstrip("/")
            return f"{base}/rfps/{str(rfp_id or '').strip()}"
        
        # Download the file from Slack
        pdf_data = download_slack_file(url=file_url, max_bytes=60 * 1024 * 1024)
        
        # Analyze the RFP
        analysis = analyze_rfp(pdf_data, file_name)
        
        # Create the RFP
        saved = create_rfp_from_analysis(analysis=analysis, source_file_name=file_name, source_file_size=len(pdf_data))
        rfp_id = str(saved.get("_id") or saved.get("rfpId") or "").strip()
        
        if not rfp_id:
            return {"ok": False, "error": "rfp_creation_failed", "hint": "RFP was created but no ID was returned"}
        
        # Post a confirmation message if channel/thread provided
        if channel_id and thread_ts:
            try:
                from .slack_web import chat_post_message_result
                chat_post_message_result(
                    text=f"Created RFP: <{_rfp_url(rfp_id)}|`{rfp_id}`>",
                    channel=channel_id,
                    thread_ts=thread_ts,
                    unfurl_links=False,
                )
            except Exception:
                pass  # Non-fatal if we can't post the message
        
        return {
            "ok": True,
            "rfpId": rfp_id,
            "fileName": file_name,
            "fileSize": len(pdf_data),
        }
    except RuntimeError as e:
        err_msg = str(e) or "analysis_failed"
        if "No extractable text" in err_msg:
            return {"ok": False, "error": "no_extractable_text", "hint": "PDF appears to contain no selectable text (may be a scanned image)"}
        return {"ok": False, "error": "analysis_failed", "hint": err_msg}
    except Exception as e:
        err_msg = str(e) or "creation_failed"
        return {"ok": False, "error": "creation_failed", "hint": err_msg}


OPERATOR_TOOLS: dict[str, tuple[dict[str, Any], ToolFn]] = {
    # Read tools (existing platform browsing).
    **_sa.READ_TOOLS,
    # State artifacts.
    "opportunity_load": (
        _tool_def(
            "opportunity_load",
            "Load the canonical OpportunityState plus recent journal and event log entries.",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "journalLimit": {"type": "integer", "minimum": 1, "maximum": 30},
                    "eventsLimit": {"type": "integer", "minimum": 1, "maximum": 30},
                },
                "required": ["rfpId"],
                "additionalProperties": False,
            },
        ),
        _opportunity_load_tool,
    ),
    "opportunity_patch": (
        _tool_def(
            "opportunity_patch",
            "Patch OpportunityState (durable artifact). Use *_append keys to append to lists; commitments are add-only and require provenance on appended items.",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "patch": {"type": "object"},
                    "createSnapshot": {"type": "boolean"},
                    "slackUserId": {"type": "string", "maxLength": 40},
                    "correlationId": {"type": "string", "maxLength": 120},
                },
                "required": ["rfpId", "patch"],
                "additionalProperties": False,
            },
        ),
        _opportunity_patch_tool,
    ),
    "journal_append": (
        _tool_def(
            "journal_append",
            "Append a journal entry capturing what changed and why (decision narrative).",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "topics": {"type": "array", "items": {"type": "string"}, "maxItems": 25},
                    "userStated": {"type": "string", "maxLength": 2000},
                    "agentIntent": {"type": "string", "maxLength": 800},
                    "whatChanged": {"type": "string", "maxLength": 2000},
                    "why": {"type": "string", "maxLength": 2000},
                    "assumptions": {"type": "array", "items": {"type": "string"}, "maxItems": 50},
                    "sources": {"type": "array", "items": {"type": "object"}, "maxItems": 50},
                    "meta": {"type": "object"},
                },
                "required": ["rfpId"],
                "additionalProperties": False,
            },
        ),
        _journal_append_tool,
    ),
    "event_append": (
        _tool_def(
            "event_append",
            "Append an explainability event (append-only log of tool calls/decisions).",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "type": {"type": "string", "maxLength": 120},
                    "tool": {"type": "string", "maxLength": 120},
                    "payload": {"type": "object"},
                    "inputsRedacted": {"type": "object"},
                    "outputsRedacted": {"type": "object"},
                    "policyChecks": {"type": "array", "items": {"type": "object"}, "maxItems": 50},
                    "confidenceFlags": {"type": "array", "items": {"type": "string"}, "maxItems": 25},
                    "downstreamEffects": {"type": "array", "items": {"type": "object"}, "maxItems": 50},
                    "createdBy": {"type": "string", "maxLength": 120},
                    "correlationId": {"type": "string", "maxLength": 120},
                },
                "required": ["rfpId", "type"],
                "additionalProperties": False,
            },
        ),
        _event_append_tool,
    ),
    "schedule_job": (
        _tool_def(
            "schedule_job",
            "Schedule a one-shot agent job for later execution (dueAt ISO time). Supports long-running jobs with checkpoint/resume.",
            {
                "type": "object",
                "properties": {
                    "dueAt": {"type": "string", "minLength": 1, "maxLength": 40},
                    "jobType": {"type": "string", "minLength": 1, "maxLength": 120},
                    "scope": {"type": "object"},
                    "payload": {"type": "object"},
                    "dependsOn": {"type": "array", "items": {"type": "string"}, "maxItems": 20, "description": "List of job IDs this job depends on (must complete first)"},
                },
                "required": ["dueAt", "jobType", "scope"],
                "additionalProperties": False,
            },
        ),
        _schedule_job_tool,
    ),
    "agent_job_list": (
        _tool_def(
            "agent_job_list",
            "List recent agent jobs with optional filtering by status, jobType, or rfpId scope.",
            {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "status": {"type": "string", "enum": ["queued", "running", "completed", "failed", "cancelled"]},
                    "jobType": {"type": "string", "maxLength": 120},
                    "rfpId": {"type": "string", "maxLength": 120},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _agent_job_list_tool,
    ),
    "agent_job_get": (
        _tool_def(
            "agent_job_get",
            "Get full details of a specific agent job by ID, including result (if completed) or error (if failed).",
            {
                "type": "object",
                "properties": {
                    "jobId": {"type": "string", "minLength": 1, "maxLength": 60},
                },
                "required": ["jobId"],
                "additionalProperties": False,
            },
        ),
        _agent_job_get_tool,
    ),
    "agent_job_query_due": (
        _tool_def(
            "agent_job_query_due",
            "Query jobs that are due or overdue (queued and should have run by now). Useful for checking job backlog.",
            {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "beforeIso": {"type": "string", "maxLength": 40},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _agent_job_query_due_tool,
    ),
    "job_plan": (
        _tool_def(
            "job_plan",
            "Plan a job execution for a user request. Returns execution plan with steps, tools, and estimates. Use this before scheduling a job to verify the plan is correct.",
            {
                "type": "object",
                "properties": {
                    "request": {"type": "string", "description": "User's request/goal", "maxLength": 2000},
                    "context": {"type": "object", "description": "Additional context (rfpId, channelId, etc.)"},
                    "rfpId": {"type": "string", "maxLength": 120},
                },
                "required": ["request"],
                "additionalProperties": False,
            },
        ),
        _job_plan_tool,
    ),
    "create_change_proposal": (
        _tool_def(
            "create_change_proposal",
            "Create a ChangeProposal artifact (patch + rationale) for a future PR. Does not change code.",
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1, "maxLength": 180},
                    "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "patch": {"type": "string", "minLength": 1, "maxLength": 120000},
                    "filesTouched": {"type": "array", "items": {"type": "string"}, "maxItems": 50},
                    "rfpId": {"type": "string", "maxLength": 120},
                    "createdBySlackUserId": {"type": "string", "maxLength": 60},
                    "meta": {"type": "object"},
                },
                "required": ["title", "summary", "patch"],
                "additionalProperties": False,
            },
        ),
        _create_change_proposal_tool,
    ),
    # Slack reply tools.
    "slack_post_summary": (
        _tool_def(
            "slack_post_summary",
            "Post a summary to Slack (threaded) after updating state and logging.",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "channel": {"type": "string", "minLength": 1, "maxLength": 50},
                    "threadTs": {"type": "string", "maxLength": 40},
                    "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "blocks": {"type": "array", "items": {"type": "object"}, "maxItems": 40},
                    "correlationId": {"type": "string", "maxLength": 120},
                },
                "required": ["rfpId", "channel", "text"],
                "additionalProperties": False,
            },
        ),
        _slack_post_summary_tool,
    ),
    "slack_ask_clarifying_question": (
        _tool_def(
            "slack_ask_clarifying_question",
            "Ask a single blocking clarifying question in Slack thread (rare).",
            {
                "type": "object",
                "properties": {
                    "rfpId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "channel": {"type": "string", "minLength": 1, "maxLength": 50},
                    "threadTs": {"type": "string", "maxLength": 40},
                    "question": {"type": "string", "minLength": 1, "maxLength": 1200},
                    "correlationId": {"type": "string", "maxLength": 120},
                },
                "required": ["rfpId", "channel", "question"],
                "additionalProperties": False,
            },
        ),
        _slack_ask_tool,
    ),
    "slack_send_dm": (
        _tool_def(
            "slack_send_dm",
            "Send a direct message to a Slack user by their user ID (e.g., U123456). Use this when the user asks you to DM someone or send them a message privately.",
            {
                "type": "object",
                "properties": {
                    "userId": {"type": "string", "description": "Slack user ID (e.g., U123456) to send DM to", "minLength": 1, "maxLength": 50},
                    "text": {"type": "string", "description": "Message text to send", "minLength": 1, "maxLength": 4000},
                    "blocks": {"type": "array", "items": {"type": "object"}, "maxItems": 40, "description": "Optional Slack Block Kit blocks"},
                },
                "required": ["userId", "text"],
                "additionalProperties": False,
            },
        ),
        _slack_send_dm_tool,
    ),
    "rfp_create_from_slack_file": (
        _tool_def(
            "rfp_create_from_slack_file",
            "Create a new RFP opportunity from a PDF file attached to a Slack message. Use this when the user asks to upload a file as a new RFP opportunity or create a new RFP from a file in the thread. The fileUrl should come from the 'files' array in thread messages (from slack_get_thread).",
            {
                "type": "object",
                "properties": {
                    "fileUrl": {"type": "string", "description": "Slack file download URL (url_private_download or url_private from file metadata)", "minLength": 1, "maxLength": 500},
                    "fileName": {"type": "string", "description": "Name of the file (e.g., 'RFP.pdf')", "minLength": 1, "maxLength": 200},
                    "channelId": {"type": "string", "description": "Channel ID to post confirmation message (optional)", "maxLength": 50},
                    "threadTs": {"type": "string", "description": "Thread timestamp to post confirmation message (optional)", "maxLength": 40},
                },
                "required": ["fileUrl", "fileName"],
                "additionalProperties": False,
            },
        ),
        _rfp_create_from_slack_file_tool,
    ),
}


def run_slack_operator_for_mention(
    *,
    question: str,
    channel_id: str,
    thread_ts: str,
    user_id: str | None,
    correlation_id: str | None = None,
    max_steps: int = 8,
) -> SlackOperatorResult:
    """
    Operator-style Slack agent:
    - reconstructs context from durable artifacts
    - updates state/journal/events
    - replies via Slack tools (not by returning chat text)
    """
    q = normalize_ws(question or "", max_chars=5000)
    ch = str(channel_id or "").strip()
    th = str(thread_ts or "").strip()
    corr = str(correlation_id or "").strip() or None
    if not q or not ch or not th:
        return SlackOperatorResult(did_post=False, text=None, meta={"error": "missing_params"})

    # Best-effort identity resolution for safer write actions (and future "me" support).
    # Use unified identity service
    actor_ctx = None
    actor_user_sub = None
    try:
        from .identity_service import resolve_from_slack

        actor_identity = resolve_from_slack(slack_user_id=user_id)
        actor_user_sub = actor_identity.user_sub
        # Create a compatibility object for existing code
        class _CompatContext:
            def __init__(self, identity):
                self.user_sub = identity.user_sub
                self.email = identity.email
                self.display_name = identity.display_name
                self.user_profile = identity.user_profile
                self.slack_user = identity.slack_user
        actor_ctx = _CompatContext(actor_identity)
    except Exception:
        actor_user_sub = None

    if not settings.openai_api_key:
        raise AiNotConfigured("OPENAI_API_KEY not configured")

    # Thread utilities: remove rfpId friction via thread→rfp binding.
    # - In-thread: "@polaris link rfp_..." binds the thread.
    # - In-thread: "@polaris where" shows current binding.
    try:
        from .slack_web import chat_post_message_result

        m_link = re.match(r"^\s*(link|bind)\s+(rfp_[a-zA-Z0-9-]{6,})\b", q, flags=re.IGNORECASE)
        if m_link:
            rid = str(m_link.group(2) or "").strip()
            set_thread_binding(channel_id=ch, thread_ts=th, rfp_id=rid, bound_by_slack_user_id=user_id)
            chat_post_message_result(
                text=f"Bound this thread to `{rid}`. Future mentions will use that as context.",
                channel=ch,
                thread_ts=th,
                unfurl_links=False,
            )
            return SlackOperatorResult(did_post=True, text=None, meta={"boundRfpId": rid})

        if q.strip().lower() in ("where", "where?"):
            b = get_thread_binding(channel_id=ch, thread_ts=th)
            bound_rid = str((b or {}).get("rfpId") or "").strip() or None
            if bound_rid:
                msg = f"This thread is bound to `{bound_rid}`."
            else:
                msg = "No RFP is bound to this thread yet. Bind it once with: `@polaris link rfp_...`"
            chat_post_message_result(text=msg, channel=ch, thread_ts=th, unfurl_links=False)
            return SlackOperatorResult(did_post=True, text=msg, meta={"boundRfpId": bound_rid})
    except Exception:
        # Never block the operator on thread-binding helpers.
        pass

    # Attempt to scope to an RFP for durable state.
    rfp_id = _extract_rfp_id(q)
    thread_binding = None
    if not rfp_id:
        # Fall back to thread binding.
        try:
            thread_binding = get_thread_binding(channel_id=ch, thread_ts=th)
            rfp_id = str((thread_binding or {}).get("rfpId") or "").strip() or None
        except Exception:
            rfp_id = None
            thread_binding = None

    if not rfp_id:
        # Check if this operation requires RFP scope (with context-aware detection)
        has_thread_binding = bool(thread_binding and thread_binding.get("rfpId"))
        
        try:
            thread_ctx_preview = _fetch_thread_history(channel_id=ch, thread_ts=th, limit=10)
        except Exception:
            thread_ctx_preview = None
        
        # Use keyword-based classification (fast and reliable)
        # ML classification can be enabled later by initializing model/client earlier if needed
        scope_req = _operations_requiring_rfp_scope(
            question=q,
            thread_context=thread_ctx_preview,
            has_thread_rfp_binding=has_thread_binding,
            use_ml_classification=False,
        )
        if not scope_req:
            # Fallback if scope_req is None (shouldn't happen, but be safe)
            scope_req = RfpScopeRequirement(
                requires_rfp=None,
                confidence=0.0,
                indicators=["fallback"],
                reasoning="Classification failed, treating as unclear",
            )
        requires_rfp = scope_req.requires_rfp
        
        # Try delegating to conversational agent for non-RFP questions or unclear cases
        # Use confidence to make nuanced decisions: low confidence False → still try conversational agent first
        if requires_rfp is False:
            # This operation clearly doesn't require RFP scope - delegate to conversational agent
            # (even if confidence is low, False means don't ask for RFP scope)
            try:
                from .slack_web import chat_post_message_result
                from .identity_service import resolve_from_slack

                identity = resolve_from_slack(slack_user_id=user_id)
                display_name = identity.display_name
                email = identity.email
                user_profile = identity.user_profile

                ans = _sa.run_slack_agent_question(
                    question=q,
                    user_id=user_id,
                    user_display_name=display_name,
                    user_email=email,
                    user_profile=user_profile,
                    channel_id=ch,
                    thread_ts=th,
                )
                txt = str(ans.text or "").strip() or "No answer."
                chat_post_message_result(
                    text=txt,
                    channel=ch,
                    thread_ts=th,
                    blocks=ans.blocks,
                    unfurl_links=False,
                )
                return SlackOperatorResult(did_post=True, text=txt, meta={"scoped": False, "delegated": "slack_agent"})
            except Exception as e:
                # Log the error but continue to operator agent without RFP (don't ask for RFP)
                log.warning("slack_agent_delegation_failed", error=str(e), question=q[:100])
                # Continue to operator agent with rfp_id=None - don't ask for RFP
                pass
        elif requires_rfp is None:
            # Unclear - try delegating to conversational agent first
            # This keeps @mentions responsive without requiring thread binding.
            # If confidence is high but still None, we might want to be more cautious
            try:
                from .slack_web import chat_post_message_result
                from .identity_service import resolve_from_slack

                identity = resolve_from_slack(slack_user_id=user_id)
                display_name = identity.display_name
                email = identity.email
                user_profile = identity.user_profile

                ans = _sa.run_slack_agent_question(
                    question=q,
                    user_id=user_id,
                    user_display_name=display_name,
                    user_email=email,
                    user_profile=user_profile,
                    channel_id=ch,
                    thread_ts=th,
                )
                txt = str(ans.text or "").strip() or "No answer."
                chat_post_message_result(
                    text=txt,
                    channel=ch,
                    thread_ts=th,
                    blocks=ans.blocks,
                    unfurl_links=False,
                )
                return SlackOperatorResult(did_post=True, text=txt, meta={"scoped": False, "delegated": "slack_agent"})
            except Exception as e:
                # Fall through to the binding prompt if delegation fails
                log.warning("slack_agent_delegation_failed", error=str(e), question=q[:100])
                pass
        else:
            # requires_rfp is True - this clearly needs RFP scope, so ask for it
            # Only ask for RFP binding if requires_rfp is explicitly True (not None/False)
            if requires_rfp is True:
                # Ask to include an explicit id or bind the thread; keep it short.
                msg = (
                "Which RFP is this about?\n"
                "- include an id like `rfp_...` in your message, or\n"
                "- bind this thread once with: `@polaris link rfp_...`"
                "\n\nIf this isn’t about a specific RFP, use `/polaris ask <question>`."
                )
                try:
                    from .slack_web import chat_post_message_result

                    chat_post_message_result(text=msg, channel=ch, thread_ts=th, unfurl_links=False)
                except Exception:
                    pass
                return SlackOperatorResult(did_post=True, text=msg, meta={"scoped": False})
            # If requires_rfp is False or None, proceed as a general question (no RFP binding required)
    
    # If we have rfp_id, ensure state exists. Otherwise, proceed without it for global operations.
    if rfp_id:
        ensure_state_exists(rfp_id=rfp_id)

    # Initialize model and client early (needed for ML classification if enabled)
    model = settings.openai_model_for("slack_agent")
    client = _client(timeout_s=75)

    tools = [tpl for (tpl, _fn) in OPERATOR_TOOLS.values()]
    # Allow proposing platform actions with human confirmation (existing pattern).
    if bool(settings.slack_agent_actions_enabled):
        tools.append(_sa._propose_action_tool_def())
    # Filter out tools with empty or missing names before conversion
    valid_tools = [
        tpl for tpl in tools
        if isinstance(tpl, dict) and tpl.get("name") and str(tpl.get("name", "")).strip()
    ]
    tool_names = [tpl["name"] for tpl in valid_tools]
    chat_tools = [_sa._to_chat_tool(tpl) for tpl in valid_tools]

    # Use enhanced context builder for comprehensive context
    from .agent_context_builder import (
        build_rfp_state_context,
        build_related_rfps_context,
        build_cross_thread_context,
        build_comprehensive_context,
    )
    from .user_agent_context import build_user_agent_context
    
    # Build user-specific agent context (ties together all interactions with this user)
    # This creates a "user agent" that has robust context on the user
    user_agent_ctx = ""
    if actor_user_sub or user_id:
        try:
            user_agent_ctx = build_user_agent_context(
                slack_user_id=user_id,
                user_sub=actor_user_sub,
                user_profile=actor_ctx.user_profile if actor_ctx else None,
                user_display_name=actor_ctx.display_name if actor_ctx else None,
                user_email=actor_ctx.email if actor_ctx else None,
                channel_id=ch,
                thread_ts=th,
                current_query=q,
                rfp_id=rfp_id,
                include_recent_interactions=True,
                include_preferences=True,
                include_work_patterns=True,
            )
        except Exception as e:
            log.warning("user_agent_context_build_failed", user_id=user_id, error=str(e))
    
    # Build comprehensive context with query-aware retrieval
    # Note: token_budget_tracker is None for slack operator (not a long-running job)
    # Memory retrieval will work without it, but won't be budget-aware
    comprehensive_ctx = build_comprehensive_context(
        user_profile=actor_ctx.user_profile if actor_ctx else None,
        user_display_name=actor_ctx.display_name if actor_ctx else None,
        user_email=actor_ctx.email if actor_ctx else None,
        user_id=user_id,
        channel_id=ch,
        thread_ts=th,
        rfp_id=rfp_id,
        user_query=q,  # Pass user query for query-aware memory retrieval
        max_total_chars=50000,
        token_budget_tracker=None,  # Slack operator doesn't use token budgets (not long-running)
    )
    
    # Build team member awareness context if the query mentions team members or capabilities
    team_awareness_ctx = ""
    if q and any(phrase in q.lower() for phrase in ["team", "member", "biography", "bio", "capability", "skill", "expertise", "who can", "who has"]):
        try:
            from .agent_context_builder import build_user_context
            from . import content_repo
            
            # Build user context for the current user (includes their linked team member info)
            user_ctx = build_user_context(
                user_profile=actor_ctx.user_profile if actor_ctx else None,
                user_display_name=actor_ctx.display_name if actor_ctx else None,
                user_email=actor_ctx.email if actor_ctx else None,
                user_id=user_id,
            )
            
            # Get team members list for awareness
            team_members = content_repo.list_team_members(limit=50)
            if team_members:
                team_summary_lines: list[str] = []
                team_summary_lines.append("Team Member Awareness:")
                # Include current user's context if available
                if user_ctx:
                    team_summary_lines.append("Current User Context:")
                    team_summary_lines.append(user_ctx)
                    team_summary_lines.append("")
                team_summary_lines.append(f"- Total team members in system: {len(team_members)}")
                # Include key team members (first 10) with their positions
                for tm in team_members[:10]:
                    if isinstance(tm, dict):
                        tm_name = str(tm.get("nameWithCredentials") or tm.get("name") or "").strip()
                        tm_position = str(tm.get("position") or "").strip()
                        tm_id = str(tm.get("memberId") or "").strip()
                        if tm_name and tm_id:
                            summary = f"  - {tm_name}"
                            if tm_position:
                                summary += f" ({tm_position})"
                            summary += f" [ID: {tm_id}]"
                            team_summary_lines.append(summary)
                team_summary_lines.append("- Use `get_team_member` or `list_team_members` tools to fetch detailed information about specific team members.")
                team_awareness_ctx = "\n".join(team_summary_lines)
        except Exception as e:
            log.warning("team_awareness_context_build_failed", error=str(e))
            team_awareness_ctx = ""
    
    # Also build individual components for context complexity estimation
    rfp_state_context = build_rfp_state_context(rfp_id=rfp_id, journal_limit=10, events_limit=10) if rfp_id else ""
    related_rfps_context = build_related_rfps_context(rfp_id=rfp_id, limit=5) if rfp_id else ""
    cross_thread_context = build_cross_thread_context(
        rfp_id=rfp_id,
        current_channel_id=ch,
        current_thread_ts=th,
        limit=5,
    ) if rfp_id else ""

    # Generate structured metaprompt analysis
    metaprompt_analysis = _generate_structured_metaprompt(
        question=q,
        rfp_id=rfp_id,
        user_id=user_id,
        comprehensive_ctx=comprehensive_ctx,
        model=model,
        client=client,
    )
    
    # Format metaprompt as text for system prompt (backward compatibility)
    metaprompt = f"Intent: {metaprompt_analysis.intent} (complexity: {metaprompt_analysis.complexity}). {metaprompt_analysis.reasoning}"
    
    # Extract relevant tool categories from structured analysis
    relevant_tool_categories = _extract_relevant_tool_categories_from_analysis(metaprompt_analysis)
    
    # Adaptive max_steps based on complexity analysis
    if metaprompt_analysis.complexity == "simple":
        effective_max_steps = max(3, min(max_steps, 5))  # 3-5 steps for simple
    elif metaprompt_analysis.complexity == "moderate":
        effective_max_steps = max(6, min(max_steps, 10))  # 6-10 steps for moderate
    else:  # complex
        effective_max_steps = max(12, min(max_steps, 20))  # 12-20 steps for complex
    
    # Also consider likely_steps from analysis
    if metaprompt_analysis.likely_steps > effective_max_steps:
        effective_max_steps = min(metaprompt_analysis.likely_steps + 2, max_steps * 2)  # Add buffer
    
    # Retrieve procedural memories for tool guidance
    procedural_guidance = ""
    procedural_memories: list[dict[str, Any]] | None = None
    if actor_user_sub:
        try:
            from ..memory.retrieval.agent_memory_retrieval import get_memories_for_context
            procedural_memories = get_memories_for_context(
                user_sub=actor_user_sub,
                rfp_id=rfp_id,
                query_text=q,  # Use user query to find relevant patterns
                memory_types=["PROCEDURAL"],
                limit=5,  # Get top 5 relevant procedural memories
            )
            
            if procedural_memories:
                tool_patterns: list[str] = []
                for mem in procedural_memories:
                    metadata = mem.get("metadata", {})
                    tool_seq = metadata.get("toolSequence", [])
                    workflow = mem.get("summary") or mem.get("content", "")
                    success = metadata.get("success", True)
                    
                    if tool_seq and isinstance(tool_seq, list) and len(tool_seq) > 0:
                        seq_str = " → ".join([str(t) for t in tool_seq[:5]])  # Limit to 5 tools
                        status = "✓" if success else "✗"
                        pattern = f"  {status} {seq_str}"
                        if workflow:
                            pattern += f" ({workflow[:60]})"
                        tool_patterns.append(pattern)
                
                if tool_patterns:
                    procedural_guidance = "\n".join([
                        "Past Successful Tool Patterns (for similar requests):",
                        *tool_patterns[:3],  # Show top 3 patterns
                        "",
                    ])
        except Exception as e:
            log.warning("procedural_memory_retrieval_failed", error=str(e))
    
    # Tool recommendation engine: recommend specific tools based on analysis and procedural memories
    tool_recommendations = _generate_tool_recommendations(
        analysis=metaprompt_analysis,
        rfp_id=rfp_id,
        procedural_memories=procedural_memories,
    )
    
    # Check for relevant skills if query mentions skills/capabilities
    skills_guidance = ""
    if q and any(term in q.lower() for term in ["skill", "capability", "expertise", "what can", "how to"]):
        try:
            from ..tools.registry.read_registry import READ_TOOLS
            if "skills_search" in READ_TOOLS:
                skills_guidance = (
                    "- Use `skills_search` to find relevant skills/capabilities for this request\n"
                    "- Use `skills_get` to get details about a specific skill\n"
                    "- Use `skills_load` to load and execute a skill\n"
                )
        except Exception:
            pass
    
    # Determine if this is a DM or a channel mention
    is_dm = ch and ch.startswith("D")  # DM channels start with "D" in Slack
    
    system = "\n".join(
        [
            "You are Polaris Operator, a general-purpose Slack-connected agent for an RFP→Proposal→Contracting platform.",
            "You are stateless: you MUST reconstruct context by calling tools every invocation.",
            "",
            "Your Capabilities:",
            "- You have awareness of team members, RFPs, proposals, opportunities, and platform state",
            "- You can read and write platform data, schedule jobs, and execute multi-step workflows",
            "- You can handle both simple queries and complex multi-turn operations",
            "- You are aware of user preferences, team member profiles, and collaboration patterns",
            "- You maintain rich context about each user across all conversations (DMs, mentions, threads)",
            "- Each user has their own 'agent' with persistent context that grows over time",
            "- You can self-introspect your environment: use infrastructure_config_summary for complete pre-loaded config, ecs_metadata_introspect to discover cluster/service info, logs_discover_for_ecs to find log groups, logs_list_available to see accessible log groups, github_discover_config to find GitHub repo configuration",
            "- When troubleshooting infrastructure issues, ALWAYS start by using introspection tools (infrastructure_config_summary, ecs_metadata_introspect, logs_discover_for_ecs, logs_list_available, github_discover_config) rather than asking users for configuration details",
            "- infrastructure_config_summary provides pre-loaded configuration (GitHub repos, ECS clusters/services, log groups, DynamoDB tables, S3 buckets, etc.) - use this for fast access to static infrastructure metadata",
            "- When creating GitHub issues or performing GitHub operations, use github_discover_config or infrastructure_config_summary to find the configured repository name",
            "- If you encounter AccessDeniedException errors (e.g., CloudWatch Logs), clearly explain what permissions are missing and suggest the IAM policy statement needed. Offer to create a GitHub issue to track the fix.",
            "",
            "Metaprompt Analysis (your thinking about this request):",
            metaprompt if metaprompt else "- Analyzing user request...",
            "",
            "Relevant Tool Categories for this request:",
            relevant_tool_categories if relevant_tool_categories else "- All tools available",
            "",
            "Tool Recommendations:" if tool_recommendations else "",
            tool_recommendations if tool_recommendations else "",
            "",
            procedural_guidance if procedural_guidance else "",
            "Skills System:" if skills_guidance else "",
            skills_guidance if skills_guidance else "",
            "Slack Permissions:",
            SLACK_BOT_SCOPES.strip(),
            "",
            "Agent Jobs System:",
            AGENT_JOBS_SYSTEM_DOCS.strip(),
            "",
            "Available Job Types:",
            AGENT_JOB_TYPES_DOCS.strip(),
            "",
            "Tool Categories:",
            AGENT_TOOL_CATEGORIES_DOCS.strip(),
            "",
            "Critical rules:",
            "- Do not treat Slack chat history as truth. Use platform tools + OpportunityState + Journal + Events.",
            "- However, use the thread conversation history below to remember previous context in this thread (channel names, permissions, user preferences, etc.).",
            "- RFP Scope: Some operations require an RFP scope (opportunity_load, opportunity_patch, journal_append, event_append). Others can be global (schedule_job, agent_job_*, read tools).",
            "- When the user explicitly states something is NOT about an existing RFP (e.g., 'create a job to search for new RFPs'), proceed without requiring RFP binding.",
            "- Default to silence. If you need to communicate, use `slack_post_summary` (or `slack_ask_clarifying_question` only when blocking).",
            "- Before posting in RFP-scoped context, update durable artifacts: call `opportunity_patch` and/or `journal_append` so the system remembers.",
            "- Never invent IDs, dates, or commitments. Cite tool output or ask a single clarifying question.",
            "- For code changes: first call `create_change_proposal` (stores a patch + rationale). Then propose an approval-gated action `self_modify_open_pr` with the `proposalId`.",
            "- Use `schedule_job` to queue jobs for the North Star runner. Jobs can have global scope ({} or {\"env\": \"production\"}) or RFP scope ({\"rfpId\": \"rfp_...\"}).",
            "- For open-ended user requests (e.g., 'find me a web development RFP', 'search for opportunities'), use job type `ai_agent_execute` with payload `{\"request\": \"user's request\"}`. This universal executor will plan and execute any request using available tools.",
            "- Use `job_plan` to preview an execution plan before scheduling a job (helps verify the plan is correct).",
            "- Use `agent_job_list` to check job status when users ask about scheduled/running jobs.",
            "- When users ask about their resume, check the user context for resume S3 keys. For PDF or DOCX files, use `extract_resume_text` to extract text content. For plain text files, use `s3_get_object_text`. For binary files that need downloading, use `s3_presign_get` to get a download URL.",
            "- When users ask about their professional background, check both user context (job titles, certifications) and linked team member information (biography, bioProfiles) if available. Use `get_team_member` tool to fetch full team member details if needed.",
            "- For complex requests: Break down into steps, gather information incrementally, and iterate. Use multi-turn loops to work through the problem systematically.",
            "- Team awareness: You have access to team member profiles, biographies, and project-specific bios. Use `get_team_member` or `list_team_members` when users ask about team capabilities or need to match team members to projects.",
            "- Creating new RFPs from files: When users ask to upload a file as a new RFP opportunity (e.g., 'upload this as a new opportunity', 'create a new RFP from the file above', 'it's brand new'), use `slack_get_thread` to find PDF files in the thread, then use `rfp_create_from_slack_file` with the file URL and name. This does NOT require RFP scope - it creates a NEW RFP.",
            "- Error handling: When tools fail, always include the full error message, errorType, and errorCategory in your Slack response. Errors are automatically logged to memory for learning, but you must surface them to users so they understand what went wrong and can provide feedback.",
            "",
            "GPT-5.2 Best Practices:",
            "- You are using GPT-5.2 with the Responses API, which supports passing chain of thought (CoT) between turns for improved intelligence.",
            "- Before calling tools, briefly explain why you're calling them (preambles) - this improves tool-calling accuracy and user confidence.",
            "- Use reasoning effort appropriately: 'none' for simple queries, 'medium' for standard operations, 'high' for complex multi-step tasks, 'xhigh' for very complex persistent problems.",
            "- Verbosity: 'low' for concise answers, 'medium' for balanced responses, 'high' for thorough explanations.",
            "- When a request is complex or persists across many steps, reasoning effort may escalate to 'xhigh' to ensure thorough problem-solving.",
            "",
            "Runtime context:",
            f"- channel: {ch}",
            f"- thread_ts: {th}",
            f"- is_dm: {is_dm}",
            f"- slack_user_id: {str(user_id or '').strip() or '(unknown)'}",
            f"- rfp_id_scope: {rfp_id or '(none - global operations allowed)'}",
            f"- correlation_id: {corr or '(none)'}",
            "",
            "User Context:",
            "- You have access to USER_AGENT_CONTEXT below, which includes:",
            "  * Recent interactions with this user across all channels/threads",
            "  * User preferences, facts, and patterns learned over time",
            "  * Work patterns and successful procedures for this user",
            "  * Related context from other conversations",
            "- Use this context to provide personalized, consistent responses",
            "- Remember what you've discussed with this user before",
            "- Build on previous conversations to provide continuity",
            "",
            "When rfp_id_scope is '(none - global operations allowed)':",
            "- You can use schedule_job, agent_job_*, and read tools without RFP scope.",
            "- You can use slack_post_summary without RFP scope (just omit rfpId or use a placeholder).",
            "- Do NOT try to use opportunity_load, opportunity_patch, journal_append, or event_append without RFP scope.",
            "",
            SLACK_FORMATTING_GUIDE.strip(),
        ]
    )
    
    # Add user-specific agent context (ties together all user interactions)
    # This is added first to give the agent rich context about the user
    if user_agent_ctx:
        system += "\n\n=== USER_AGENT_CONTEXT (Rich Context About This User) ===\n"
        system += user_agent_ctx + "\n"
    
    # Add comprehensive context (includes all context layers)
    if comprehensive_ctx:
        system += "\n\n" + comprehensive_ctx + "\n"
    
    # Add team member awareness if relevant
    if team_awareness_ctx:
        system += "\n\n" + team_awareness_ctx + "\n"

    input0 = f"{system}\n\nUSER_MESSAGE:\n{q}"

    did_post = False
    steps = 0
    did_load = False
    did_patch = False
    did_journal = False
    last_load_time: float | None = None

    def _inject_and_enforce(*, tool_name: str, tool_args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """
        Enforce the operator run protocol:
          - First: opportunity_load (for RFP-scoped operations)
          - Before speaking (slack_post_summary / slack_ask_clarifying_question): write durable artifacts

        Also inject correlationId into relevant tool args for traceability.
        
        Note: Some tools don't require RFP scope (schedule_job, agent_job_*, read tools).
        """
        nonlocal did_load, did_patch, did_journal, last_load_time
        name = str(tool_name or "").strip()
        args2 = tool_args if isinstance(tool_args, dict) else {}

        # Tools that don't require RFP scope (can be used without opportunity_load)
        tools_not_requiring_rfp = {
            "opportunity_load",  # This IS the load operation
            _sa.ACTION_TOOL_NAME,  # propose_action can be global
            "schedule_job",  # Can schedule global jobs
            "agent_job_list",  # Can query jobs without RFP
            "agent_job_get",  # Job lookup by ID
            "agent_job_query_due",  # Query due jobs globally
            "job_plan",  # Job planning tool (doesn't require RFP)
            "create_change_proposal",  # Can be global
        }
        # Also allow all read tools (they're in READ_TOOLS and don't modify state)
        is_read_tool = name in _sa.READ_TOOLS

        # Correlation id propagation (best-effort)
        if corr and isinstance(args2, dict):
            if name in ("event_append", "opportunity_patch", "slack_post_summary", "slack_ask_clarifying_question"):
                if "correlationId" not in args2:
                    args2["correlationId"] = corr
            if name == "journal_append":
                meta_raw = args2.get("meta")
                meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
                if "correlationId" not in meta:
                    meta["correlationId"] = corr
                args2["meta"] = meta

        # Load-first protocol (only for RFP-scoped operations).
        # Skip if no RFP scope OR if tool doesn't require it.
        # Context-aware: if context was recently loaded, we may relax the requirement for read operations
        if rfp_id and name not in tools_not_requiring_rfp and not is_read_tool and not did_load:
            # RFP-scoped operation that requires state reconstruction
            if name not in ("opportunity_load",):
                # Check if context was recently loaded (within last 30 seconds in same invocation)
                # This allows skipping redundant loads in multi-turn conversations
                now = time.time()
                context_freshness = None
                if last_load_time:
                    context_freshness = now - last_load_time
                context_is_fresh = context_freshness is not None and context_freshness < 30.0
                
                # For read-only RFP operations, we might be more lenient
                # But for write operations, we should enforce more strictly
                is_write_operation = name in ("opportunity_patch", "journal_append", "event_append")
                
                if not context_is_fresh or is_write_operation:
                    # Write operations: enforce strictly (always require fresh load)
                    # Read operations: if context is fresh, allow but log suggestion
                    if is_write_operation:
                        # Write operations: enforce more strictly - always need fresh load
                        return args2, {
                            "ok": False,
                            "error": "protocol_missing_opportunity_load",
                            "hint": "Call opportunity_load first to reconstruct context before using other RFP-scoped write tools.",
                        }
                    else:
                        # Read operations: if context is not fresh, suggest but don't block
                        # Agent can proceed but may have stale context
                        log.info(
                            "protocol_suggestion_opportunity_load",
                            tool_name=name,
                            rfp_id=rfp_id,
                            context_age_seconds=context_freshness,
                            hint="Consider calling opportunity_load first for fresh context",
                        )
                        # Don't return error, just log the suggestion - agent can proceed

        # Write-it-down protocol: before posting/asking in RFP-scoped context, ensure we wrote durable artifacts.
        if rfp_id and name in ("slack_post_summary", "slack_ask_clarifying_question") and not (did_patch or did_journal):
            return args2, {
                "ok": False,
                "error": "protocol_missing_state_write",
                "hint": "Before posting, call opportunity_patch and/or journal_append so the system remembers next invocation.",
            }

        return args2, None

    # Use Responses API for GPT-5.2 (primary path) - provides better intelligence through CoT passing
    # Only fall back to Chat Completions if Responses API is not available (legacy SDK)
    # GPT-5.2 works best with Responses API which supports passing chain of thought between turns
    from ..ai.client import _is_gpt5_family as _is_gpt5_family_check
    use_responses_api = _sa._supports_responses_api(client) and _is_gpt5_family_check(model)
    
    if not use_responses_api:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": q},
        ]
        recent_tools_chat: list[str] = []  # Track tool calls for procedural memory (chat_tools path)
        while True:
            steps += 1
            if steps > max(1, int(effective_max_steps)):
                break
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=chat_tools,
                tool_choice="auto",
                temperature=0.2,
                max_completion_tokens=1100,
            )
            calls = _sa._chat_tool_calls(completion)
            if not calls:
                text = (completion.choices[0].message.content or "").strip()
                break

            # Add assistant tool-call message.
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c.get("id"),
                            "type": "function",
                            "function": {
                                "name": (c.get("function") or {}).get("name"),
                                "arguments": (c.get("function") or {}).get("arguments"),
                            },
                        }
                        for c in calls
                    ],
                }
            )

            for c in calls:
                call_id = str(c.get("id") or "").strip()
                fn = c.get("function") if isinstance(c.get("function"), dict) else {}
                name = str((fn or {}).get("name") or "").strip()
                raw_args = (fn or {}).get("arguments")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else {}
                except Exception:
                    args = {}

                args, proto_err = _inject_and_enforce(tool_name=name, tool_args=args if isinstance(args, dict) else {})
                if proto_err is not None:
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": _sa._safe_json(proto_err)})
                    continue

                # Track tool for procedural memory
                if name:
                    recent_tools_chat.append(name)
                    if len(recent_tools_chat) > 10:
                        recent_tools_chat = recent_tools_chat[-10:]

                if name == "slack_post_summary" or name == "slack_ask_clarifying_question":
                    did_post = True

                if name == _sa.ACTION_TOOL_NAME:
                    # Use shared risk model: auto-execute low-risk, confirm risky.
                    ans = _sa._handle_proposed_action(
                        tool_args=args if isinstance(args, dict) else {},
                        slack_user_id=user_id,
                        user_sub=actor_user_sub,
                        channel_id=ch,
                        thread_ts=th,
                        question=q,
                        model=model,
                        steps=steps,
                        response_format="chat_tools",
                    )
                    try:
                        if rfp_id:
                            post_summary(
                                rfp_id=rfp_id,
                                channel=ch,
                                thread_ts=th,
                                text=str(ans.text or "").strip() or "Done.",
                                blocks=ans.blocks,
                                correlation_id=corr,
                            )
                        else:
                            # Post without RFP scope (for global operations)
                            from .slack_reply_tools import chat_post_message_result
                            chat_post_message_result(
                                text=str(ans.text or "").strip() or "Done.",
                                channel=ch,
                                blocks=ans.blocks,
                                thread_ts=th,
                                unfurl_links=False,
                            )
                        did_post = True
                    except Exception:
                        pass
                    return SlackOperatorResult(did_post=did_post, text=None, meta={"steps": steps, "meta": ans.meta})

                tool = OPERATOR_TOOLS.get(name)
                if not tool:
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": _sa._safe_json({"ok": False, "error": "unknown_tool"})})
                    continue
                _tpl, func = tool
                started = time.time()
                try:
                    # Use resilience module for retry and error handling
                    from .agent_resilience import retry_with_classification, classify_error
                    
                    def _execute_tool():
                        return func(args if isinstance(args, dict) else {})
                    
                    result = retry_with_classification(
                        _execute_tool,
                        max_retries=2,
                        base_delay=0.5,
                        max_delay=5.0,
                    )
                except Exception as e:
                    import traceback
                    classification = classify_error(e)
                    error_tb = traceback.format_exc()
                    result = {
                        "ok": False,
                        "error": str(e) or "tool_failed",
                        "errorCategory": classification.category.value,
                        "retryable": classification.retryable,
                        "errorType": type(e).__name__,
                        "errorDetails": {
                            "message": str(e),
                            "category": classification.category.value,
                            "retryable": classification.retryable,
                        },
                    }
                    
                    # Store error log in memory (best-effort, non-blocking)
                    try:
                        from ..memory.core.agent_memory_error_logs import store_error_log
                        from .identity_service import resolve_from_slack
                        from .slack_actor_context import resolve_actor_context
                        
                        # Resolve actor context for provenance
                        # Try new identity service first, fall back to old method for compatibility
                        try:
                            actor_identity_for_error = resolve_from_slack(slack_user_id=user_id)
                            cognito_id = actor_identity_for_error.user_sub or actor_user_sub
                            slack_id = actor_identity_for_error.slack_user_id or user_id
                            team_id = actor_identity_for_error.slack_team_id
                        except Exception:
                            # Fallback to old method if new service fails
                            try:
                                actor_ctx_for_error = resolve_actor_context(slack_user_id=user_id, force_refresh=False)
                                cognito_id = actor_ctx_for_error.user_sub or actor_user_sub
                                slack_id = actor_ctx_for_error.slack_user_id or user_id
                                team_id = actor_ctx_for_error.slack_team_id
                            except Exception:
                                cognito_id = actor_user_sub
                                slack_id = user_id
                                team_id = None
                        
                        store_error_log(
                            tool_name=name,
                            error_message=str(e) or "tool_failed",
                            error_type=type(e).__name__,
                            error_details=result.get("errorDetails"),
                            tool_args=args if isinstance(args, dict) else {},
                            tool_result=result,
                            user_query=q,
                            traceback_str=error_tb,
                            user_sub=actor_user_sub,
                            cognito_user_id=cognito_id,
                            slack_user_id=slack_id,
                            slack_channel_id=ch,
                            slack_thread_ts=th,
                            slack_team_id=team_id,
                            rfp_id=rfp_id,
                            source="slack_operator",
                        )
                    except Exception as storage_err:
                        log.warning("error_log_storage_failed", error=str(storage_err))

                # Track tool failure for learning
                # Validate tool result structure
                validation_error = _validate_tool_result(tool_name=name, result=result)
                if validation_error:
                    log.warning(
                        "tool_result_validation_failed",
                        tool_name=name,
                        error=validation_error,
                    )
                    # Don't fail the tool call, but log the validation issue
                    # The agent can handle invalid results if needed
                
                tool_failed = not bool(result.get("ok"))
                
                # Update protocol flags on success.
                if bool(result.get("ok")):
                    if name == "opportunity_load":
                        did_load = True
                        last_load_time = time.time()  # Track when context was loaded
                    elif name == "opportunity_patch":
                        did_patch = True
                    elif name == "journal_append":
                        did_journal = True
                elif tool_failed and actor_user_sub:
                    # Store failure pattern (best-effort, non-blocking)
                    try:
                        from ..memory.hooks.agent_memory_hooks import store_procedural_memory_from_tool_sequence
                        # Get recent tools up to this point (including the failed one)
                        failed_sequence = recent_tools_chat[-3:] if len(recent_tools_chat) >= 3 else recent_tools_chat
                        if failed_sequence:
                            error_msg = str(result.get("error", "unknown_error")) if isinstance(result, dict) else "tool_failed"
                            # Resolve actor context for provenance (if not already resolved)
                            try:
                                from .identity_service import resolve_from_slack
                                actor_identity_for_failure = resolve_from_slack(slack_user_id=user_id)
                                cognito_id = actor_identity_for_failure.user_sub or actor_user_sub
                                slack_id = actor_identity_for_failure.slack_user_id or user_id
                                team_id = actor_identity_for_failure.slack_team_id
                            except Exception:
                                cognito_id = actor_user_sub
                                slack_id = user_id
                                team_id = None
                            
                            store_procedural_memory_from_tool_sequence(
                                user_sub=actor_user_sub,
                                tool_sequence=failed_sequence,
                                success=False,  # Mark as failure
                                outcome=f"Tool {name} failed: {error_msg}",
                                context={
                                    "rfpId": rfp_id,
                                    "channelId": ch,
                                    "threadTs": th,
                                    "failedTool": name,
                                    "error": error_msg,
                                },
                                cognito_user_id=cognito_id,
                                slack_user_id=slack_id,
                                slack_channel_id=ch,
                                slack_thread_ts=th,
                                slack_team_id=team_id,
                                rfp_id=rfp_id,
                                source="slack_operator",
                            )
                            log.info("tool_failure_memory_stored", tool=name, error=error_msg[:100])
                    except Exception as e:
                        log.warning("tool_failure_memory_store_failed", error=str(e))
                dur_ms = int((time.time() - started) * 1000)
                try:
                    if rfp_id:
                        append_event(
                            rfp_id=rfp_id,
                            type="tool_call",
                            tool=name,
                            payload={"ok": bool(result.get("ok")), "durationMs": dur_ms},
                            inputs_redacted={
                                "argsKeys": [str(k) for k in list((args or {}).keys())[:60]] if isinstance(args, dict) else [],
                            },
                            outputs_redacted={
                                "resultPreview": {k: result.get(k) for k in list(result.keys())[:30]} if isinstance(result, dict) else {},
                            },
                            correlation_id=corr,
                        )
                except Exception:
                    pass
                messages.append({"role": "tool", "tool_call_id": call_id, "content": _sa._safe_json(result)})

        # Fallback: if the model returned plain text, post it.
        if not did_post and text:
            try:
                if rfp_id:
                    post_summary(rfp_id=rfp_id, channel=ch, thread_ts=th, text=text, correlation_id=corr)
                else:
                    # Post without RFP scope
                    from .slack_reply_tools import chat_post_message_result
                    chat_post_message_result(
                        text=text,
                        channel=ch,
                        thread_ts=th,
                        unfurl_links=False,
                    )
                did_post = True
            except Exception:
                pass
        
        # Store episodic memory for this interaction (best-effort, non-blocking)
        # Also detect collaboration patterns and temporal events, and link memories
        if actor_user_sub:
            try:
                from ..memory.hooks.agent_memory_hooks import store_episodic_memory_from_agent_interaction
                # Resolve full actor context for provenance
                slack_user_id_for_memory = user_id
                cognito_user_id_for_memory = actor_user_sub  # actor_user_sub should be cognito sub
                try:
                    from .identity_service import resolve_from_slack
                    actor_identity = resolve_from_slack(slack_user_id=user_id)
                    if actor_identity.user_sub:
                        cognito_user_id_for_memory = actor_identity.user_sub
                    if actor_identity.slack_user_id:
                        slack_user_id_for_memory = actor_identity.slack_user_id
                    slack_team_id_for_memory = actor_identity.slack_team_id
                except Exception:
                    slack_team_id_for_memory = None  # Use defaults if resolution fails
                
                # Store episodic memory with enhanced context
                # Include conversation type (DM vs mention) and user-specific context
                memory_context = {
                    "rfpId": rfp_id,
                    "channelId": ch,
                    "threadTs": th,
                    "steps": steps,
                    "didPost": did_post,
                    "isDm": is_dm,
                    "conversationType": "dm" if is_dm else "mention",
                    "toolsUsed": tool_names[:10] if tool_names else [],  # Track which tools were used
                    "maxSteps": max_steps,
                }
                
                # Add RFP context if available
                if rfp_id:
                    memory_context["rfpScope"] = True
                
                # Store episodic memory
                store_episodic_memory_from_agent_interaction(
                    user_sub=actor_user_sub,
                    user_message=q,
                    agent_response=text or "Action completed",
                    context=memory_context,
                    cognito_user_id=cognito_user_id_for_memory,
                    slack_user_id=slack_user_id_for_memory,
                    slack_channel_id=ch,
                    slack_thread_ts=th,
                    slack_team_id=slack_team_id_for_memory,
                    rfp_id=rfp_id,
                    source="slack_operator",
                )
                
                # Detect and store collaboration context if multiple users in thread
                try:
                    _detect_and_store_collaboration(
                        channel_id=ch,
                        thread_ts=th,
                        current_user_id=cognito_user_id_for_memory,
                        current_slack_user_id=slack_user_id_for_memory,
                        rfp_id=rfp_id,
                        slack_team_id=slack_team_id_for_memory,
                        user_message=q,
                        agent_response=text or "Action completed",
                    )
                except Exception as e:
                    log.warning("collaboration_detection_failed", error=str(e))
                
                # Detect and store temporal events from user message
                try:
                    _detect_and_store_temporal_events(
                        user_message=q,
                        user_sub=actor_user_sub,
                        rfp_id=rfp_id,
                        channel_id=ch,
                        thread_ts=th,
                        cognito_user_id=cognito_user_id_for_memory,
                        slack_user_id=slack_user_id_for_memory,
                        slack_team_id=slack_team_id_for_memory,
                    )
                except Exception as e:
                    log.warning("temporal_event_detection_failed", error=str(e))
                
                # Link memories (episodic → RFP, users, collaboration contexts)
                try:
                    _link_memories_after_interaction(
                        user_sub=actor_user_sub,
                        rfp_id=rfp_id,
                        channel_id=ch,
                        thread_ts=th,
                    )
                except Exception as e:
                    log.warning("memory_linking_failed", error=str(e))
                
                # Store procedural memory from successful tool sequence
                # Only store if we actually used tools and completed successfully
                if did_post and recent_tools_chat:
                    try:
                        from ..memory.hooks.agent_memory_hooks import store_procedural_memory_from_tool_sequence
                        store_procedural_memory_from_tool_sequence(
                            user_sub=actor_user_sub,
                            tool_sequence=recent_tools_chat,
                            success=True,
                            outcome=text or "Action completed successfully",
                            context={
                                "rfpId": rfp_id,
                                "channelId": ch,
                                "threadTs": th,
                                "steps": steps,
                                "userQuery": q,
                                "toolCount": len(recent_tools_chat),
                            },
                            cognito_user_id=cognito_user_id_for_memory,
                            slack_user_id=slack_user_id_for_memory,
                            slack_channel_id=ch,
                            slack_thread_ts=th,
                            slack_team_id=slack_team_id_for_memory,
                            rfp_id=rfp_id,
                            source="slack_operator",
                        )
                        log.info(
                            "procedural_memory_stored",
                            tool_count=len(recent_tools_chat),
                            tool_sequence=recent_tools_chat[:5],  # Log first 5 tools
                        )
                    except Exception as e:
                        log.warning("procedural_memory_store_failed", error=str(e))
            except Exception:
                pass  # Non-critical
        
        return SlackOperatorResult(did_post=did_post, text=None, meta={"steps": steps, "response_format": "chat_tools"})

    prev_id: str | None = None
    recent_tools: list[str] = []  # Track recent tool calls for complexity detection
    conversation_state: dict[str, Any] = {}  # Track conversation state for multi-turn loops
    start_time = time.time()
    
    # Use effective_max_steps calculated from structured metaprompt analysis (already set above)
    # This is more accurate than keyword-based detection
    
    while True:
        steps += 1
        if steps > effective_max_steps:
            # For complex requests that hit step limit, provide a summary
            if metaprompt_analysis.complexity == "complex" and steps > max_steps:
                try:
                    from .slack_web import chat_post_message_result
                    summary_msg = (
                        f"I've been working through your request ({steps-1} steps so far). "
                        "This appears to be a complex multi-step operation. "
                        "Would you like me to continue, or would you prefer to break this down into smaller parts?"
                    )
                    chat_post_message_result(
                        text=summary_msg,
                        channel=ch,
                        thread_ts=th,
                        unfurl_links=False,
                    )
                    did_post = True
                except Exception:
                    pass
            break

        # Get tuning with complexity awareness (including context complexity)
        # Estimate context complexity
        context_len = len(input0) if not prev_id else 0  # Approximate context length
        tuning = tuning_for(
            purpose="slack_agent",
            kind="tools",
            attempt=steps,
            recent_tools=recent_tools[-5:] if recent_tools else None,  # Last 5 tools for context
            context_length=context_len,
            has_rfp_state=bool(rfp_id and rfp_state_context),
            has_related_rfps=bool(related_rfps_context),
            has_cross_thread=bool(cross_thread_context),
            is_long_running=False,
        )

        # Use adaptive timeout based on complexity
        from .agent_resilience import adaptive_timeout
        timeout_seconds = adaptive_timeout(
            base_timeout=75.0,
            complexity_score=1.0 + (len(recent_tools) * 0.1) if recent_tools else 1.0,
            previous_failures=0,
        )
        
        kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "tool_choice": _sa._tool_choice_allowed(tool_names),
            "reasoning": {"effort": tuning.reasoning_effort},
            "text": {"verbosity": tuning.verbosity},
            "max_output_tokens": 1100,
            "timeout": timeout_seconds,
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id
            kwargs["input"] = []
            # For multi-turn loops, add conversation state context
            if conversation_state and metaprompt_analysis.complexity == "complex":
                state_summary = f"\n\nConversation state (step {steps}):\n"
                state_summary += f"- Previous tools used: {', '.join(recent_tools[-5:]) if recent_tools else 'none'}\n"
                state_summary += f"- Steps completed: {steps - 1}\n"
                state_summary += "- Continue working through the request systematically.\n"
                # Note: We can't directly modify input for Responses API, but we can add this to the system context
                # For now, the previous_response_id should carry the context
        else:
            kwargs["input"] = input0

        # Wrap API call with resilience
        from .agent_resilience import retry_with_classification, should_retry_with_adjusted_params
        from ..ai.client import _is_model_access_error, _is_gpt5_family
        
        def _call_api():
            return client.responses.create(**kwargs)
        
        try:
            resp = retry_with_classification(
                _call_api,
                max_retries=2,
                base_delay=1.0,
                max_delay=10.0,
            )
        except Exception as e:
            # If API call fails, try with adjusted parameters or fallback to gpt-5.2-pro
            should_retry, adjusted = should_retry_with_adjusted_params(e, attempt=1)
            if should_retry and adjusted:
                kwargs["reasoning"] = {"effort": adjusted.get("reasoning_effort", "medium")}
                kwargs["max_output_tokens"] = adjusted.get("max_tokens", 1100)
                resp = client.responses.create(**kwargs)
            elif _is_model_access_error(e, model=model):
                # Model access error: try gpt-5.2-pro as fallback for GPT-5.2 models
                if _is_gpt5_family(model) and model != "gpt-5.2-pro":
                    log.info("falling_back_to_gpt52_pro", original_model=model)
                    kwargs["model"] = "gpt-5.2-pro"
                    # gpt-5.2-pro can handle higher reasoning - keep or increase effort
                    if tuning.reasoning_effort in ["high", "xhigh"]:
                        kwargs["reasoning"] = {"effort": "xhigh"}  # Use xhigh for pro model
                    resp = client.responses.create(**kwargs)
                else:
                    raise
            else:
                raise
        prev_id = str(getattr(resp, "id", "") or "") or prev_id

        tool_calls = _sa._extract_tool_calls(resp)
        if not tool_calls:
            text = _sa._responses_text(resp).strip()
            # Check if the agent is indicating it needs more information or wants to continue
            # For complex requests, allow the agent to continue even if it says something
            if metaprompt_analysis.complexity == "complex" and text and any(phrase in text.lower() for phrase in [
                "need more", "gather", "let me", "i'll", "checking", "looking", "searching", "working", "analyzing"
            ]):
                # Agent is working through the problem - continue the loop
                # Add the agent's thinking to conversation state
                conversation_state[f"step_{steps}_thinking"] = text
                # For Responses API, we need to continue with the same response_id
                # The agent's text indicates it wants to continue, so we'll let it proceed
                # by not breaking and allowing the loop to continue
                # However, we need to actually call tools, so we'll treat this as needing more work
                # For now, break but log that we detected continuation intent
                log.info("complex_request_continuation_detected", step=steps, text_preview=text[:100])
            break

        outputs: list[dict[str, Any]] = []
        for call in tool_calls:
            call_id = str(call.get("id") or "").strip()
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str((fn or {}).get("name") or "").strip()
            raw_args = (fn or {}).get("arguments")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else {}
            except Exception:
                args = {}

            # Track tool for complexity detection and conversation state
            if name:
                recent_tools.append(name)
                # Keep only last 10 tools to avoid unbounded growth
                if len(recent_tools) > 10:
                    recent_tools = recent_tools[-10:]
                
                # Track tool failures for learning (store procedural memory with success=False)
                # This will be checked after tool execution

            args, proto_err = _inject_and_enforce(tool_name=name, tool_args=args if isinstance(args, dict) else {})
            if proto_err is not None:
                outputs.append(_sa._tool_output_item(call_id, _sa._safe_json(proto_err)))
                continue
            
            # Track tool calls in conversation state for multi-turn awareness (after protocol check)
            if name:
                tool_call_count = len([t for t in recent_tools if t == name])
                conversation_state[f"step_{steps}_tool_{tool_call_count}"] = {
                    "tool": name,
                    "args_keys": list(args.keys()) if isinstance(args, dict) else [],
                }

            if name in ("slack_post_summary", "slack_ask_clarifying_question"):
                did_post = True

            if name == _sa.ACTION_TOOL_NAME:
                ans = _sa._handle_proposed_action(
                    tool_args=args if isinstance(args, dict) else {},
                    slack_user_id=user_id,
                    user_sub=actor_user_sub,
                    channel_id=ch,
                    thread_ts=th,
                    question=q,
                    model=model,
                    steps=steps,
                    response_format="responses_tools",
                )
                try:
                    if rfp_id:
                        post_summary(
                            rfp_id=rfp_id,
                            channel=ch,
                            thread_ts=th,
                            text=str(ans.text or "").strip() or "Done.",
                            blocks=ans.blocks,
                            correlation_id=corr,
                        )
                    else:
                        # Post without RFP scope
                        from .slack_reply_tools import chat_post_message_result
                        chat_post_message_result(
                            text=str(ans.text or "").strip() or "Done.",
                            channel=ch,
                            blocks=ans.blocks,
                            thread_ts=th,
                            unfurl_links=False,
                        )
                    did_post = True
                except Exception:
                    pass
                return SlackOperatorResult(did_post=did_post, text=None, meta={"steps": steps, "response_format": "responses_tools", "meta": ans.meta})

            tool = OPERATOR_TOOLS.get(name)
            if not tool:
                outputs.append(_sa._tool_output_item(call_id, _sa._safe_json({"ok": False, "error": "unknown_tool"})))
                continue
            _tpl, func = tool
            started = time.time()
            try:
                # Use resilience module for retry and error handling
                from .agent_resilience import retry_with_classification, classify_error
                
                # Track tool failure for learning (will store procedural memory with success=False)
                tool_failed = False
                
                def _execute_tool():
                    return func(args if isinstance(args, dict) else {})
                
                result = retry_with_classification(
                    _execute_tool,
                    max_retries=2,
                    base_delay=0.5,
                    max_delay=5.0,
                    on_retry=lambda exc, attempt: log.warning(
                        "slack_operator_tool_retry",
                        tool=name,
                        attempt=attempt,
                        error=str(exc)[:200],
                    ),
                )
            except Exception as e:
                import traceback
                classification = classify_error(e)
                error_tb = traceback.format_exc()
                result = {
                    "ok": False,
                    "error": str(e) or "tool_failed",
                    "errorCategory": classification.category.value,
                    "retryable": classification.retryable,
                    "errorType": type(e).__name__,
                    "errorDetails": {
                        "message": str(e),
                        "category": classification.category.value,
                        "retryable": classification.retryable,
                    },
                }
                
                # Store error log in memory (best-effort, non-blocking)
                try:
                    from ..memory.core.agent_memory_error_logs import store_error_log
                    from .identity_service import resolve_from_slack
                    
                    # Resolve actor context for provenance
                    try:
                        actor_identity_for_error = resolve_from_slack(slack_user_id=user_id)
                        cognito_id = actor_identity_for_error.user_sub or actor_user_sub
                        slack_id = actor_identity_for_error.slack_user_id or user_id
                        team_id = actor_identity_for_error.slack_team_id
                    except Exception:
                        cognito_id = actor_user_sub
                        slack_id = user_id
                        team_id = None
                    
                    store_error_log(
                        tool_name=name,
                        error_message=str(e) or "tool_failed",
                        error_type=type(e).__name__,
                        error_details=result.get("errorDetails"),
                        tool_args=args if isinstance(args, dict) else {},
                        tool_result=result,
                        user_query=q,
                        traceback_str=error_tb,
                        user_sub=actor_user_sub,
                        cognito_user_id=cognito_id,
                        slack_user_id=slack_id,
                        slack_channel_id=ch,
                        slack_thread_ts=th,
                        slack_team_id=team_id,
                        rfp_id=rfp_id,
                        source="slack_operator",
                    )
                except Exception as storage_err:
                    log.warning("error_log_storage_failed", error=str(storage_err))

            # Update protocol flags on success.
            if bool(result.get("ok")):
                if name == "opportunity_load":
                    did_load = True
                elif name == "opportunity_patch":
                    did_patch = True
                elif name == "journal_append":
                    did_journal = True
            dur_ms = int((time.time() - started) * 1000)
            try:
                # Enhanced telemetry with performance metrics
                telemetry_payload = {
                    "ok": bool(result.get("ok")),
                    "durationMs": dur_ms,
                    "step": steps,
                    "errorCategory": result.get("errorCategory"),
                    "retryable": result.get("retryable"),
                }
                if rfp_id:
                    append_event(
                        rfp_id=rfp_id,
                        type="tool_call",
                        tool=name,
                        payload=telemetry_payload,
                        inputs_redacted={
                            "argsKeys": [str(k) for k in list((args or {}).keys())[:60]] if isinstance(args, dict) else [],
                        },
                        outputs_redacted={
                            "resultPreview": {k: result.get(k) for k in list(result.keys())[:30]} if isinstance(result, dict) else {},
                        },
                        correlation_id=corr,
                    )
                # Also log performance metrics
                log.info(
                    "agent_tool_call",
                    tool=name,
                    ok=bool(result.get("ok")),
                    duration_ms=dur_ms,
                    step=steps,
                    rfp_id=rfp_id,
                    error_category=result.get("errorCategory"),
                )
            except Exception:
                pass
            outputs.append(_sa._tool_output_item(call_id, _sa._safe_json(result)))

        # Get updated tuning with latest tool complexity
        # May escalate to xhigh for very complex persistent operations
        tuning2 = tuning_for(
            purpose="slack_agent",
            kind="tools",
            attempt=steps,
            recent_tools=recent_tools[-5:] if recent_tools else None,
            context_length=len(str(outputs)) if outputs else 0,
            has_rfp_state=bool(rfp_id),
            is_long_running=steps >= 8,  # Consider long-running if many steps
        )
        
        # Try with updated tuning, fallback to gpt-5.2-pro if needed
        try:
            resp2 = client.responses.create(
                model=model,
                previous_response_id=prev_id,
                input=outputs,
                tools=tools,
                tool_choice=_sa._tool_choice_allowed(tool_names),
                reasoning={"effort": tuning2.reasoning_effort},
                text={"verbosity": tuning2.verbosity},
                max_output_tokens=1100,
            )
        except Exception as e2:
            # If second call fails and we're not already on pro, try gpt-5.2-pro
            if _is_model_access_error(e2, model=model) and _is_gpt5_family(model) and model != "gpt-5.2-pro":
                log.info("falling_back_to_gpt52_pro_on_second_call", original_model=model, step=steps)
                resp2 = client.responses.create(
                    model="gpt-5.2-pro",
                    previous_response_id=prev_id,
                    input=outputs,
                    tools=tools,
                    tool_choice=_sa._tool_choice_allowed(tool_names),
                    reasoning={"effort": "xhigh"},  # Use xhigh for pro model on complex operations
                    text={"verbosity": tuning2.verbosity},
                    max_output_tokens=1100,
                )
            else:
                raise
        prev_id = str(getattr(resp2, "id", "") or "") or prev_id
        tool_calls2 = _sa._extract_tool_calls(resp2)
        if tool_calls2:
            continue
        text = _sa._responses_text(resp2).strip()
        break

    # Fallback: if the model returned plain text and did not post, post it.
    if not did_post and text:
        try:
            if rfp_id:
                post_summary(rfp_id=rfp_id, channel=ch, thread_ts=th, text=text, correlation_id=corr)
            else:
                # Post without RFP scope
                from .slack_reply_tools import chat_post_message_result
                chat_post_message_result(
                    text=text,
                    channel=ch,
                    thread_ts=th,
                    unfurl_links=False,
                )
            did_post = True
        except Exception:
            pass

    # Log completion telemetry
    try:
        from .agent_telemetry import track_agent_operation
        
        total_duration = int((time.time() - start_time) * 1000)
        track_agent_operation(
            operation_type="slack_operator_agent",
            purpose="slack_agent",
            duration_ms=total_duration,
            steps=steps,
            success=True,
            tool_count=len(recent_tools),
            metadata={"rfp_id": rfp_id, "did_post": did_post},
        )
        if rfp_id:
            append_event(
                rfp_id=rfp_id,
                type="agent_completion",
                tool="slack_operator_agent",
                payload={
                    "steps": steps,
                    "durationMs": total_duration,
                    "didPost": did_post,
                    "success": True,
                    "toolCount": len(recent_tools),
                },
                correlation_id=corr,
            )
    except Exception:
        pass
    
    return SlackOperatorResult(
        did_post=did_post,
        text=None,
        meta={"steps": steps, "response_format": "responses_tools", "response_id": prev_id, "scopedRfpId": rfp_id},
    )

