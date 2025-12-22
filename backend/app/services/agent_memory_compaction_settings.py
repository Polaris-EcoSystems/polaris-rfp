"""
Intelligent compaction settings for memory compression.

Configurable compaction rules that determine when memories should be compressed
based on age, access patterns, and importance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_memory_consolidation import calculate_importance_score
from ..observability.logging import get_logger

log = get_logger("agent_memory_compaction_settings")


@dataclass
class CompactionSettings:
    """
    Configurable compaction rules for memory compression.
    
    Attributes:
        age_threshold_days: Minimum age in days for compression (default: 30)
        access_count_threshold: Maximum access count for compression (default: 5)
        importance_threshold: Maximum importance score for compression (default: 0.3)
        compression_strategy: Strategy for compression ("summarize" or "archive") (default: "summarize")
        enabled: Whether compaction is enabled (default: True)
    """
    
    age_threshold_days: int = 30
    access_count_threshold: int = 5
    importance_threshold: float = 0.3
    compression_strategy: str = "summarize"  # "summarize" or "archive"
    enabled: bool = True
    
    def should_compress(
        self,
        memory: dict[str, Any],
        days_old: int | None = None,
    ) -> bool:
        """
        Determine if a memory should be compressed based on settings.
        
        Args:
            memory: Memory dict to evaluate
            days_old: Age of memory in days (optional, will calculate if not provided)
        
        Returns:
            True if memory should be compressed, False otherwise
        """
        if not self.enabled:
            return False
        
        # Skip already compressed memories
        if memory.get("compressed", False):
            return False
        
        # Check age threshold
        if days_old is None:
            from datetime import datetime, timezone
            created_at = memory.get("createdAt", "")
            if created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    days_old = (datetime.now(timezone.utc) - created_dt.replace(tzinfo=timezone.utc)).days
                except Exception:
                    days_old = 0
            else:
                days_old = 0
        
        if days_old < self.age_threshold_days:
            return False  # Too recent
        
        # Check access count threshold
        access_count = memory.get("accessCount", 0)
        if access_count > self.access_count_threshold:
            return False  # Too frequently accessed
        
        # Check importance threshold
        try:
            importance = calculate_importance_score(memory=memory, base_access_count=access_count)
            if importance > self.importance_threshold:
                return False  # Too important
        except Exception:
            # If importance calculation fails, use access count as fallback
            pass
        
        return True


def get_compaction_settings(
    *,
    scope_id: str,
) -> CompactionSettings:
    """
    Get compaction settings for a scope.
    
    For now, returns default settings. In a full implementation,
    this would load per-scope settings from storage.
    
    Args:
        scope_id: Scope identifier
    
    Returns:
        CompactionSettings instance
    """
    # TODO: Load per-scope settings from storage (DynamoDB or config)
    # For now, return default settings
    return CompactionSettings()


def save_compaction_settings(
    *,
    scope_id: str,
    settings: CompactionSettings,
) -> bool:
    """
    Save compaction settings for a scope.
    
    For now, this is a placeholder. In a full implementation,
    this would store settings in DynamoDB or config.
    
    Args:
        scope_id: Scope identifier
        settings: CompactionSettings instance
    
    Returns:
        True if successful, False otherwise
    """
    # TODO: Store per-scope settings in DynamoDB or config
    log.info("compaction_settings_saved", scope_id=scope_id, settings=settings)
    return True
