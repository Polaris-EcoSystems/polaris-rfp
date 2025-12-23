"""
Agent Infrastructure Configuration - Pre-loaded at startup.

This module loads infrastructure configuration at application startup and caches it
for use by agent introspection tools. This allows the agent to have immediate
awareness of available resources without runtime queries for static configuration.

Runtime queries are still supported for dynamic discovery, but static config is
pre-loaded for faster access.
"""

from __future__ import annotations

import time
from typing import Any

from ....observability.logging import get_logger
from ....settings import settings
from ....tools.registry.aws_clients import logs_client
from ....tools.categories.aws.aws_ecs import _allowed_clusters, _allowed_services
from ....tools.categories.aws.aws_logs import _allowed_log_groups
from ....infrastructure.github.github_api import _allowed_repos

log = get_logger("agent_infrastructure_config")


class InfrastructureConfig:
    """
    Cached infrastructure configuration loaded at startup.
    
    This is populated once during application startup and provides fast access
    to static infrastructure metadata without runtime queries.
    """
    
    def __init__(self):
        self._loaded_at: float | None = None
        self._load_errors: list[str] = []
        
        # GitHub configuration
        self.github_repo: str | None = None
        self.github_allowed_repos: list[str] = []
        self.github_token_configured: bool = False
        
        # ECS configuration
        self.ecs_cluster: str | None = None
        self.ecs_service: str | None = None
        self.ecs_allowed_clusters: list[str] = []
        self.ecs_allowed_services: list[str] = []
        
        # CloudWatch Logs configuration
        self.log_groups: list[str] = []
        self.log_groups_discovered: list[str] = []  # From runtime discovery
        
        # DynamoDB configuration
        self.dynamodb_tables: list[str] = []
        
        # S3 configuration
        self.s3_buckets: list[str] = []
        self.s3_prefixes: list[str] = []
        
        # SQS configuration
        self.sqs_queues: list[str] = []
        
        # Cognito configuration
        self.cognito_user_pools: list[str] = []
        
        # Secrets Manager configuration
        self.secrets_arns: list[str] = []
        
        # Google Drive configuration
        self.google_drive_service_account_configured: bool = False
        self.google_drive_api_key_configured: bool = False
        self.google_drive_credentials_valid: bool = False
        self.google_drive_credentials_error: str | None = None
    
    def load(self) -> None:
        """Load infrastructure configuration from settings and runtime discovery."""
        start_time = time.time()
        log.info("loading_infrastructure_config")
        
        try:
            # Load from settings (static configuration)
            self._load_from_settings()
            
            # Perform runtime discovery (best-effort, non-blocking)
            self._discover_runtime_config()
            
            self._loaded_at = time.time()
            duration_ms = int((self._loaded_at - start_time) * 1000)
            
            log.info(
                "infrastructure_config_loaded",
                duration_ms=duration_ms,
                github_repos=len(self.github_allowed_repos),
                log_groups=len(self.log_groups),
                ecs_clusters=len(self.ecs_allowed_clusters),
                errors=len(self._load_errors),
            )
        except Exception as e:
            log.warning("infrastructure_config_load_failed", error=str(e))
            self._load_errors.append(f"Load failed: {str(e)}")
    
    def _load_from_settings(self) -> None:
        """Load static configuration from settings."""
        # GitHub
        self.github_repo = settings.github_repo
        self.github_allowed_repos = _allowed_repos()
        
        try:
            from ....infrastructure.github.github_api import _token
            self.github_token_configured = bool(_token())
        except Exception:
            self.github_token_configured = False
        
        # ECS
        self.ecs_cluster = settings.ecs_cluster
        self.ecs_service = settings.ecs_service
        self.ecs_allowed_clusters = _allowed_clusters()
        self.ecs_allowed_services = _allowed_services()
        
        # CloudWatch Logs - load from settings/allowlist
        self.log_groups = _allowed_log_groups()
        
        # DynamoDB
        if settings.agent_allowed_ddb_tables:
            from ....tools.registry.allowlist import parse_csv, uniq
            self.dynamodb_tables = uniq(parse_csv(settings.agent_allowed_ddb_tables))
        
        # S3
        if settings.agent_allowed_s3_buckets:
            from ....tools.registry.allowlist import parse_csv, uniq
            self.s3_buckets = uniq(parse_csv(settings.agent_allowed_s3_buckets))
        
        if settings.agent_allowed_s3_prefixes:
            from ....tools.registry.allowlist import parse_csv, uniq
            self.s3_prefixes = uniq(parse_csv(settings.agent_allowed_s3_prefixes))
        
        # SQS
        if settings.agent_allowed_sqs_queue_urls:
            from ....tools.registry.allowlist import parse_csv, uniq
            self.sqs_queues = uniq(parse_csv(settings.agent_allowed_sqs_queue_urls))
        
        # Cognito
        if settings.agent_allowed_cognito_user_pool_ids:
            from ....tools.registry.allowlist import parse_csv, uniq
            self.cognito_user_pools = uniq(parse_csv(settings.agent_allowed_cognito_user_pool_ids))
        elif settings.cognito_user_pool_id:
            self.cognito_user_pools = [settings.cognito_user_pool_id]
        
        # Secrets Manager
        if settings.agent_allowed_secrets_arns:
            from ....tools.registry.allowlist import parse_csv, uniq
            self.secrets_arns = uniq(parse_csv(settings.agent_allowed_secrets_arns))
        
        # Google Drive credentials validation
        self._validate_google_drive_credentials()
    
    def _validate_google_drive_credentials(self) -> None:
        """
        Validate Google Drive credentials are accessible and can be loaded.
        
        Checks:
        - Service account JSON credentials can be loaded from Secrets Manager
        - API key can be loaded from Secrets Manager (fallback)
        - Service account credentials can be initialized (valid JSON format)
        
        Note: This validates credentials can be loaded, not that they actually work.
        Full validation (API call test) happens on first use via the tools.
        """
        # Check service account credentials (preferred)
        try:
            from ....tools.categories.google.google_drive import _get_google_credentials
            
            # Try to load service account credentials (validates they exist and are valid JSON)
            credentials = _get_google_credentials(use_api_key=False)
            if credentials:
                self.google_drive_service_account_configured = True
                self.google_drive_credentials_valid = True
                log.info("google_drive_service_account_configured")
        except Exception as e:
            error_msg = str(e)[:200]
            self.google_drive_credentials_error = f"Service account: {error_msg}"
            log.debug("google_drive_service_account_not_configured", error=error_msg)
        
        # Check API key (fallback)
        try:
            from ....tools.categories.google.google_drive import _get_google_credentials
            api_key = _get_google_credentials(use_api_key=True)
            if api_key and isinstance(api_key, str) and api_key.strip():
                self.google_drive_api_key_configured = True
                # If service account failed but API key works, mark as valid
                if not self.google_drive_credentials_valid:
                    self.google_drive_credentials_valid = True
                    self.google_drive_credentials_error = None
                    log.info("google_drive_api_key_configured")
        except Exception as e:
            if not self.google_drive_service_account_configured:
                # Only set error if service account also failed
                if not self.google_drive_credentials_error:
                    self.google_drive_credentials_error = f"API key: {str(e)[:200]}"
                log.debug("google_drive_api_key_not_configured", error=str(e))
    
    def _discover_runtime_config(self) -> None:
        """Discover additional configuration from AWS APIs (best-effort, non-blocking)."""
        # Discover CloudWatch log groups matching common patterns
        try:
            env = str(settings.normalized_environment or "").strip() or "production"
            
            # Method 1: Query CloudWatch Logs for log groups matching common patterns
            # We limit to /ecs/ and /aws/ prefixes to avoid expensive queries
            try:
                logs = logs_client()
                paginator = logs.get_paginator("describe_log_groups")
                discovered: list[str] = []
                
                # Query for common ECS log group pattern
                for page in paginator.paginate(logGroupNamePrefix="/ecs/", limitPerPage=50):
                    groups = page.get("logGroups") or []
                    for group in groups[:50]:  # Limit per page
                        if not isinstance(group, dict):
                            continue
                        group_name = group.get("logGroupName")
                        if group_name and isinstance(group_name, str):
                            # Include if it matches our environment pattern
                            if f"-{env}" in group_name:
                                discovered.append(group_name)
                
                # Add discovered groups that aren't already in our list
                for lg in discovered:
                    if lg not in self.log_groups:
                        self.log_groups_discovered.append(lg)
                        self.log_groups.append(lg)
                
                if self.log_groups_discovered:
                    log.info(
                        "log_groups_discovered_at_startup",
                        count=len(self.log_groups_discovered),
                        groups=self.log_groups_discovered[:10],  # Log first 10
                    )
            except Exception as e:
                log.debug("log_groups_discovery_failed", error=str(e))
                self._load_errors.append(f"Log groups discovery: {str(e)}")
            
            # Method 2: Discover log groups from ECS services via task definitions
            # This finds log groups configured in task definitions (more accurate)
            try:
                from ....tools.categories.aws.aws_logs import discover_log_groups_for_ecs_service
                
                # Try to discover from configured ECS cluster/service if available
                if self.ecs_cluster and self.ecs_service:
                    discovery_result = discover_log_groups_for_ecs_service(
                        cluster=self.ecs_cluster,
                        service=self.ecs_service,
                    )
                    if discovery_result.get("ok"):
                        service_log_groups = discovery_result.get("logGroups", [])
                        for lg in service_log_groups:
                            if lg and lg not in self.log_groups:
                                self.log_groups_discovered.append(lg)
                                self.log_groups.append(lg)
                
                # Also try other allowed services
                for service in self.ecs_allowed_services[:5]:  # Limit to first 5 services
                    if service == self.ecs_service:
                        continue  # Already processed
                    
                    discovery_result = discover_log_groups_for_ecs_service(
                        cluster=self.ecs_cluster,
                        service=service,
                    )
                    if discovery_result.get("ok"):
                        service_log_groups = discovery_result.get("logGroups", [])
                        for lg in service_log_groups:
                            if lg and lg not in self.log_groups:
                                self.log_groups_discovered.append(lg)
                                self.log_groups.append(lg)
            except Exception as e:
                log.debug("ecs_service_log_groups_discovery_failed", error=str(e))
                self._load_errors.append(f"ECS service log groups discovery: {str(e)}")
        
        except Exception as e:
            log.debug("runtime_config_discovery_failed", error=str(e))
            self._load_errors.append(f"Runtime discovery: {str(e)}")
    
    def get_summary(self) -> dict[str, Any]:
        """Get a summary of loaded configuration for introspection."""
        return {
            "loadedAt": self._loaded_at,
            "loadErrors": self._load_errors,
            "github": {
                "repo": self.github_repo,
                "allowedRepos": self.github_allowed_repos,
                "tokenConfigured": self.github_token_configured,
            },
            "ecs": {
                "cluster": self.ecs_cluster,
                "service": self.ecs_service,
                "allowedClusters": self.ecs_allowed_clusters,
                "allowedServices": self.ecs_allowed_services,
            },
            "cloudWatchLogs": {
                "logGroups": self.log_groups,
                "discoveredAtStartup": self.log_groups_discovered,
                "count": len(self.log_groups),
            },
            "dynamodb": {
                "tables": self.dynamodb_tables,
                "count": len(self.dynamodb_tables),
            },
            "s3": {
                "buckets": self.s3_buckets,
                "prefixes": self.s3_prefixes,
                "bucketCount": len(self.s3_buckets),
            },
            "sqs": {
                "queues": self.sqs_queues,
                "count": len(self.sqs_queues),
            },
            "cognito": {
                "userPools": self.cognito_user_pools,
                "count": len(self.cognito_user_pools),
            },
            "secrets": {
                "arns": self.secrets_arns,
                "count": len(self.secrets_arns),
            },
            "googleDrive": {
                "serviceAccountConfigured": self.google_drive_service_account_configured,
                "apiKeyConfigured": self.google_drive_api_key_configured,
                "credentialsValid": self.google_drive_credentials_valid,
                "error": self.google_drive_credentials_error,
            },
        }


# Global instance - populated at startup
_infrastructure_config: InfrastructureConfig | None = None


def get_infrastructure_config() -> InfrastructureConfig:
    """Get the cached infrastructure configuration."""
    global _infrastructure_config
    if _infrastructure_config is None:
        # Lazy initialization if not loaded at startup
        _infrastructure_config = InfrastructureConfig()
        _infrastructure_config.load()
    return _infrastructure_config


def initialize_infrastructure_config() -> None:
    """Initialize infrastructure configuration (called at startup)."""
    global _infrastructure_config
    if _infrastructure_config is None:
        _infrastructure_config = InfrastructureConfig()
        _infrastructure_config.load()
