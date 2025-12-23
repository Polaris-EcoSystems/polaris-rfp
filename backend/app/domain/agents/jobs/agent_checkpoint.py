from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .agent_events_repo import append_event, list_recent_events


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_checkpoint(
    *,
    rfp_id: str,
    job_id: str | None = None,
    checkpoint_data: dict[str, Any],
    step: int,
    tool_calls: list[dict[str, Any]] | None = None,
    intermediate_results: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Save a checkpoint for a long-running operation.
    
    Checkpoints are stored as AgentEvents with type="checkpoint" for queryability.
    
    Args:
        rfp_id: RFP ID (or pseudo-ID like "rfp_slack_agent")
        job_id: Job ID if this is part of a job
        checkpoint_data: Core checkpoint state
        step: Current step number
        tool_calls: History of tool calls made so far
        intermediate_results: Intermediate results to preserve
        metadata: Additional metadata
    
    Returns:
        Checkpoint event dict
    """
    checkpoint_payload: dict[str, Any] = {
        "step": step,
        "checkpointData": checkpoint_data,
        "toolCalls": tool_calls if tool_calls else [],
        "intermediateResults": intermediate_results if intermediate_results else {},
        "metadata": metadata if metadata else {},
    }
    
    if job_id:
        checkpoint_payload["jobId"] = job_id
    
    event = append_event(
        rfp_id=rfp_id,
        type="checkpoint",
        payload=checkpoint_payload,
        tool="agent_checkpoint",
        created_by="agent",
        correlation_id=job_id,
    )
    
    return event


def get_latest_checkpoint(
    *,
    rfp_id: str,
    job_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Get the latest checkpoint for an operation.
    
    Args:
        rfp_id: RFP ID (or pseudo-ID)
        job_id: Job ID if filtering by job
    
    Returns:
        Latest checkpoint event dict, or None if not found
    """
    # Get recent events, filter for checkpoints
    events = list_recent_events(rfp_id=rfp_id, limit=100)
    
    checkpoints: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").strip() != "checkpoint":
            continue
        
        # Filter by job_id if provided
        if job_id:
            payload = event.get("payload")
            if isinstance(payload, dict):
                event_job_id = str(payload.get("jobId") or "").strip()
                if event_job_id != job_id:
                    continue
        
        checkpoints.append(event)
    
    if not checkpoints:
        return None
    
    # Sort by created_at descending, return most recent
    checkpoints.sort(
        key=lambda e: str(e.get("createdAt") or ""),
        reverse=True,
    )
    
    return checkpoints[0]


def restore_from_checkpoint(
    *,
    rfp_id: str,
    job_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Restore state from the latest checkpoint.
    
    Args:
        rfp_id: RFP ID (or pseudo-ID)
        job_id: Job ID if filtering by job
    
    Returns:
        Restored state dict with:
        - step: Step number to resume from
        - checkpoint_data: Core state
        - tool_calls: Tool call history
        - intermediate_results: Intermediate results
        - metadata: Additional metadata
        Or None if no checkpoint found
    """
    checkpoint = get_latest_checkpoint(rfp_id=rfp_id, job_id=job_id)
    if not checkpoint:
        return None
    
    payload = checkpoint.get("payload")
    if not isinstance(payload, dict):
        return None
    
    return {
        "step": int(payload.get("step") or 0),
        "checkpoint_data": payload.get("checkpointData") or {},
        "tool_calls": payload.get("toolCalls") or [],
        "intermediate_results": payload.get("intermediateResults") or {},
        "metadata": payload.get("metadata") or {},
        "checkpoint_id": str(checkpoint.get("eventId") or "").strip(),
        "checkpoint_created_at": str(checkpoint.get("createdAt") or "").strip(),
    }


def validate_checkpoint_state(
    *,
    checkpoint_state: dict[str, Any],
    expected_keys: list[str] | None = None,
) -> tuple[bool, str | None]:
    """
    Validate checkpoint state before resuming.
    
    Args:
        checkpoint_state: State dict from restore_from_checkpoint
        expected_keys: List of expected keys in checkpoint_data
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(checkpoint_state, dict):
        return False, "checkpoint_state is not a dict"
    
    checkpoint_data = checkpoint_state.get("checkpoint_data")
    if not isinstance(checkpoint_data, dict):
        return False, "checkpoint_data is missing or invalid"
    
    step = checkpoint_state.get("step")
    if not isinstance(step, int) or step < 0:
        return False, "step is missing or invalid"
    
    # Check expected keys
    if expected_keys:
        for key in expected_keys:
            if key not in checkpoint_data:
                return False, f"missing expected key: {key}"
    
    return True, None


def should_checkpoint(
    *,
    step: int,
    last_checkpoint_step: int = 0,
    checkpoint_interval_steps: int = 10,
    last_checkpoint_time: float | None = None,
    checkpoint_interval_seconds: float = 300.0,  # 5 minutes
) -> bool:
    """
    Determine if we should create a checkpoint now.
    
    Args:
        step: Current step number
        last_checkpoint_step: Step number of last checkpoint
        checkpoint_interval_steps: Checkpoint every N steps
        last_checkpoint_time: Timestamp of last checkpoint (epoch seconds)
        checkpoint_interval_seconds: Checkpoint every N seconds
    
    Returns:
        True if should checkpoint
    """
    # Checkpoint by step interval
    if step - last_checkpoint_step >= checkpoint_interval_steps:
        return True
    
    # Checkpoint by time interval
    if last_checkpoint_time:
        elapsed = time.time() - last_checkpoint_time
        if elapsed >= checkpoint_interval_seconds:
            return True
    
    return False


def cleanup_old_checkpoints(
    *,
    rfp_id: str,
    job_id: str | None = None,
    keep_latest: int = 3,
) -> int:
    """
    Clean up old checkpoints, keeping only the most recent N.
    
    Args:
        rfp_id: RFP ID (or pseudo-ID)
        job_id: Job ID if filtering by job
        keep_latest: Number of latest checkpoints to keep
    
    Returns:
        Number of checkpoints cleaned up
    """
    # Get all checkpoints
    events = list_recent_events(rfp_id=rfp_id, limit=500)
    
    checkpoints: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").strip() != "checkpoint":
            continue
        
        # Filter by job_id if provided
        if job_id:
            payload = event.get("payload")
            if isinstance(payload, dict):
                event_job_id = str(payload.get("jobId") or "").strip()
                if event_job_id != job_id:
                    continue
        
        checkpoints.append(event)
    
    if len(checkpoints) <= keep_latest:
        return 0
    
    # Sort by created_at descending
    checkpoints.sort(
        key=lambda e: str(e.get("createdAt") or ""),
        reverse=True,
    )
    
    # Keep latest N, mark others for deletion
    to_delete = checkpoints[keep_latest:]
    
    # Note: In a full implementation, we would delete these events
    # For now, we just return the count
    # Actual deletion would require a delete_event function
    
    return len(to_delete)


def get_checkpoint_progress(
    *,
    rfp_id: str,
    job_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Get progress information from the latest checkpoint.
    
    Args:
        rfp_id: RFP ID (or pseudo-ID)
        job_id: Job ID if filtering by job
    
    Returns:
        Progress dict with:
        - step: Current step
        - checkpoint_count: Number of checkpoints
        - last_checkpoint_at: Timestamp of last checkpoint
        - estimated_progress: Estimated progress percentage (if available)
    """
    checkpoint = get_latest_checkpoint(rfp_id=rfp_id, job_id=job_id)
    if not checkpoint:
        return None
    
    payload = checkpoint.get("payload")
    if not isinstance(payload, dict):
        return None
    
    step = int(payload.get("step") or 0)
    metadata = payload.get("metadata") or {}
    
    # Get total checkpoints
    events = list_recent_events(rfp_id=rfp_id, limit=500)
    checkpoint_count = sum(
        1 for e in events
        if isinstance(e, dict) and str(e.get("type") or "").strip() == "checkpoint"
    )
    
    return {
        "step": step,
        "checkpoint_count": checkpoint_count,
        "last_checkpoint_at": str(checkpoint.get("createdAt") or "").strip(),
        "estimated_progress": metadata.get("estimatedProgress"),
        "status": metadata.get("status"),
    }
