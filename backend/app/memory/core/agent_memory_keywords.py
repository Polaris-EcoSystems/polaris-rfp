from __future__ import annotations

import re
from typing import Any


def extract_keywords(content: str, max_keywords: int = 50) -> list[str]:
    """
    Extract keywords from memory content using simple NLP techniques.
    
    This is a basic implementation - in production, you might want to use
    more sophisticated NLP libraries like spaCy or NLTK.
    
    Args:
        content: Text content to extract keywords from
        max_keywords: Maximum number of keywords to return
    
    Returns:
        List of lowercase keywords
    """
    if not content or not isinstance(content, str):
        return []
    
    # Common stopwords to filter out
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
        "been", "have", "has", "had", "do", "does", "did", "will", "would",
        "should", "could", "may", "might", "must", "can", "this", "that",
        "these", "those", "i", "you", "he", "she", "it", "we", "they",
        "me", "him", "her", "us", "them", "what", "which", "who", "whom",
        "whose", "where", "when", "why", "how", "all", "each", "every",
        "both", "few", "more", "most", "other", "some", "such", "no",
        "nor", "not", "only", "own", "same", "so", "than", "too", "very",
        "just", "now", "then", "here", "there", "about", "above", "below",
        "up", "down", "out", "off", "over", "under", "again", "further",
    }
    
    # Extract words (alphanumeric sequences, at least 3 characters)
    words = re.findall(r'\b[a-zA-Z0-9]{3,}\b', content.lower())
    
    # Filter stopwords and common words
    keywords = [w for w in words if w not in stopwords and len(w) >= 3]
    
    # Count frequency
    word_counts: dict[str, int] = {}
    for word in keywords:
        word_counts[word] = word_counts.get(word, 0) + 1
    
    # Sort by frequency (descending), then alphabetically
    sorted_keywords = sorted(word_counts.items(), key=lambda x: (-x[1], x[0]))
    
    # Return top keywords
    result = [word for word, count in sorted_keywords[:max_keywords]]
    return result


def extract_tags(content: str, metadata: dict[str, Any] | None = None) -> list[str]:
    """
    Extract tags for categorization from content and metadata.
    
    Tags are more structured than keywords - they represent categories,
    topics, or entities that can be used for filtering.
    
    Args:
        content: Text content
        metadata: Optional metadata dict that may contain tag hints
    
    Returns:
        List of lowercase tags
    """
    tags: list[str] = []
    
    # Extract common patterns from content
    content_lower = content.lower()
    
    # Common RFP/proposal related tags
    if any(word in content_lower for word in ["rfp", "request for proposal", "proposal"]):
        tags.append("rfp")
    
    if any(word in content_lower for word in ["pricing", "price", "cost", "budget"]):
        tags.append("pricing")
    
    if any(word in content_lower for word in ["deadline", "due date", "submission"]):
        tags.append("deadline")
    
    if any(word in content_lower for word in ["workflow", "process", "procedure"]):
        tags.append("workflow")
    
    if any(word in content_lower for word in ["decision", "decided", "choose"]):
        tags.append("decision")
    
    if any(word in content_lower for word in ["preference", "prefer", "like"]):
        tags.append("preference")
    
    if any(word in content_lower for word in ["tool", "api", "integration"]):
        tags.append("tool")
    
    if any(word in content_lower for word in ["error", "failed", "failure", "issue"]):
        tags.append("error")
    
    if any(word in content_lower for word in ["success", "successful", "worked"]):
        tags.append("success")
    
    # Extract from metadata if available
    if metadata:
        # Look for RFP IDs
        if isinstance(metadata.get("rfpId"), str):
            tags.append("rfp_related")
        
        # Look for tool names
        if isinstance(metadata.get("tool"), str):
            tool_name = str(metadata.get("tool")).lower()
            tags.append(f"tool_{tool_name}")
        
        # Look for explicit tags in metadata
        if isinstance(metadata.get("tags"), list):
            for tag in metadata.get("tags", []):
                if isinstance(tag, str) and tag.strip():
                    tags.append(tag.strip().lower())
    
    # Deduplicate and limit
    unique_tags = list(dict.fromkeys(tags))[:25]  # Max 25 tags
    return unique_tags


def extract_entities(content: str) -> list[str]:
    """
    Extract entities (like RFP IDs, user IDs, etc.) from content.
    
    This is a basic implementation that looks for common patterns.
    In production, you might use NER (Named Entity Recognition).
    
    Args:
        content: Text content
    
    Returns:
        List of extracted entities
    """
    entities: list[str] = []
    
    # Extract RFP IDs (pattern: rfp_ followed by alphanumeric)
    rfp_ids = re.findall(r'\brfp_[a-zA-Z0-9-]{6,}\b', content, re.IGNORECASE)
    entities.extend([id.lower() for id in rfp_ids])
    
    # Extract proposal IDs
    proposal_ids = re.findall(r'\bprop_[a-zA-Z0-9-]{6,}\b', content, re.IGNORECASE)
    entities.extend([id.lower() for id in proposal_ids])
    
    # Extract user IDs (pattern: USER# followed by alphanumeric)
    user_ids = re.findall(r'\bUSER#[a-zA-Z0-9-]+\b', content)
    entities.extend([id.lower() for id in user_ids])
    
    # Extract email addresses
    emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', content)
    entities.extend([email.lower() for email in emails])
    
    # Deduplicate
    return list(dict.fromkeys(entities))
