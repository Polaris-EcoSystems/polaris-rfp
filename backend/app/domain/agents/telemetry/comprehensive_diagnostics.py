"""
Comprehensive diagnostics for the Polaris RFP backend.

Provides detailed diagnostics including:
- Credentials status (OpenAI, GitHub, Google Drive, Slack, Canva)
- Infrastructure resources (DynamoDB, S3, SQS, Cognito, ECS, CloudWatch)
- Available tools and capabilities
- Agent capabilities and skills
"""

from __future__ import annotations

from typing import Any

from ...observability.logging import get_logger
from ...settings import settings

log = get_logger("comprehensive_diagnostics")


def get_comprehensive_diagnostics() -> dict[str, Any]:
    """
    Get comprehensive diagnostics for the backend.
    
    Returns a structured dictionary with:
    - credentials: Status of all API keys and credentials
    - infrastructure: Infrastructure resources (tables, buckets, queues, etc.)
    - tools: Available tools summary
    - capabilities: Agent capabilities summary
    - recentErrors: Recent agent errors from memory
    """
    diagnostics: dict[str, Any] = {
        "credentials": _get_credentials_diagnostics(),
        "infrastructure": _get_infrastructure_diagnostics(),
        "tools": _get_tools_diagnostics(),
        "capabilities": _get_capabilities_diagnostics(),
        "recentErrors": _get_recent_agent_errors(),
    }
    
    return diagnostics


def _get_credentials_diagnostics() -> dict[str, Any]:
    """Get credentials status diagnostics."""
    creds: dict[str, Any] = {}
    
    # OpenAI
    try:
        creds["openai"] = {
            "configured": bool(settings.openai_api_key),
            "model": settings.openai_model,
            "projectId": bool(settings.openai_project_id),
            "organizationId": bool(settings.openai_organization_id),
        }
    except Exception as e:
        creds["openai"] = {"error": str(e)[:200]}
    
    # GitHub
    try:
        from ...domain.agents.infrastructure.agent_infrastructure_config import get_infrastructure_config
        from ...infrastructure.github.github_secrets import get_github_secret
        from ...infrastructure.github.github_api import _token
        
        infra_config = get_infrastructure_config()
        infra_summary = infra_config.get_summary()
        github_info = infra_summary.get("github", {})
        
        # Enhanced diagnostics
        secret_arn_configured = bool(settings.github_secret_arn and str(settings.github_secret_arn).strip())
        secret_accessible = False
        secret_keys = []
        
        if secret_arn_configured:
            try:
                secret_dict = get_github_secret()
                if secret_dict:
                    secret_accessible = True
                    secret_keys = list(secret_dict.keys()) if isinstance(secret_dict, dict) else []
            except Exception:
                pass  # Will show secret_accessible as False
        
        # Try to get token directly
        token_value = _token()
        token_configured = bool(token_value)
        
        # Try to validate token with a test API call
        token_valid = False
        if token_configured:
            try:
                import httpx
                headers = {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token_value}",
                    "User-Agent": "polaris-rfp-diagnostics",
                }
                # Make a lightweight API call to validate token
                with httpx.Client(timeout=5.0) as client:
                    resp = client.get("https://api.github.com/user", headers=headers)
                    if resp.status_code == 200:
                        token_valid = True
            except Exception:
                pass  # Token validation failed, but token is configured
        
        creds["github"] = {
            "tokenConfigured": token_configured,
            "tokenValid": token_valid,
            "secretArnConfigured": secret_arn_configured,
            "secretAccessible": secret_accessible,
            "secretKeys": secret_keys,
            "repo": github_info.get("repo"),
            "allowedRepos": github_info.get("allowedRepos", []),
        }
    except Exception as e:
        creds["github"] = {"error": str(e)[:200]}
    
    # Google Drive
    try:
        from ...domain.agents.infrastructure.agent_infrastructure_config import get_infrastructure_config
        infra_config = get_infrastructure_config()
        infra_summary = infra_config.get_summary()
        gd_info = infra_summary.get("googleDrive", {})
        creds["googleDrive"] = {
            "serviceAccountConfigured": bool(gd_info.get("serviceAccountConfigured")),
            "apiKeyConfigured": bool(gd_info.get("apiKeyConfigured")),
            "credentialsValid": bool(gd_info.get("credentialsValid")),
            "error": gd_info.get("error"),
        }
    except Exception as e:
        creds["googleDrive"] = {"error": str(e)[:200]}
    
    # Slack
    try:
        from ...infrastructure.integrations.slack.slack_web import get_bot_token
        token_present = bool(get_bot_token())
        
        # Try to validate token works
        auth_ok = False
        try:
            from ...infrastructure.integrations.slack.slack_web import slack_api_get
            if token_present:
                auth = slack_api_get(method="auth.test", params={})
                auth_ok = bool(auth.get("ok"))
        except Exception:
            pass
        
        creds["slack"] = {
            "tokenPresent": token_present,
            "authTestOk": auth_ok,
            "signingSecretConfigured": bool(settings.slack_signing_secret),
        }
    except Exception as e:
        creds["slack"] = {"error": str(e)[:200]}
    
    # Canva
    try:
        creds["canva"] = {
            "clientIdConfigured": bool(settings.canva_client_id),
            "clientSecretConfigured": bool(settings.canva_client_secret),
            "redirectUriConfigured": bool(settings.canva_redirect_uri),
            "tokenEncKeyConfigured": bool(settings.canva_token_enc_key),
        }
    except Exception as e:
        creds["canva"] = {"error": str(e)[:200]}
    
    return creds


