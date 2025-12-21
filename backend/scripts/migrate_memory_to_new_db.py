#!/usr/bin/env python3
"""
Migration script to move existing memory data from user profiles to the new structured memory database.

This script:
1. Reads aiMemorySummary and aiPreferences from all user profiles
2. Converts them to structured memories in the new memory database
3. Optionally indexes them in OpenSearch
4. Reports migration statistics

Usage:
    python -m app.scripts.migrate_memory_to_new_db [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(__file__ + "/../../.."))

from app.services.user_profiles_repo import get_user_profile
from app.observability.logging import get_logger

log = get_logger("migrate_memory")


def _scan_all_user_profiles(limit: int | None = None) -> list[dict[str, Any]]:
    """
    Scan all user profiles from the main table.
    
    Note: This requires a scan operation which can be expensive.
    For large datasets, consider running this during off-peak hours.
    
    Since DynamoTable doesn't have scan_page, we'll use a different approach:
    iterate through known user_subs if available, or use raw boto3 scan.
    
    Args:
        limit: Maximum number of profiles to return (not yet implemented)
    """
    # For now, this is a placeholder - full implementation would require
    # either a GSI on entityType or a manual list of user_subs
    # In practice, you might have user_subs from another source
    # TODO: Implement limit when implementing actual scan
    profiles: list[dict[str, Any]] = []
    
    # TODO: Implement actual scan using boto3 client directly if needed
    # For migration purposes, it's often better to provide user_subs explicitly
    # or migrate incrementally as users interact with the system
    
    return profiles


def migrate_user_memory(user_sub: str, dry_run: bool = False) -> dict[str, Any]:
    """
    Migrate a single user's memory data to the new database.
    
    Returns:
        Dict with migration results
    """
    profile = get_user_profile(user_sub=user_sub)
    if not profile:
        return {"user_sub": user_sub, "migrated": False, "reason": "profile_not_found"}
    
    migrated_count = 0
    errors: list[str] = []
    
    # Migrate aiMemorySummary to episodic memories
    memory_summary = str(profile.get("aiMemorySummary") or "").strip()
    if memory_summary:
        try:
            if not dry_run:
                from app.services.agent_memory import add_episodic_memory
                add_episodic_memory(
                    user_sub=user_sub,
                    content=memory_summary,
                    context={
                        "migratedFrom": "aiMemorySummary",
                        "originalSource": "user_profile",
                    },
                    cognito_user_id=user_sub,  # user_sub is cognito sub
                    source="migration",
                )
                migrated_count += 1
            else:
                migrated_count += 1
                log.info("would_migrate_episodic", user_sub=user_sub, content_length=len(memory_summary))
        except Exception as e:
            errors.append(f"episodic_migration_failed: {str(e)}")
    
    # Migrate aiPreferences to semantic memories
    preferences = profile.get("aiPreferences")
    if isinstance(preferences, dict) and preferences:
        try:
            if not dry_run:
                from app.services.agent_memory import update_semantic_memory
                for key, value in preferences.items():
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        update_semantic_memory(
                            user_sub=user_sub,
                            key=key,
                            value=value,
                            cognito_user_id=user_sub,  # user_sub is cognito sub
                            source="migration",
                        )
                        migrated_count += 1
            else:
                migrated_count += len([k for k, v in preferences.items() if isinstance(v, (str, int, float, bool)) or v is None])
                log.info("would_migrate_semantic", user_sub=user_sub, preference_count=len(preferences))
        except Exception as e:
            errors.append(f"semantic_migration_failed: {str(e)}")
    
    return {
        "user_sub": user_sub,
        "migrated": migrated_count > 0,
        "migrated_count": migrated_count,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate memory data to new structured database")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually write, just report what would be migrated")
    parser.add_argument("--limit", type=int, help="Limit number of users to migrate (for testing)")
    parser.add_argument("--user-sub", type=str, help="Migrate specific user only")
    args = parser.parse_args()
    
    dry_run = args.dry_run
    _ = args.limit  # TODO: Implement limit support when batch migration is implemented
    
    if dry_run:
        log.info("migration_dry_run", message="DRY RUN MODE - no changes will be made")
    
    if args.user_sub:
        # Migrate single user
        result = migrate_user_memory(args.user_sub, dry_run=dry_run)
        log.info("migration_result", **result)
        print(f"User {args.user_sub}: migrated={result['migrated']}, count={result['migrated_count']}, errors={len(result['errors'])}")
    else:
        # Migrate all users (requires explicit user_sub list for now)
        # In production, you might have a list of user_subs or implement scanning
        log.warning("full_migration_requires_user_list", message="Provide --user-sub for specific users, or implement user list scanning")
        print("Please use --user-sub to migrate specific users, or implement user list scanning.")
        print("Example: python -m app.scripts.migrate_memory_to_new_db --user-sub <user_sub>")
        return 1
    
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
