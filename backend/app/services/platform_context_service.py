"""
Platform Context Service - Unified interface for external platform data.

This service provides a single interface for accessing context from:
- GitHub (repos, commits, PRs, issues)
- Google Drive (files, folders, documents) - TODO: implement
- Canva (designs, templates)
- Web app (RFPs, proposals, users)
- Other platforms as needed

The service aggregates and caches platform context for efficient retrieval.
"""

from __future__ import annotations

from typing import Any

from ..observability.logging import get_logger

log = get_logger("platform_context_service")


class PlatformContextService:
    """
    Unified service for accessing platform context.
    
    This service:
    1. Provides unified query interface: "Get all context for user X" or "Get context for RFP Y"
    2. Aggregates data from multiple platforms
    3. Caches results for performance
    4. Handles platform-specific authentication
    """
    
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes
    
    def get_context_for_user(
        self,
        *,
        user_sub: str | None = None,
        email: str | None = None,
        slack_user_id: str | None = None,
        platforms: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get all platform context for a user.
        
        Args:
            user_sub: Cognito user sub
            email: User email
            slack_user_id: Slack user ID
            platforms: Specific platforms to fetch (None = all)
            use_cache: Whether to use cached data
        
        Returns:
            Dict with platform context organized by platform
        """
        cache_key = f"user::{user_sub or email or slack_user_id}"
        
        # Check cache
        if use_cache and cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            import time
            if (time.time() - cached_time) < self._cache_ttl_seconds:
                return cached_data
        
        result: dict[str, Any] = {
            "user_sub": user_sub,
            "email": email,
            "slack_user_id": slack_user_id,
            "platforms": {},
        }
        
        platforms_to_fetch = platforms or ["github", "canva", "web_app"]
        
        # Fetch GitHub context
        if "github" in platforms_to_fetch:
            try:
                github_ctx = self._get_github_context_for_user(
                    user_sub=user_sub,
                    email=email,
                )
                if github_ctx:
                    result["platforms"]["github"] = github_ctx
            except Exception as e:
                log.warning("github_context_fetch_failed", user_sub=user_sub, error=str(e))
                result["platforms"]["github"] = {"ok": False, "error": str(e)}
        
        # Fetch Canva context
        if "canva" in platforms_to_fetch:
            try:
                canva_ctx = self._get_canva_context_for_user(
                    user_sub=user_sub,
                    email=email,
                )
                if canva_ctx:
                    result["platforms"]["canva"] = canva_ctx
            except Exception as e:
                log.warning("canva_context_fetch_failed", user_sub=user_sub, error=str(e))
                result["platforms"]["canva"] = {"ok": False, "error": str(e)}
        
        # Fetch web app context
        if "web_app" in platforms_to_fetch:
            try:
                web_ctx = self._get_web_app_context_for_user(
                    user_sub=user_sub,
                    email=email,
                )
                if web_ctx:
                    result["platforms"]["web_app"] = web_ctx
            except Exception as e:
                log.warning("web_app_context_fetch_failed", user_sub=user_sub, error=str(e))
                result["platforms"]["web_app"] = {"ok": False, "error": str(e)}
        
        # Cache result
        import time
        self._cache[cache_key] = (time.time(), result)
        
        return result
    
    def get_context_for_rfp(
        self,
        *,
        rfp_id: str,
        platforms: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get all platform context related to an RFP.
        
        This includes:
        - GitHub: Related PRs, commits, issues
        - Canva: Related designs
        - Web app: RFP data, proposals, team members
        
        Args:
            rfp_id: RFP ID
            platforms: Specific platforms to fetch (None = all)
            use_cache: Whether to use cached data
        
        Returns:
            Dict with platform context organized by platform
        """
        cache_key = f"rfp::{rfp_id}"
        
        # Check cache
        if use_cache and cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            import time
            if (time.time() - cached_time) < self._cache_ttl_seconds:
                return cached_data
        
        result: dict[str, Any] = {
            "rfp_id": rfp_id,
            "platforms": {},
        }
        
        platforms_to_fetch = platforms or ["github", "canva", "web_app"]
        
        # Fetch GitHub context
        if "github" in platforms_to_fetch:
            try:
                github_ctx = self._get_github_context_for_rfp(rfp_id=rfp_id)
                if github_ctx:
                    result["platforms"]["github"] = github_ctx
            except Exception as e:
                log.warning("github_context_fetch_failed", rfp_id=rfp_id, error=str(e))
                result["platforms"]["github"] = {"ok": False, "error": str(e)}
        
        # Fetch Canva context
        if "canva" in platforms_to_fetch:
            try:
                canva_ctx = self._get_canva_context_for_rfp(rfp_id=rfp_id)
                if canva_ctx:
                    result["platforms"]["canva"] = canva_ctx
            except Exception as e:
                log.warning("canva_context_fetch_failed", rfp_id=rfp_id, error=str(e))
                result["platforms"]["canva"] = {"ok": False, "error": str(e)}
        
        # Fetch web app context
        if "web_app" in platforms_to_fetch:
            try:
                web_ctx = self._get_web_app_context_for_rfp(rfp_id=rfp_id)
                if web_ctx:
                    result["platforms"]["web_app"] = web_ctx
            except Exception as e:
                log.warning("web_app_context_fetch_failed", rfp_id=rfp_id, error=str(e))
                result["platforms"]["web_app"] = {"ok": False, "error": str(e)}
        
        # Cache result
        import time
        self._cache[cache_key] = (time.time(), result)
        
        return result
    
    def _get_github_context_for_user(
        self,
        *,
        user_sub: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any] | None:
        """Get GitHub context for a user."""
        # TODO: Implement GitHub user context fetching
        # This would include:
        # - User's repositories
        # - Recent commits
        # - Open PRs
        # - Issues assigned/created
        
        # For now, return empty context
        return {
            "ok": True,
            "platform": "github",
            "repositories": [],
            "recent_commits": [],
            "open_prs": [],
            "issues": [],
        }
    
    def _get_github_context_for_rfp(self, *, rfp_id: str) -> dict[str, Any] | None:
        """Get GitHub context related to an RFP."""
        # TODO: Implement GitHub RFP context fetching
        # This would include:
        # - PRs mentioning the RFP
        # - Commits related to the RFP
        # - Issues linked to the RFP
        
        # For now, return empty context
        return {
            "ok": True,
            "platform": "github",
            "related_prs": [],
            "related_commits": [],
            "related_issues": [],
        }
    
    def _get_canva_context_for_user(
        self,
        *,
        user_sub: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any] | None:
        """Get Canva context for a user."""
        # TODO: Implement Canva user context fetching
        # This would include:
        # - User's designs
        # - Recent templates used
        # - Shared designs
        
        # For now, return empty context
        return {
            "ok": True,
            "platform": "canva",
            "designs": [],
            "templates": [],
        }
    
    def _get_canva_context_for_rfp(self, *, rfp_id: str) -> dict[str, Any] | None:
        """Get Canva context related to an RFP."""
        # TODO: Implement Canva RFP context fetching
        # This would include:
        # - Designs created for the RFP
        # - Templates used
        # - Shared designs
        
        # For now, return empty context
        return {
            "ok": True,
            "platform": "canva",
            "designs": [],
            "templates": [],
        }
    
    def _get_web_app_context_for_user(
        self,
        *,
        user_sub: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any] | None:
        """Get web app context for a user."""
        from ..repositories.users.user_profiles_repo import get_user_profile
        
        if not user_sub:
            return None
        
        try:
            user_profile = get_user_profile(user_sub=user_sub)
            if not user_profile:
                return None
            
            # Get user's RFPs and proposals
            from ..repositories.rfp.rfps_repo import list_rfps
            from ..repositories.rfp.proposals_repo import list_proposals
            
            # Get RFPs where user is involved (simplified - would need proper filtering)
            rfps_result = list_rfps(page=1, limit=50, next_token=None)
            user_rfps = rfps_result.get("data", [])
            
            # Get proposals
            proposals_result = list_proposals(page=1, limit=50, next_token=None)
            user_proposals = proposals_result.get("data", [])
            
            return {
                "ok": True,
                "platform": "web_app",
                "user_profile": user_profile,
                "rfps": user_rfps[:10],  # Limit to 10 most recent
                "proposals": user_proposals[:10],  # Limit to 10 most recent
            }
        except Exception as e:
            log.warning("web_app_user_context_fetch_failed", user_sub=user_sub, error=str(e))
            return None
    
    def _get_web_app_context_for_rfp(self, *, rfp_id: str) -> dict[str, Any] | None:
        """Get web app context for an RFP."""
        try:
            from ..repositories.rfp.rfps_repo import get_rfp_by_id
            from ..repositories.rfp.proposals_repo import list_proposals
            from ..repositories.rfp.opportunity_state_repo import get_state
            
            # Get RFP
            rfp = get_rfp_by_id(rfp_id=rfp_id)
            if not rfp:
                return None
            
            # Get proposals for this RFP
            proposals_result = list_proposals(page=1, limit=50, next_token=None)
            rfp_proposals = [
                p for p in (proposals_result.get("data") or [])
                if str(p.get("rfpId") or "").strip() == rfp_id
            ]
            
            # Get opportunity state
            opp_state = get_state(rfp_id=rfp_id)
            
            return {
                "ok": True,
                "platform": "web_app",
                "rfp": rfp,
                "proposals": rfp_proposals,
                "opportunity_state": opp_state,
            }
        except Exception as e:
            log.warning("web_app_rfp_context_fetch_failed", rfp_id=rfp_id, error=str(e))
            return None
    
    def format_context_for_prompt(
        self,
        *,
        context: dict[str, Any],
        max_chars: int = 3000,
    ) -> str:
        """
        Format platform context for inclusion in agent prompts.
        
        Args:
            context: Context dict from get_context_for_user or get_context_for_rfp
            max_chars: Maximum characters for formatted output
        
        Returns:
            Formatted string for prompt inclusion
        """
        lines: list[str] = []
        lines.append("=== PLATFORM_CONTEXT (External Platform Data) ===")
        lines.append("")
        
        platforms = context.get("platforms", {})
        
        # Format GitHub context
        if "github" in platforms and platforms["github"].get("ok"):
            github = platforms["github"]
            lines.append("GitHub:")
            if github.get("repositories"):
                lines.append(f"  Repositories: {len(github['repositories'])}")
            if github.get("recent_commits"):
                lines.append(f"  Recent commits: {len(github['recent_commits'])}")
            if github.get("open_prs"):
                lines.append(f"  Open PRs: {len(github['open_prs'])}")
            lines.append("")
        
        # Format Canva context
        if "canva" in platforms and platforms["canva"].get("ok"):
            canva = platforms["canva"]
            lines.append("Canva:")
            if canva.get("designs"):
                lines.append(f"  Designs: {len(canva['designs'])}")
            if canva.get("templates"):
                lines.append(f"  Templates: {len(canva['templates'])}")
            lines.append("")
        
        # Format web app context
        if "web_app" in platforms and platforms["web_app"].get("ok"):
            web = platforms["web_app"]
            lines.append("Web App:")
            if web.get("rfp"):
                rfp = web["rfp"]
                rfp_title = rfp.get("title") or rfp.get("name") or "Unknown"
                lines.append(f"  RFP: {rfp_title}")
            if web.get("proposals"):
                lines.append(f"  Proposals: {len(web['proposals'])}")
            if web.get("opportunity_state"):
                state = web["opportunity_state"]
                stage = state.get("stage") or "unknown"
                lines.append(f"  Stage: {stage}")
            lines.append("")
        
        formatted = "\n".join(lines).strip()
        
        # Truncate if needed
        if len(formatted) > max_chars:
            formatted = formatted[:max_chars - 100] + "\n\n[Platform context truncated...]"
        
        return formatted
    
    def clear_cache(self) -> None:
        """Clear the platform context cache."""
        self._cache.clear()
        log.info("platform_context_cache_cleared")


# Singleton instance
_service: PlatformContextService | None = None


def get_platform_context_service() -> PlatformContextService:
    """Get the singleton platform context service instance."""
    global _service
    if _service is None:
        _service = PlatformContextService()
    return _service