def _get_infrastructure_diagnostics() -> dict[str, Any]:
    """Get infrastructure resources diagnostics."""
    infra: dict[str, Any] = {}
    
    try:
        from ...domain.agents.infrastructure.agent_infrastructure_config import get_infrastructure_config
        infra_config = get_infrastructure_config()
        infra_summary = infra_config.get_summary()
        
        infra["ecs"] = {
            "cluster": infra_summary.get("ecs", {}).get("cluster"),
            "service": infra_summary.get("ecs", {}).get("service"),
            "allowedClusters": len(infra_summary.get("ecs", {}).get("allowedClusters", [])),
            "allowedServices": len(infra_summary.get("ecs", {}).get("allowedServices", [])),
        }
        
        infra["cloudWatchLogs"] = {
            "logGroups": infra_summary.get("cloudWatchLogs", {}).get("count", 0),
            "discoveredAtStartup": len(infra_summary.get("cloudWatchLogs", {}).get("discoveredAtStartup", [])),
        }
        
        infra["dynamodb"] = {
            "tables": infra_summary.get("dynamodb", {}).get("count", 0),
            "tableNames": infra_summary.get("dynamodb", {}).get("tables", []),
        }
        
        infra["s3"] = {
            "buckets": infra_summary.get("s3", {}).get("bucketCount", 0),
            "bucketNames": infra_summary.get("s3", {}).get("buckets", []),
            "prefixes": len(infra_summary.get("s3", {}).get("prefixes", [])),
        }
        
        infra["sqs"] = {
            "queues": infra_summary.get("sqs", {}).get("count", 0),
        }
        
        infra["cognito"] = {
            "userPools": infra_summary.get("cognito", {}).get("count", 0),
        }
        
        infra["secrets"] = {
            "arns": infra_summary.get("secrets", {}).get("count", 0),
        }
        
        infra["loadErrors"] = infra_summary.get("loadErrors", [])
        
    except Exception as e:
        infra["error"] = str(e)[:200]
        log.error("infrastructure_diagnostics_failed", error=str(e))
    
    return infra


