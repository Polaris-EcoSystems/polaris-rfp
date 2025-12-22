"""
Unified integrations router for status and health checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..observability.logging import get_logger
from ..services.agent_infrastructure_config import get_infrastructure_config
from ..services import canva_repo

log = get_logger("integrations_router")

router = APIRouter(tags=["integrations"])


def _user_id_from_request(request: Request) -> str:
    """Extract user ID from request."""
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(status_code=401, detail="Unauthorized")
    sub = getattr(u, "sub", None)
    if sub:
        return str(sub)
    user_id = getattr(u, "user_id", None)
    if user_id:
        return str(user_id)
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/status")
def get_integrations_status(request: Request) -> dict[str, Any]:
    """
    Get status for all integrations.
    
    Returns health status, authentication status, and recent activities for each integration.
    """
    user_id = _user_id_from_request(request)
    
    integrations: dict[str, Any] = {}
    
    # Google Drive Status
    try:
        config = get_infrastructure_config()
        
        overall_error = config.google_drive_credentials_error
        
        # Check service account
        service_account_configured = config.google_drive_service_account_configured
        service_account_valid = False
        service_account_error = None
        
        if service_account_configured:
            # If service account is configured and credentials are valid, service account is working
            # If only service account is configured, it must be what's valid
            if config.google_drive_credentials_valid:
                service_account_valid = True
            else:
                service_account_valid = False
                service_account_error = overall_error or "Service account credentials invalid"
        
        # Check API key
        api_key_configured = config.google_drive_api_key_configured
        api_key_valid = False
        api_key_error = None
        
        if api_key_configured:
            # API key is valid if credentials are valid and service account is not configured
            # OR if credentials are valid and service account is not valid
            if config.google_drive_credentials_valid:
                if not service_account_configured:
                    api_key_valid = True
                elif not service_account_valid:
                    api_key_valid = True  # API key is the fallback
                else:
                    api_key_valid = False  # Service account is working, API key not needed
            else:
                api_key_valid = False
                api_key_error = overall_error or "API key credentials invalid"
        
        # Determine overall status
        any_configured = service_account_configured or api_key_configured
        any_valid = service_account_valid or api_key_valid
        
        if not any_configured:
            status = "red"
            status_message = "Not configured"
        elif not any_valid:
            status = "red"
            status_message = overall_error or "Credentials invalid"
        elif service_account_valid:
            status = "green"
            status_message = "Service account credentials working"
        elif api_key_valid:
            status = "yellow"
            status_message = "API key working (service account preferred)"
        else:
            status = "red"
            status_message = overall_error or "Unknown error"
        
        integrations["googleDrive"] = {
            "status": status,
            "statusMessage": status_message,
            "serviceAccount": {
                "configured": service_account_configured,
                "valid": service_account_valid,
                "error": service_account_error,
            },
            "apiKey": {
                "configured": api_key_configured,
                "valid": api_key_valid,
                "error": api_key_error,
            },
            "overallError": overall_error,
        }
    except Exception as e:
        log.exception("failed_to_check_google_drive_status", error=str(e))
        integrations["googleDrive"] = {
            "status": "red",
            "statusMessage": f"Error checking status: {str(e)}",
            "serviceAccount": {"configured": False, "valid": False, "error": str(e)},
            "apiKey": {"configured": False, "valid": False, "error": None},
            "overallError": str(e),
        }
    
    # Canva Status
    try:
        conn = canva_repo.get_connection_for_user(user_id)
        
        if not conn:
            integrations["canva"] = {
                "status": "red",
                "statusMessage": "Not connected",
                "connected": False,
                "error": None,
            }
        else:
            # Try to validate the connection by checking if we can get a valid token
            try:
                from ..services.canva_client import get_valid_access_token_for_user
                access_token, updated_conn = get_valid_access_token_for_user(user_id)
                
                if access_token:
                    status = "green"
                    status_message = "Connected and working"
                    error = None
                else:
                    status = "yellow"
                    status_message = "Connected but token invalid"
                    error = "Unable to get valid access token"
            except Exception as e:
                status = "yellow"
                status_message = f"Connected but error: {str(e)}"
                error = str(e)
            
            safe_conn = dict(conn)
            safe_conn.pop("accessTokenEnc", None)
            safe_conn.pop("refreshTokenEnc", None)
            
            integrations["canva"] = {
                "status": status,
                "statusMessage": status_message,
                "connected": True,
                "connection": safe_conn,
                "error": error,
            }
    except Exception as e:
        log.exception("failed_to_check_canva_status", error=str(e))
        integrations["canva"] = {
            "status": "red",
            "statusMessage": f"Error checking status: {str(e)}",
            "connected": False,
            "error": str(e),
        }
    
    return {
        "ok": True,
        "integrations": integrations,
    }


@router.get("/activities")
def get_recent_activities(request: Request, limit: int = 5) -> dict[str, Any]:
    """
    Get recent activities for integrations.
    
    Returns recent events/activities related to Canva and Google Drive.
    """
    _ = _user_id_from_request(request)  # Ensure user is authenticated
    lim = max(1, min(50, int(limit or 5)))
    
    since = datetime.now(timezone.utc) - timedelta(days=7)
    since_iso = since.isoformat().replace("+00:00", "Z")
    
    activities: list[dict[str, Any]] = []
    
    try:
        from ..services.agent_events_repo import list_recent_events_global
        
        events = list_recent_events_global(since_iso=since_iso, limit=lim * 10)  # Get more for filtering
        
        # Filter for integration-related events
        for event in events[:lim * 3]:  # Look at more events
            if not isinstance(event, dict):
                continue
            
            event_type = str(event.get("type") or "").lower()
            tool = str(event.get("tool") or "").lower()
            payload = event.get("payload") or {}
            
            # Check if event is related to integrations
            is_integration_event = False
            integration_name = None
            
            if "canva" in event_type or "canva" in tool:
                is_integration_event = True
                integration_name = "canva"
            elif "drive" in event_type or "drive" in tool or "googledrive" in event_type or "googledrive" in tool:
                is_integration_event = True
                integration_name = "googleDrive"
            
            # Check payload for integration keywords
            if not is_integration_event and isinstance(payload, dict):
                payload_str = str(payload).lower()
                if "canva" in payload_str:
                    is_integration_event = True
                    integration_name = "canva"
                elif any(kw in payload_str for kw in ["drive", "googledrive"]):
                    is_integration_event = True
                    integration_name = "googleDrive"
            
            if is_integration_event:
                activities.append({
                    "integration": integration_name,
                    "type": event.get("type", "activity"),
                    "tool": event.get("tool"),
                    "createdAt": event.get("createdAt"),
                    "payload": payload,
                })
                
                if len(activities) >= lim:
                    break
        
        # Sort by createdAt descending
        activities.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
        activities = activities[:lim]
        
    except Exception as e:
        log.warning("failed_to_fetch_integration_activities", error=str(e))
    
    return {
        "ok": True,
        "activities": activities,
        "count": len(activities),
    }
