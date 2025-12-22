from __future__ import annotations

import time
from typing import Any

from ...settings import settings
from .allowlist import parse_csv, uniq
from .aws_clients import logs_client, ecs_client


def _default_log_groups() -> list[str]:
    env = str(settings.normalized_environment or "").strip() or "production"
    # From CloudFormation templates.
    return [
        f"/ecs/polaris-backend-{env}",
        f"/ecs/polaris-contracting-worker-{env}",
        f"/ecs/northstar-ambient-{env}",
        f"/ecs/northstar-job-runner-{env}",
        f"/ecs/northstar-daily-report-{env}",
    ]


def _allowed_log_groups() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_log_groups))
    if explicit:
        return explicit
    return uniq(_default_log_groups())


def _require_allowed_log_group(name: str) -> str:
    lg = str(name or "").strip()
    if not lg:
        raise ValueError("missing_logGroupName")
    allowed = _allowed_log_groups()
    if allowed and lg not in allowed:
        raise ValueError("log_group_not_allowed")
    return lg


def tail_log_group(
    *,
    log_group_name: str,
    lookback_minutes: int = 15,
    limit: int = 50,
) -> dict[str, Any]:
    lg = _require_allowed_log_group(log_group_name)
    lb = max(1, min(180, int(lookback_minutes or 15)))
    lim = max(1, min(200, int(limit or 50)))
    start_ms = int((time.time() - (lb * 60)) * 1000)
    resp = logs_client().filter_log_events(
        logGroupName=lg,
        startTime=start_ms,
        limit=lim,
    )
    evs = resp.get("events") if isinstance(resp, dict) else None
    rows = evs if isinstance(evs, list) else []
    out: list[dict[str, Any]] = []
    for e in rows[:lim]:
        if not isinstance(e, dict):
            continue
        msg = str(e.get("message") or "")
        out.append(
            {
                "timestamp": int(e.get("timestamp") or 0) or None,
                "ingestionTime": int(e.get("ingestionTime") or 0) or None,
                "message": (msg[:1800] + "…") if len(msg) > 1800 else msg,
            }
        )
    return {"ok": True, "logGroupName": lg, "lookbackMinutes": lb, "events": out}


def discover_log_groups_for_ecs_service(*, cluster: str | None = None, service: str | None = None) -> dict[str, Any]:
    """
    Discover CloudWatch log groups for an ECS service by querying its task definition.
    
    If cluster/service not provided, tries to use ECS metadata introspection to discover them.
    """
    from .aws_ecs import _resolve_cluster, _resolve_service, describe_task_definition
    
    # Try to resolve cluster and service
    try:
        c = _resolve_cluster(cluster) if cluster else None
        s = _resolve_service(service) if service else None
    except ValueError:
        c = None
        s = None
    
    # If we don't have cluster/service, try ECS metadata introspection
    if not c or not s:
        try:
            from .aws_ecs import metadata_introspect
            metadata = metadata_introspect()
            if metadata.get("ok"):
                c = metadata.get("cluster") or c
                # Try to infer service name from task family (common pattern: service name matches task family)
                task_family = metadata.get("taskFamily")
                if task_family and not s:
                    # Common pattern: task family is like "northstar-job-runner-production"
                    # Service name might be similar or same
                    s = task_family
        except Exception:
            pass
    
    if not c or not s:
        return {
            "ok": False,
            "error": "missing_cluster_or_service",
            "hint": "Provide cluster and service, or run ecs_metadata_introspect first to auto-discover",
        }
    
    # Get service info to find current task definition
    try:
        resp = ecs_client().describe_services(cluster=c, services=[s])
        services = resp.get("services") if isinstance(resp, dict) else None
        sv = services[0] if (services and isinstance(services, list) and services) else None
        if not isinstance(sv, dict):
            return {"ok": False, "error": "service_not_found", "cluster": c, "service": s}
        
        task_def_arn = sv.get("taskDefinition")
        if not task_def_arn:
            return {"ok": False, "error": "no_task_definition", "cluster": c, "service": s}
    except Exception as e:
        return {"ok": False, "error": str(e) or "ecs_api_failed", "cluster": c, "service": s}
    
    # Get task definition to find log configuration
    try:
        td_resp = describe_task_definition(task_definition=task_def_arn)
        if not td_resp.get("ok"):
            return {"ok": False, "error": "task_definition_not_found", "taskDefinition": task_def_arn}
        
        # Get full task definition for log configuration
        resp = ecs_client().describe_task_definition(taskDefinition=task_def_arn)
        td = resp.get("taskDefinition") if isinstance(resp, dict) else None
        if not isinstance(td, dict):
            return {"ok": False, "error": "task_definition_invalid"}
        
        log_groups: list[str] = []
        container_defs = td.get("containerDefinitions") or []
        
        for container in container_defs:
            if not isinstance(container, dict):
                continue
            log_config = container.get("logConfiguration")
            if isinstance(log_config, dict):
                log_driver = log_config.get("logDriver")
                if log_driver == "awslogs":
                    options = log_config.get("options") or {}
                    log_group = options.get("awslogs-group")
                    if log_group and isinstance(log_group, str):
                        log_groups.append(log_group)
        
        # Also infer log group from service name pattern (common pattern: /ecs/{service-name}-{env})
        env = str(settings.normalized_environment or "").strip() or "production"
        inferred_log_group = f"/ecs/{s}-{env}"
        
        result: dict[str, Any] = {
            "ok": True,
            "cluster": c,
            "service": s,
            "taskDefinition": task_def_arn,
            "logGroups": list(set(log_groups)),  # Deduplicate
        }
        
        # If we found log groups, also check if inferred one is different
        if log_groups and inferred_log_group not in log_groups:
            result["inferredLogGroup"] = inferred_log_group
            result["hint"] = f"Task definition uses {log_groups}, but common pattern would be {inferred_log_group}"
        
        return result
        
    except Exception as e:
        return {"ok": False, "error": str(e) or "task_definition_query_failed"}


