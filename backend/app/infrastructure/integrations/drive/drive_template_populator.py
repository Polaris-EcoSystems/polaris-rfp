"""
Drive template populator service for auto-creating project templates in Drive folders.
"""

from __future__ import annotations

from typing import Any

from ....observability.logging import get_logger
from ...repositories.rfp.rfps_repo import get_rfp_by_id
from ...tools.categories.google.google_drive import create_google_doc

log = get_logger("drive_template_populator")


def populate_project_templates(
    *,
    rfp_id: str,
    templates_folder_id: str | None = None,
    financial_folder_id: str | None = None,
) -> dict[str, Any]:
    """
    Create standard templates in Drive folders for an RFP project.
    
    Creates:
    - Budget template (Google Sheets) in Financial folder
    - Invoice template (Google Doc) in Financial folder
    - Project timeline (Google Sheets) in Templates folder
    - Questions tracker (Google Sheets) in Questions folder
    
    Args:
        rfp_id: RFP ID
        templates_folder_id: Optional Templates folder ID (will use if provided)
        financial_folder_id: Optional Financial folder ID (will use if provided)
    
    Returns:
        Dict with 'ok', 'templates' (map of template type to file ID/link)
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        return {"ok": False, "error": "rfp_id is required"}
    
    try:
        # Get RFP details
        rfp = get_rfp_by_id(rid) or {}
        rfp_title = str(rfp.get("title") or rfp.get("rfpTitle") or "RFP").strip()
        client_name = str(rfp.get("clientName") or "Client").strip()
        
        # Get project folders if not provided
        if not templates_folder_id or not financial_folder_id:
            from .drive_project_setup import get_project_folders
            
            folders_result = get_project_folders(rfp_id=rid)
            if folders_result.get("ok"):
                folders = folders_result.get("folders", {})
                if not templates_folder_id:
                    templates_folder_id = folders.get("templates")
                if not financial_folder_id:
                    financial_folder_id = folders.get("financial")
        
        templates: dict[str, Any] = {}
        errors: list[str] = []
        
        # Create Budget Template (Google Sheets - we'll create as a Doc with table structure)
        if financial_folder_id:
            budget_content = f"""Budget Template - {rfp_title}

Client: {client_name}
RFP ID: {rid}

Budget Items:
-------------
| Item | Description | Quantity | Unit Cost | Total |
|------|-------------|----------|-----------|-------|
|      |             |          |           |       |

Notes:
------


Total Budget: $0.00
"""
            budget_result = create_google_doc(
                title=f"Budget - {rfp_title}",
                content=budget_content,
                folder_id=financial_folder_id,
            )
            if budget_result.get("ok"):
                templates["budget"] = {
                    "fileId": budget_result.get("documentId"),
                    "webViewLink": budget_result.get("webViewLink"),
                    "title": f"Budget - {rfp_title}",
                }
            else:
                errors.append(f"Budget template: {budget_result.get('error')}")
            
            # Create Invoice Template
            invoice_content = f"""Invoice Template - {rfp_title}

Client: {client_name}
RFP ID: {rid}
Invoice Date: [DATE]
Invoice Number: [INVOICE_NUMBER]

Bill To:
--------
[CLIENT_ADDRESS]

Services/Items:
---------------
| Description | Quantity | Rate | Amount |
|-------------|----------|------|--------|
|             |          |      |        |

Subtotal: $0.00
Tax: $0.00
Total: $0.00

Payment Terms: [TERMS]
Due Date: [DUE_DATE]
"""
            invoice_result = create_google_doc(
                title=f"Invoice Template - {rfp_title}",
                content=invoice_content,
                folder_id=financial_folder_id,
            )
            if invoice_result.get("ok"):
                templates["invoice"] = {
                    "fileId": invoice_result.get("documentId"),
                    "webViewLink": invoice_result.get("webViewLink"),
                    "title": f"Invoice Template - {rfp_title}",
                }
            else:
                errors.append(f"Invoice template: {invoice_result.get('error')}")
        
        # Create Project Timeline (in Templates folder)
        if templates_folder_id:
            timeline_content = f"""Project Timeline - {rfp_title}

Client: {client_name}
RFP ID: {rid}

Timeline:
---------
| Phase | Task | Start Date | End Date | Status | Owner |
|-------|------|------------|----------|--------|-------|
|       |      |            |          |        |       |

Milestones:
-----------
| Milestone | Target Date | Status |
|-----------|-------------|--------|
|           |             |        |

Notes:
------


"""
            timeline_result = create_google_doc(
                title=f"Project Timeline - {rfp_title}",
                content=timeline_content,
                folder_id=templates_folder_id,
            )
            if timeline_result.get("ok"):
                templates["timeline"] = {
                    "fileId": timeline_result.get("documentId"),
                    "webViewLink": timeline_result.get("webViewLink"),
                    "title": f"Project Timeline - {rfp_title}",
                }
            else:
                errors.append(f"Timeline template: {timeline_result.get('error')}")
        
        # Create Questions Tracker (in Questions folder - need to get that folder)
        questions_folder_id = None
        if not questions_folder_id:
            from .drive_project_setup import get_project_folders
            
            folders_result = get_project_folders(rfp_id=rid)
            if folders_result.get("ok"):
                folders = folders_result.get("folders", {})
                questions_folder_id = folders.get("questions")
        
        if questions_folder_id:
            questions_content = f"""Questions Tracker - {rfp_title}

Client: {client_name}
RFP ID: {rid}

Questions:
----------
| # | Question | Category | Asked Date | Response Date | Status | Notes |
|---|----------|----------|------------|---------------|--------|-------|
|   |          |          |            |               |        |       |

Key Questions:
--------------
1. 
2. 
3. 

Follow-up Items:
----------------
- 
- 
- 
"""
            questions_result = create_google_doc(
                title=f"Questions Tracker - {rfp_title}",
                content=questions_content,
                folder_id=questions_folder_id,
            )
            if questions_result.get("ok"):
                templates["questions"] = {
                    "fileId": questions_result.get("documentId"),
                    "webViewLink": questions_result.get("webViewLink"),
                    "title": f"Questions Tracker - {rfp_title}",
                }
            else:
                errors.append(f"Questions tracker: {questions_result.get('error')}")
        
        result: dict[str, Any] = {
            "ok": True,
            "templates": templates,
            "rfpId": rid,
        }
        
        if errors:
            result["warnings"] = errors
            result["partial"] = True
        
        return result
    
    except Exception as e:
        log.error("populate_project_templates_failed", rfp_id=rid, error=str(e))
        return {"ok": False, "error": str(e)}


def create_budget_template(
    *,
    rfp_id: str,
    folder_id: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Create a budget template document."""
    rid = str(rfp_id or "").strip()
    if not rid:
        return {"ok": False, "error": "rfp_id is required"}
    
    rfp = get_rfp_by_id(rid) or {}
    rfp_title = str(rfp.get("title") or rfp.get("rfpTitle") or "RFP").strip()
    client_name = str(rfp.get("clientName") or "Client").strip()
    
    template_title = title or f"Budget - {rfp_title}"
    content = f"""Budget Template - {rfp_title}

Client: {client_name}
RFP ID: {rid}

Budget Items:
-------------
| Item | Description | Quantity | Unit Cost | Total |
|------|-------------|----------|-----------|-------|
|      |             |          |           |       |

Notes:
------


Total Budget: $0.00
"""
    
    result = create_google_doc(
        title=template_title,
        content=content,
        folder_id=folder_id,
    )
    
    return result
