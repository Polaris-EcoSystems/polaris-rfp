"""
RFP workflow orchestrator for automated RFP onboarding workflow.
"""

from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger
from ..infrastructure.integrations.drive.drive_project_setup import setup_project_folders
from ..infrastructure.integrations.slack.slack_web import download_slack_file
from .rfp_analyzer import analyze_rfp
from ..repositories.rfp.rfps_repo import create_rfp_from_analysis, get_rfp_by_id
from ..tools.categories.google.google_drive import upload_file_to_drive, create_google_doc
from ..repositories.rfp.opportunity_state_repo import patch_state, ensure_state_exists

log = get_logger("rfp_workflow_orchestrator")


def run_rfp_onboarding_workflow(
    *,
    rfp_url: str | None = None,
    rfp_id: str | None = None,
    file_url: str | None = None,
    file_name: str | None = None,
    channel_id: str | None = None,
    user_sub: str | None = None,
) -> dict[str, Any]:
    """
    Run the complete RFP onboarding workflow:
    1. Download RFP (if URL/file provided)
    2. Analyze and create RFP (if not exists)
    3. Create Drive folder structure
    4. Upload RFP files to Drive
    5. Link files to OpportunityState
    6. Update dates in opp tracker
    7. Create initial questions document
    8. Create initial content draft
    
    Args:
        rfp_url: URL to download RFP from
        rfp_id: Existing RFP ID (skip download/analysis)
        file_url: Slack file URL (alternative to rfp_url)
        file_name: File name (if file_url provided)
        channel_id: Slack channel ID for context
        user_sub: User sub for attribution
    
    Returns:
        Dict with 'ok', 'rfpId', 'steps' (completed steps), 'errors'
    """
    steps_completed: list[str] = []
    errors: list[str] = []
    result_rfp_id: str | None = None
    
    try:
        # Step 1: Download and analyze RFP (if needed)
        if rfp_id:
            rfp = get_rfp_by_id(rfp_id) or {}
            if not rfp:
                return {"ok": False, "error": f"RFP {rfp_id} not found"}
            result_rfp_id = rfp_id
            steps_completed.append("rfp_exists")
        else:
            # Download RFP
            pdf_data = None
            file_name_final = file_name or "RFP.pdf"
            
            if file_url:
                try:
                    pdf_data = download_slack_file(url=file_url, max_bytes=60 * 1024 * 1024)
                    steps_completed.append("downloaded_from_slack")
                except Exception as e:
                    errors.append(f"Download from Slack failed: {str(e)}")
                    return {"ok": False, "error": f"Download failed: {str(e)}", "steps": steps_completed}
            elif rfp_url:
                try:
                    import requests
                    response = requests.get(rfp_url, timeout=30, allow_redirects=True)
                    response.raise_for_status()
                    pdf_data = response.content
                    steps_completed.append("downloaded_from_url")
                except Exception as e:
                    errors.append(f"Download from URL failed: {str(e)}")
                    return {"ok": False, "error": f"Download failed: {str(e)}", "steps": steps_completed}
            else:
                return {"ok": False, "error": "rfp_url, file_url, or rfp_id required"}
            
            # Analyze and create RFP
            try:
                analysis = analyze_rfp(pdf_data, file_name_final)
                saved = create_rfp_from_analysis(
                    analysis=analysis,
                    source_file_name=file_name_final,
                    source_file_size=len(pdf_data),
                    source_pdf_data=pdf_data,
                )
                result_rfp_id = str(saved.get("_id") or saved.get("rfpId") or "").strip()
                if not result_rfp_id:
                    return {"ok": False, "error": "RFP creation failed - no ID returned", "steps": steps_completed}
                steps_completed.append("rfp_created")
            except Exception as e:
                errors.append(f"RFP analysis/creation failed: {str(e)}")
                return {"ok": False, "error": f"RFP creation failed: {str(e)}", "steps": steps_completed}
        
        if not result_rfp_id:
            return {"ok": False, "error": "No RFP ID available", "steps": steps_completed}
        
        # Step 2: Create Drive folder structure
        try:
            folder_result = setup_project_folders(
                rfp_id=result_rfp_id,
                channel_id=channel_id,
            )
            if folder_result.get("ok"):
                folders = folder_result.get("folders", {})
                root_folder_id = folder_result.get("rootFolderId")
                steps_completed.append("folders_created")
            else:
                errors.append(f"Folder creation failed: {folder_result.get('error')}")
                folders = {}
                root_folder_id = None
        except Exception as e:
            errors.append(f"Folder creation error: {str(e)}")
            folders = {}
            root_folder_id = None
        
        # Step 3: Upload RFP file to Drive (if we have PDF data)
        drive_file_id = None
        if pdf_data and root_folder_id:
            try:
                rfp_files_folder = folders.get("rfpfiles") or root_folder_id
                upload_result = upload_file_to_drive(
                    name=file_name_final if 'file_name_final' in locals() else "RFP.pdf",
                    content=pdf_data,
                    mime_type="application/pdf",
                    folder_id=rfp_files_folder,
                )
                if upload_result.get("ok"):
                    drive_file_id = upload_result.get("fileId")
                    steps_completed.append("rfp_uploaded_to_drive")
                else:
                    errors.append(f"RFP upload failed: {upload_result.get('error')}")
            except Exception as e:
                errors.append(f"RFP upload error: {str(e)}")
        
        # Step 4: Link files to OpportunityState and update dates
        try:
            ensure_state_exists(rfp_id=result_rfp_id, created_by_user_sub=user_sub)
            
            # Update driveFolders
            if folders:
                patch_state(
                    rfp_id=result_rfp_id,
                    patch={"driveFolders": folders},
                )
            
            # Add file to driveFiles if uploaded
            if drive_file_id:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                patch_state(
                    rfp_id=result_rfp_id,
                    patch={
                        "driveFiles_append": [{
                            "fileId": drive_file_id,
                            "fileName": file_name_final if 'file_name_final' in locals() else "RFP.pdf",
                            "folderId": folders.get("rfpfiles") or root_folder_id,
                            "category": "rfpfiles",
                            "uploadedAt": now,
                            "uploadedBy": user_sub,
                        }],
                    },
                )
            
            # Update dates from RFP
            rfp = get_rfp_by_id(result_rfp_id) or {}
            due_dates = {}
            for key in ("submissionDeadline", "questionsDeadline", "bidMeetingDate", "bidRegistrationDate", "projectDeadline"):
                value = rfp.get(key)
                if value:
                    due_dates[key] = value
            
            if due_dates:
                patch_state(
                    rfp_id=result_rfp_id,
                    patch={"dueDates": due_dates},
                )
            
            steps_completed.append("state_updated")
        except Exception as e:
            errors.append(f"State update error: {str(e)}")
        
        # Step 5: Create initial questions document
        try:
            questions_folder = folders.get("questions")
            if questions_folder:
                rfp = get_rfp_by_id(result_rfp_id) or {}
                rfp_title = str(rfp.get("title") or rfp.get("rfpTitle") or "RFP").strip()
                client_name = str(rfp.get("clientName") or "Client").strip()
                
                questions_content = f"""Initial Questions - {rfp_title}

Client: {client_name}
RFP ID: {result_rfp_id}

Key Questions to Clarify:
--------------------------
1. 
2. 
3. 
4. 
5. 

Technical Questions:
--------------------
- 
- 
- 

Business/Process Questions:
----------------------------
- 
- 

Timeline Questions:
-------------------
- 
- 

Budget/Scope Questions:
------------------------
- 
- 
"""
                questions_result = create_google_doc(
                    title=f"Initial Questions - {rfp_title}",
                    content=questions_content,
                    folder_id=questions_folder,
                )
                if questions_result.get("ok"):
                    steps_completed.append("questions_created")
                else:
                    errors.append(f"Questions creation failed: {questions_result.get('error')}")
        except Exception as e:
            errors.append(f"Questions creation error: {str(e)}")
        
        # Step 6: Create initial content draft
        try:
            drafts_folder = folders.get("drafts")
            if drafts_folder:
                rfp = get_rfp_by_id(result_rfp_id) or {}
                rfp_title = str(rfp.get("title") or rfp.get("rfpTitle") or "RFP").strip()
                client_name = str(rfp.get("clientName") or "Client").strip()
                
                draft_content = f"""Proposal Draft - {rfp_title}

Client: {client_name}
RFP ID: {result_rfp_id}

Executive Summary:
------------------


Approach:
---------


Key Personnel:
--------------


Timeline:
---------


Budget:
-------


Next Steps:
----------
- Review RFP requirements
- Develop detailed approach
- Prepare budget breakdown
- Identify key team members
"""
                draft_result = create_google_doc(
                    title=f"Proposal Draft - {rfp_title}",
                    content=draft_content,
                    folder_id=drafts_folder,
                )
                if draft_result.get("ok"):
                    steps_completed.append("draft_created")
                else:
                    errors.append(f"Draft creation failed: {draft_result.get('error')}")
        except Exception as e:
            errors.append(f"Draft creation error: {str(e)}")
        
        return {
            "ok": True,
            "rfpId": result_rfp_id,
            "steps": steps_completed,
            "errors": errors if errors else None,
            "folders": folders,
        }
    
    except Exception as e:
        log.error("rfp_onboarding_workflow_failed", error=str(e), rfp_id=result_rfp_id)
        return {
            "ok": False,
            "error": str(e),
            "steps": steps_completed,
            "errors": errors + [str(e)],
        }