def list_available_log_groups(*, prefix: str | None = None, limit: int = 50) -> dict[str, Any]:
    """
    List available CloudWatch log groups (allowlisted or matching common patterns).
    
    This provides introspection capability - agent can discover what log groups exist
    that it might be able to access.
    """
    lim = max(1, min(200, int(limit or 50)))
    prefix_filter = str(prefix or "").strip() or None
    
    # First, return allowlisted log groups
    allowed = _allowed_log_groups()
    result_log_groups: list[str] = []
    
    if prefix_filter:
        result_log_groups = [lg for lg in allowed if lg.startswith(prefix_filter)]
    else:
        result_log_groups = allowed[:lim]
    
    result: dict[str, Any] = {
        "ok": True,
        "logGroups": result_log_groups,
        "source": "allowlist",
        "count": len(result_log_groups),
    }
    
    # If we have space and a prefix, try to query CloudWatch Logs API for matching groups
    # (This helps discover log groups that match patterns even if not explicitly allowlisted)
    if prefix_filter and len(result_log_groups) < lim:
        try:
            logs = logs_client()
            paginator = logs.get_paginator("describe_log_groups")
            discovered: list[str] = []
            
            for page in paginator.paginate(logGroupNamePrefix=prefix_filter, limit=lim - len(result_log_groups)):
                groups = page.get("logGroups") or []
                for group in groups:
                    if not isinstance(group, dict):
                        continue
                    group_name = group.get("logGroupName")
                    if group_name and isinstance(group_name, str):
                        # Only include if it matches common patterns we expect
                        if "/ecs/" in group_name or group_name.startswith("/aws/"):
                            if group_name not in result_log_groups:
                                discovered.append(group_name)
                                if len(discovered) >= (lim - len(result_log_groups)):
                                    break
                if len(discovered) >= (lim - len(result_log_groups)):
                    break
            
            if discovered:
                result["logGroups"] = result_log_groups + discovered
                result["count"] = len(result["logGroups"])
                result["discovered"] = discovered
                result["hint"] = f"Discovered {len(discovered)} additional log groups matching prefix '{prefix_filter}'"
        except Exception:
            # Non-fatal - just return what we have from allowlist
            pass
    
    return result

