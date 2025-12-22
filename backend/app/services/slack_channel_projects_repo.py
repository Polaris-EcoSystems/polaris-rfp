from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..db.dynamodb.table import get_main_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def channel_project_key(*, channel_id: str) -> dict[str, str]:
    ch = str(channel_id or "").strip()
    if not ch:
        raise ValueError("channel_id is required")
    return {"pk": f"SLACKCHANNEL#{ch}", "sk": "PROJECT"}


def normalize(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = dict(item)
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    out["_id"] = out.get("channelId")
    return out


def get_channel_project(*, channel_id: str) -> dict[str, Any] | None:
    """Get the project mapping for a Slack channel."""
    it = get_main_table().get_item(key=channel_project_key(channel_id=channel_id))
    return normalize(it)


def set_channel_project(
    *,
    channel_id: str,
    rfp_id: str,
    drive_folder_id: str | None = None,
    project_type: str | None = None,
    set_by_slack_user_id: str | None = None,
) -> dict[str, Any]:
    """
    Set or update the project mapping for a Slack channel.
    
    Args:
        channel_id: Slack channel ID
        rfp_id: RFP ID to map to this channel
        drive_folder_id: Optional root Drive folder ID
        project_type: Optional project type/category
        set_by_slack_user_id: Optional Slack user ID who set this mapping
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    
    ch = str(channel_id or "").strip()
    if not ch:
        raise ValueError("channel_id is required")
    
    now = _now_iso()
    item: dict[str, Any] = {
        **channel_project_key(channel_id=ch),
        "entityType": "SlackChannelProject",
        "channelId": ch,
        "rfpId": rid,
        "driveFolderId": str(drive_folder_id).strip() if drive_folder_id else None,
        "projectType": str(project_type).strip() if project_type else None,
        "setBySlackUserId": str(set_by_slack_user_id).strip() if set_by_slack_user_id else None,
        "createdAt": now,
        "updatedAt": now,
        "gsi1pk": "TYPE#SLACK_CHANNEL_PROJECT",
        "gsi1sk": f"{now}#{rid}",
    }
    item = {k: v for k, v in item.items() if v is not None}
    get_main_table().put_item(item=item)
    return normalize(item) or {}


def get_channel_by_rfp(*, rfp_id: str) -> dict[str, Any] | None:
    """Get the channel mapping for an RFP (reverse lookup)."""
    rid = str(rfp_id or "").strip()
    if not rid:
        return None
    
    # Query GSI1 for the RFP
    table = get_main_table()
    results = table.query(
        index_name="GSI1",
        key_condition_expression="gsi1pk = :pk AND begins_with(gsi1sk, :sk)",
        expression_attribute_values={
            ":pk": "TYPE#SLACK_CHANNEL_PROJECT",
            ":sk": f"{_now_iso()[:10]}#{rid}",  # Match by date prefix and RFP ID
        },
        limit=1,
    )
    
    # Also try without date prefix for broader search
    if not results:
        results = table.query(
            index_name="GSI1",
            key_condition_expression="gsi1pk = :pk",
            filter_expression="rfpId = :rid",
            expression_attribute_values={
                ":pk": "TYPE#SLACK_CHANNEL_PROJECT",
                ":rid": rid,
            },
            limit=1,
        )
    
    if results:
        return normalize(results[0])
    return None
