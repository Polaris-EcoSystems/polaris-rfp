"""
Smart file routing service for categorizing and routing files to appropriate Drive folders.
"""

from __future__ import annotations

import re
from typing import Any

from ...observability.logging import get_logger

log = get_logger("drive_file_router")


# Category keywords mapping
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "financial": [
        "budget", "invoice", "financial", "cost", "pricing", "expense",
        "revenue", "payment", "billing", "accounting", "quote", "estimate",
        "p&l", "profit", "loss", "balance", "sheet", "statement",
    ],
    "marketing": [
        "marketing", "brand", "design", "logo", "presentation", "deck",
        "promo", "advertisement", "campaign", "social", "media", "content",
        "graphic", "visual", "creative", "artwork",
    ],
    "rfpfiles": [
        "rfp", "request", "proposal", "solicitation", "tender", "bid",
        "requirements", "specification", "scope", "statement", "of", "work",
    ],
    "drafts": [
        "draft", "version", "v1", "v2", "v3", "revision", "edit", "working",
        "temp", "temporary", "wip", "work", "in", "progress",
    ],
    "questions": [
        "question", "q&a", "qa", "clarification", "inquiry", "query",
        "response", "answer", "follow-up",
    ],
}


def auto_categorize_file(*, file_name: str, content_preview: str | None = None) -> str:
    """
    Automatically categorize a file based on name and optional content preview.
    
    Args:
        file_name: File name
        content_preview: Optional content preview/text (first few lines)
    
    Returns:
        Category key: "financial", "marketing", "rfpfiles", "drafts", "questions", or "rfpfiles" (default)
    """
    if not file_name:
        return "rfpfiles"
    
    file_lower = file_name.lower()
    content_lower = (content_preview or "").lower()
    
    # Score each category
    scores: dict[str, int] = {}
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            # Count occurrences in file name (weighted higher)
            name_matches = len(re.findall(rf"\b{re.escape(keyword)}\b", file_lower))
            score += name_matches * 3  # Weight file name matches more
            
            # Count occurrences in content
            content_matches = len(re.findall(rf"\b{re.escape(keyword)}\b", content_lower))
            score += content_matches
        
        if score > 0:
            scores[category] = score
    
    # Return category with highest score, or default to "rfpfiles"
    if scores:
        best_category = max(scores.items(), key=lambda x: x[1])[0]
        return best_category
    
    return "rfpfiles"


def route_slack_file_to_drive(
    *,
    file_url: str,
    file_name: str,
    channel_id: str | None = None,
    rfp_id: str | None = None,
    user_tags: list[str] | None = None,
    content_preview: str | None = None,
) -> dict[str, Any]:
    """
    Determine the appropriate Drive folder for a Slack file.
    
    Args:
        file_url: Slack file URL
        file_name: File name
        channel_id: Optional Slack channel ID
        rfp_id: Optional RFP ID
        user_tags: Optional user-provided tags/hints (e.g., ["financial", "budget"])
        content_preview: Optional content preview for categorization
    
    Returns:
        Dict with 'ok', 'category', 'folderKey', 'folderId' (if available), 'reason'
    """
    if not file_name:
        return {"ok": False, "error": "file_name is required"}
    
    # Check user tags first (explicit user intent)
    if user_tags:
        user_tags_lower = [tag.lower().strip() for tag in user_tags if tag]
        
        # Map user tags to categories
        for tag in user_tags_lower:
            if any(kw in tag for kw in ["financial", "budget", "invoice", "cost", "money"]):
                return {
                    "ok": True,
                    "category": "financial",
                    "folderKey": "financial",
                    "reason": "user_tag",
                }
            elif any(kw in tag for kw in ["marketing", "brand", "design", "creative"]):
                return {
                    "ok": True,
                    "category": "marketing",
                    "folderKey": "marketing",
                    "reason": "user_tag",
                }
            elif any(kw in tag for kw in ["question", "qa", "clarification"]):
                return {
                    "ok": True,
                    "category": "questions",
                    "folderKey": "questions",
                    "reason": "user_tag",
                }
            elif any(kw in tag for kw in ["draft", "version", "wip", "working"]):
                return {
                    "ok": True,
                    "category": "drafts",
                    "folderKey": "drafts",
                    "reason": "user_tag",
                }
    
    # Auto-categorize based on file name and content
    category = auto_categorize_file(file_name=file_name, content_preview=content_preview)
    
    # Map category to folder key
    folder_key_map: dict[str, str] = {
        "financial": "financial",
        "marketing": "marketing",
        "rfpfiles": "rfpfiles",
        "drafts": "drafts",
        "questions": "questions",
    }
    
    folder_key = folder_key_map.get(category, "rfpfiles")
    
    # Try to get actual folder ID if we have RFP context
    folder_id: str | None = None
    if rfp_id:
        try:
            from .drive_project_setup import get_project_folders
            
            folders_result = get_project_folders(rfp_id=rfp_id)
            if folders_result.get("ok"):
                folders = folders_result.get("folders", {})
                # Map folder key to actual folder ID
                if folder_key == "rfpfiles":
                    folder_id = folders.get("rfpfiles") or folders.get("root")
                else:
                    folder_id = folders.get(folder_key)
        except Exception as e:
            log.warning("failed_to_get_folder_id", rfp_id=rfp_id, folder_key=folder_key, error=str(e))
    
    return {
        "ok": True,
        "category": category,
        "folderKey": folder_key,
        "folderId": folder_id,
        "reason": "auto_categorized",
    }


def extract_user_tags_from_message(message: str) -> list[str]:
    """
    Extract folder/category hints from a user message.
    
    Looks for phrases like "add to financial", "send to marketing", etc.
    
    Args:
        message: User message text
    
    Returns:
        List of extracted tags
    """
    if not message:
        return []
    
    message_lower = message.lower()
    tags: list[str] = []
    
    # Patterns to extract
    patterns = [
        (r"add\s+to\s+(\w+)", "add_to"),
        (r"send\s+to\s+(\w+)", "send_to"),
        (r"put\s+in\s+(\w+)", "put_in"),
        (r"move\s+to\s+(\w+)", "move_to"),
        (r"(\w+)\s+folder", "folder"),
        (r"(\w+)\s+category", "category"),
    ]
    
    for pattern, _ in patterns:
        matches = re.findall(pattern, message_lower)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0] if match else ""
            if match and match not in ["the", "a", "an", "this", "that"]:
                tags.append(match)
    
    # Also check for explicit category mentions
    for category in ["financial", "marketing", "draft", "question", "rfp"]:
        if category in message_lower:
            tags.append(category)
    
    return list(set(tags))  # Deduplicate
