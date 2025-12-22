"""
Google Drive integration router.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..services.agent_infrastructure_config import get_infrastructure_config

router = APIRouter(tags=["integrations", "googledrive"])


@router.get("/status")
def status(request: Request):
    """
    Get Google Drive integration status.
    
    Returns whether Google Drive credentials are configured and valid.
    """
    try:
        config = get_infrastructure_config()
        
        # Check if credentials are configured (service account or API key)
        configured = (
            config.google_drive_service_account_configured
            or config.google_drive_api_key_configured
        )
        
        # Determine if initialized (credentials are valid)
        initialized = config.google_drive_credentials_valid
        
        message = None
        if not configured:
            message = "Google Drive credentials not configured"
        elif not initialized:
            message = config.google_drive_credentials_error or "Google Drive credentials invalid"
        else:
            if config.google_drive_service_account_configured:
                message = "Service account credentials configured"
            elif config.google_drive_api_key_configured:
                message = "API key credentials configured"
        
        return {
            "initialized": initialized,
            "configured": configured,
            "message": message,
            "serviceAccountConfigured": config.google_drive_service_account_configured,
            "apiKeyConfigured": config.google_drive_api_key_configured,
        }
    except Exception as e:
        return {
            "initialized": False,
            "configured": False,
            "message": f"Failed to check status: {str(e)}",
            "serviceAccountConfigured": False,
            "apiKeyConfigured": False,
        }