def _get_tools_diagnostics() -> dict[str, Any]:
    """Get tools summary diagnostics."""
    tools: dict[str, Any] = {}
    
    try:
        from ...tools.registry.read_registry import READ_TOOLS
        
        # Count tools by category
        categories: dict[str, int] = {
            "slack": 0,
            "dynamodb": 0,
            "s3": 0,
            "aws": 0,
            "github": 0,
            "telemetry": 0,
            "browser": 0,
            "memory": 0,
            "rfp": 0,
            "proposal": 0,
            "jobs": 0,
            "opportunity": 0,
            "google": 0,
            "introspection": 0,
            "external_context": 0,
            "other": 0,
        }
        
        for tool_name in READ_TOOLS.keys():
            tool_lower = tool_name.lower()
            if tool_lower.startswith("slack_"):
                categories["slack"] += 1
            elif tool_lower.startswith("ddb_") or tool_lower.startswith("dynamodb_"):
                categories["dynamodb"] += 1
            elif tool_lower.startswith("s3_"):
                categories["s3"] += 1
            elif tool_lower.startswith("ecs_") or tool_lower.startswith("sqs_") or tool_lower.startswith("cognito_") or tool_lower.startswith("secrets_") or tool_lower.startswith("aws_"):
                categories["aws"] += 1
            elif tool_lower.startswith("github_"):
                categories["github"] += 1
            elif tool_lower.startswith("telemetry_") or tool_lower.startswith("logs_"):
                categories["telemetry"] += 1
            elif tool_lower.startswith("browser_") or tool_lower.startswith("bw_"):
                categories["browser"] += 1
            elif tool_lower.startswith("agent_memory_") or tool_lower.startswith("memory_"):
                categories["memory"] += 1
            elif "rfp" in tool_lower:
                categories["rfp"] += 1
            elif "proposal" in tool_lower:
                categories["proposal"] += 1
            elif tool_lower.startswith("agent_job_") or tool_lower.startswith("job_"):
                categories["jobs"] += 1
            elif tool_lower.startswith("opportunity_") or tool_lower.startswith("journal_") or tool_lower.startswith("event_"):
                categories["opportunity"] += 1
            elif tool_lower.startswith("google_"):
                categories["google"] += 1
            elif tool_lower.startswith("list_") or tool_lower.startswith("introspect_"):
                categories["introspection"] += 1
            elif tool_lower.startswith("external_context_") or tool_lower.startswith("news_") or tool_lower.startswith("weather_"):
                categories["external_context"] += 1
            else:
                categories["other"] += 1
        
        total_tools = len(READ_TOOLS)
        
        tools["total"] = total_tools
        tools["byCategory"] = {k: v for k, v in categories.items() if v > 0}
        
    except Exception as e:
        tools["error"] = str(e)[:200]
        log.error("tools_diagnostics_failed", error=str(e))
    
    return tools


def _get_capabilities_diagnostics() -> dict[str, Any]:
    """Get capabilities summary diagnostics."""
    capabilities: dict[str, Any] = {}
    
    try:
        from ..shared.introspection.capability_inventory import get_inventory
        
        inventory = get_inventory()
        
        # Check if inventory is populated (has capabilities)
        if not hasattr(inventory, "_capabilities") or len(inventory._capabilities) == 0:
            capabilities["total"] = 0
            capabilities["note"] = "Capability inventory not populated (may need initialization)"
            return capabilities
        
        # Get counts by category
        all_caps = inventory.list_capabilities()
        
        by_category: dict[str, int] = {}
        by_subcategory: dict[str, dict[str, int]] = {}
        
        for cap in all_caps:
            cat = cap.category
            subcat = cap.subcategory or "none"
            
            by_category[cat] = by_category.get(cat, 0) + 1
            
            if cat not in by_subcategory:
                by_subcategory[cat] = {}
            by_subcategory[cat][subcat] = by_subcategory[cat].get(subcat, 0) + 1
        
        capabilities["total"] = len(all_caps)
        capabilities["byCategory"] = by_category
        capabilities["bySubcategory"] = by_subcategory
        
    except Exception as e:
        capabilities["error"] = str(e)[:200]
        log.debug("capabilities_diagnostics_failed", error=str(e))
        # Non-fatal - capability inventory might not be fully populated
    
    return capabilities


