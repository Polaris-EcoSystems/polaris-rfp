"""
Drive project setup service for automatic folder creation and management.
"""

from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger
from ..repositories.rfp.rfps_repo import get_rfp_by_id
from ..tools.categories.google.google_drive import create_google_folder
from .slack_channel_projects_repo import get_channel_project, set_channel_project

log = get_logger("drive_project_setup")


# Standard folder structure for RFP projects
STANDARD_FOLDERS = [
    "RFP Files",
    "Financial",
    "Marketing",
    "Drafts",
    "Questions",
    "Templates",
]


def setup_project_folders(
    *,
    rfp_id: str,
    channel_id: str | None = None,
    parent_folder_id: str | None = None,
) -> dict[str, Any]:
    """
    Create Drive folder structure for an RFP project.
    
    Creates:
    - Root folder: "{RFP Title} - {Client Name}"
    - Subfolders: RFP Files, Financial, Marketing, Drafts, Questions, Templates
    
    If folders already exist (in OpportunityState), returns existing folder IDs.
    
    Args:
        rfp_id: RFP ID
        channel_id: Optional Slack channel ID to link
        parent_folder_id: Optional parent folder ID (if creating in a parent folder)
    
    Returns:
        Dict with 'ok', 'rootFolderId', 'folders' (map of folder type to folder ID)
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        return {"ok": False, "error": "rfp_id is required"}
    
    try:
        # Check if folders already exist in OpportunityState
        existing_folders_result = get_project_folders(rfp_id=rid)
        if existing_folders_result.get("ok"):
            folders = existing_folders_result.get("folders", {})
            root_folder_id = folders.get("root")
            if root_folder_id:
                log.info("using_existing_drive_folders", rfp_id=rid, root_folder_id=root_folder_id)
                return {
                    "ok": True,
                    "rootFolderId": root_folder_id,
                    "folders": folders,
                    "existing": True,
                }
        
        # Get RFP details for folder naming
        rfp = get_rfp_by_id(rid) or {}
        rfp_title = str(rfp.get("title") or rfp.get("rfpTitle") or "RFP").strip()
        client_name = str(rfp.get("clientName") or "Unknown Client").strip()
        
        # Create root folder name
        root_folder_name = f"{rfp_title} - {client_name}"
        # Sanitize folder name (remove invalid characters)
        root_folder_name = "".join(c for c in root_folder_name if c.isalnum() or c in (" ", "-", "_", "."))[:100]
        if not root_folder_name.strip():
            root_folder_name = f"RFP {rid}"
        
        # Create root folder
        root_result = create_google_folder(
            name=root_folder_name,
            parent_folder_id=parent_folder_id,
        )
        
        if not root_result.get("ok"):
            return {"ok": False, "error": f"Failed to create root folder: {root_result.get('error')}"}
        
        root_folder_id = root_result.get("folderId")
        if not root_folder_id:
            return {"ok": False, "error": "Root folder created but no folder ID returned"}
        
        # Create subfolders
        folders: dict[str, str] = {"root": root_folder_id}
        errors: list[str] = []
        
        for folder_name in STANDARD_FOLDERS:
            folder_result = create_google_folder(
                name=folder_name,
                parent_folder_id=root_folder_id,
            )
            
            if folder_result.get("ok"):
                folder_id = folder_result.get("folderId")
                if folder_id:
                    # Map folder name to key
                    folder_key = folder_name.lower().replace(" ", "")
                    folders[folder_key] = folder_id
                else:
                    errors.append(f"Folder '{folder_name}' created but no ID returned")
            else:
                error_msg = folder_result.get("error", "unknown error")
                errors.append(f"Failed to create folder '{folder_name}': {error_msg}")
        
        # Update channel mapping if channel_id provided
        if channel_id:
            try:
                set_channel_project(
                    channel_id=channel_id,
                    rfp_id=rid,
                    drive_folder_id=root_folder_id,
                )
            except Exception as e:
                log.warning("failed_to_update_channel_mapping", channel_id=channel_id, rfp_id=rid, error=str(e))
        
        result: dict[str, Any] = {
            "ok": True,
            "rootFolderId": root_folder_id,
            "rootFolderName": root_folder_name,
            "folders": folders,
        }
        
        if errors:
            result["warnings"] = errors
            result["partial"] = True
        
        return result
    
    except Exception as e:
        log.error("setup_project_folders_failed", rfp_id=rid, error=str(e))
        return {"ok": False, "error": str(e)}


def ensure_channel_drive_folder(*, channel_id: str, rfp_id: str | None = None) -> dict[str, Any]:
    """
    Ensure a Drive folder exists for a Slack channel.
    
    If channel already has a folder, returns it.
    If rfp_id provided and channel doesn't have folder, creates one.
    If no rfp_id, attempts to find RFP from channel name or recent activity.
    
    Args:
        channel_id: Slack channel ID
        rfp_id: Optional RFP ID to create folder for
    
    Returns:
        Dict with 'ok', 'folderId', 'rfpId', 'folders'
    """
    ch = str(channel_id or "").strip()
    if not ch:
        return {"ok": False, "error": "channel_id is required"}
    
    try:
        # Check if channel already has a project mapping
        existing = get_channel_project(channel_id=ch)
        
        if existing:
            existing_folder_id = existing.get("driveFolderId")
            existing_rfp_id = existing.get("rfpId")
            
            if existing_folder_id:
                # Return existing folder
                return {
                    "ok": True,
                    "folderId": existing_folder_id,
                    "rfpId": existing_rfp_id,
                    "existing": True,
                }
        
        # No existing folder - create one if we have an RFP
        if rfp_id:
            setup_result = setup_project_folders(rfp_id=rfp_id, channel_id=ch)
            if setup_result.get("ok"):
                return {
                    "ok": True,
                    "folderId": setup_result.get("rootFolderId"),
                    "rfpId": rfp_id,
                    "folders": setup_result.get("folders"),
                    "existing": False,
                }
            else:
                return {"ok": False, "error": f"Failed to create folder: {setup_result.get('error')}"}
        
        # No RFP provided and no existing mapping
        return {
            "ok": False,
            "error": "No RFP ID provided and channel has no existing folder mapping",
            "needs_rfp": True,
        }
    
    except Exception as e:
        log.error("ensure_channel_drive_folder_failed", channel_id=ch, error=str(e))
        return {"ok": False, "error": str(e)}


def get_project_folders(*, rfp_id: str) -> dict[str, Any]:
    """
    Get folder structure for an RFP project.
    
    Looks up folders from OpportunityState or channel mapping.
    
    Args:
        rfp_id: RFP ID
    
    Returns:
        Dict with 'ok', 'folders' (map of folder type to folder ID)
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        return {"ok": False, "error": "rfp_id is required"}
    
    try:
        # Try to get from OpportunityState
        from ..repositories.rfp.opportunity_state_repo import get_state
        
        state = get_state(rfp_id=rid)
        if state and isinstance(state, dict):
            state_data = state.get("state")
            if isinstance(state_data, dict):
                drive_folders = state_data.get("driveFolders")
                if isinstance(drive_folders, dict) and drive_folders:
                    return {
                        "ok": True,
                        "folders": drive_folders,
                        "source": "opportunity_state",
                    }
        
        # Fallback: try channel mapping
        from .slack_channel_projects_repo import get_channel_by_rfp
        
        channel_mapping = get_channel_by_rfp(rfp_id=rid)
        if channel_mapping:
            folder_id = channel_mapping.get("driveFolderId")
            if folder_id:
                return {
                    "ok": True,
                    "folders": {"root": folder_id},
                    "source": "channel_mapping",
                }
        
        return {"ok": False, "error": "No folder structure found for this RFP"}
    
    except Exception as e:
        log.error("get_project_folders_failed", rfp_id=rid, error=str(e))
        return {"ok": False, "error": str(e)}