def _get_recent_agent_errors(limit: int = 5) -> dict[str, Any]:
    """Get recent agent errors from memory."""
    errors: dict[str, Any] = {
        "recent": [],
        "count": 0,
    }
    
    try:
        from ...memory.core.agent_memory_db import MemoryType, list_memories_by_type
        
        error_memories, _ = list_memories_by_type(
            memory_type=MemoryType.ERROR_LOG,
            limit=limit,
        )
        
        errors["count"] = len(error_memories)
        
        for mem in error_memories:
            metadata = mem.get("metadata", {})
            tool_name = metadata.get("toolName") or "unknown"
            error_message = metadata.get("errorMessage") or mem.get("summary", "unknown error")
            error_type = metadata.get("errorType")
            created_at = mem.get("createdAt", "")
            
            # Truncate error message for display
            error_preview = str(error_message)[:150]
            if len(str(error_message)) > 150:
                error_preview += "..."
            
            errors["recent"].append({
                "toolName": tool_name,
                "errorMessage": error_preview,
                "errorType": error_type,
                "createdAt": created_at,
                "source": mem.get("source"),
            })
        
    except Exception as e:
        errors["error"] = str(e)[:200]
        log.debug("recent_errors_diagnostics_failed", error=str(e))
        # Non-fatal - memory might not be available
    
    return errors


def format_diagnostics_for_slack(diagnostics: dict[str, Any] | None = None) -> list[str]:
    """
    Format comprehensive diagnostics for Slack display.
    
    Returns a list of lines suitable for Slack message formatting.
    """
    if diagnostics is None:
        diagnostics = get_comprehensive_diagnostics()
    
    lines: list[str] = []
    
    # Credentials section
    lines.append("*🔐 Credentials*")
    creds = diagnostics.get("credentials", {})
    
    # OpenAI
    openai = creds.get("openai", {})
    if openai.get("error"):
        lines.append(f"- OpenAI: `error` ({openai.get('error')})")
    else:
        status = "✅" if openai.get("configured") else "❌"
        model = openai.get("model", "unknown")
        lines.append(f"- OpenAI: {status} (model: `{model}`)")
    
    # GitHub
    github = creds.get("github", {})
    if github.get("error"):
        lines.append(f"- GitHub: `error` ({github.get('error')})")
    else:
        token_valid = github.get("tokenValid", False)
        token_configured = github.get("tokenConfigured", False)
        status = "✅" if token_valid else ("⚠️" if token_configured else "❌")
        repo = github.get("repo") or "none"
        lines.append(f"- GitHub: {status} (repo: `{repo}`)")
        if not token_valid and not token_configured:
            secret_arn_configured = github.get("secretArnConfigured", False)
            if not secret_arn_configured:
                lines.append("  - GITHUB_SECRET_ARN not configured")
    
    # Google Drive
    gd = creds.get("googleDrive", {})
    if gd.get("error"):
        lines.append(f"- Google Drive: `error` ({gd.get('error')})")
    else:
        valid = gd.get("credentialsValid", False)
        status = "✅" if valid else "❌"
        method = "service_account" if gd.get("serviceAccountConfigured") else ("api_key" if gd.get("apiKeyConfigured") else "none")
        lines.append(f"- Google Drive: {status} (method: `{method}`)")
    
    # Slack
    slack = creds.get("slack", {})
    if slack.get("error"):
        lines.append(f"- Slack: `error` ({slack.get('error')})")
    else:
        token_ok = slack.get("tokenPresent", False)
        auth_ok = slack.get("authTestOk", False)
        status = "✅" if (token_ok and auth_ok) else ("⚠️" if token_ok else "❌")
        lines.append(f"- Slack: {status} (token: {'ok' if token_ok else 'missing'}, auth: {'ok' if auth_ok else 'failed'})")
    
    # Canva
    canva = creds.get("canva", {})
    if canva.get("error"):
        lines.append(f"- Canva: `error` ({canva.get('error')})")
    else:
        configured = canva.get("clientIdConfigured") and canva.get("clientSecretConfigured")
        status = "✅" if configured else "❌"
        lines.append(f"- Canva: {status}")
    
    # Infrastructure section
    lines.append("")
    lines.append("*🏗️ Infrastructure*")
    infra = diagnostics.get("infrastructure", {})
    
    if infra.get("error"):
        lines.append(f"- Error loading infrastructure: {infra.get('error')}")
    else:
        ddb = infra.get("dynamodb", {})
        s3 = infra.get("s3", {})
        logs = infra.get("cloudWatchLogs", {})
        sqs = infra.get("sqs", {})
        cognito = infra.get("cognito", {})
        secrets = infra.get("secrets", {})
        
        lines.append(f"- DynamoDB: {ddb.get('tables', 0)} tables")
        lines.append(f"- S3: {s3.get('buckets', 0)} buckets, {s3.get('prefixes', 0)} prefixes")
        lines.append(f"- CloudWatch Logs: {logs.get('logGroups', 0)} log groups ({logs.get('discoveredAtStartup', 0)} discovered at startup)")
        lines.append(f"- SQS: {sqs.get('queues', 0)} queues")
        lines.append(f"- Cognito: {cognito.get('userPools', 0)} user pools")
        lines.append(f"- Secrets Manager: {secrets.get('arns', 0)} ARNs")
        
        load_errors = infra.get("loadErrors", [])
        if load_errors:
            lines.append(f"- Load errors: {len(load_errors)}")
    
    # Tools section
    lines.append("")
    lines.append("*🛠️ Tools*")
    tools = diagnostics.get("tools", {})
    
    if tools.get("error"):
        lines.append(f"- Error loading tools: {tools.get('error')}")
    else:
        total = tools.get("total", 0)
        lines.append(f"- Total tools: {total}")
        
        by_category = tools.get("byCategory", {})
        if by_category:
            lines.append("- By category:")
            for category, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  - {category}: {count}")
    
    # Capabilities section
    lines.append("")
    lines.append("*🧠 Capabilities*")
    caps = diagnostics.get("capabilities", {})
    
    if caps.get("error"):
        lines.append(f"- Error loading capabilities: {caps.get('error')}")
    else:
        total = caps.get("total", 0)
        if total > 0:
            lines.append(f"- Total capabilities: {total}")
            
            by_category = caps.get("byCategory", {})
            if by_category:
                lines.append("- By category:")
                for category, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"  - {category}: {count}")
        else:
            lines.append("- No capabilities catalogued (capability inventory may not be populated)")
    
    # Recent Errors section
    lines.append("")
    lines.append("*⚠️ Recent Agent Errors*")
    errors = diagnostics.get("recentErrors", {})
    
    if errors.get("error"):
        lines.append(f"- Error loading errors: {errors.get('error')}")
    else:
        recent = errors.get("recent", [])
        if recent:
            lines.append(f"- Last {len(recent)} errors:")
            for err in recent[:5]:  # Show up to 5 most recent
                tool = err.get("toolName", "unknown")
                error_msg = err.get("errorMessage", "unknown error")
                error_type = err.get("errorType")
                source = err.get("source", "unknown")
                
                error_line = f"  - `{tool}`: {error_msg}"
                if error_type:
                    error_line += f" ({error_type})"
                if source:
                    error_line += f" [{source}]"
                lines.append(error_line)
        else:
            lines.append("- No recent errors")
    
    return lines
