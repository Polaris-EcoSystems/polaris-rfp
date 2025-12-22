from __future__ import annotations

import os
from typing import Any

import httpx

from ....observability.logging import get_logger
from ....settings import settings
from ...registry.allowlist import parse_csv, uniq
from ...registry.aws_clients import ecs_client

# Import settings at module level for use in metadata_introspect

log = get_logger("aws_ecs")


def _allowed_clusters() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_ecs_clusters))
    if explicit:
        return explicit
    # Derive from core config.
    return uniq([str(settings.ecs_cluster or "").strip()])


def _allowed_services() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_ecs_services))
    if explicit:
        return explicit
    return uniq([str(settings.ecs_service or "").strip()])


def _resolve_cluster(cluster: str | None) -> str:
    c = str(cluster or "").strip() or str(settings.ecs_cluster or "").strip()
    if not c:
        raise ValueError("missing_cluster")
    allowed = [x for x in _allowed_clusters() if x]
    if allowed and c not in allowed:
        raise ValueError("cluster_not_allowed")
    return c


def _resolve_service(service: str | None) -> str:
    s = str(service or "").strip() or str(settings.ecs_service or "").strip()
    if not s:
        raise ValueError("missing_service")
    allowed = [x for x in _allowed_services() if x]
    if allowed and s not in allowed:
        raise ValueError("service_not_allowed")
    return s


def describe_service(*, cluster: str | None, service: str | None) -> dict[str, Any]:
    c = _resolve_cluster(cluster)
    s = _resolve_service(service)
    resp = ecs_client().describe_services(cluster=c, services=[s])
    services = resp.get("services") if isinstance(resp, dict) else None
    rows = services if isinstance(services, list) else []
    sv = rows[0] if rows else None
    if not isinstance(sv, dict):
        return {"ok": False, "error": "service_not_found"}

    # Trim to the essentials for conversational use.
    deployments = sv.get("deployments")
    deps = deployments if isinstance(deployments, list) else []
    dep_out: list[dict[str, Any]] = []
    for d in deps[:10]:
        if not isinstance(d, dict):
            continue
        dep_out.append(
            {
                "status": d.get("status"),
                "taskDefinition": d.get("taskDefinition"),
                "desiredCount": d.get("desiredCount"),
                "pendingCount": d.get("pendingCount"),
                "runningCount": d.get("runningCount"),
                "rolloutState": d.get("rolloutState"),
                "rolloutStateReason": d.get("rolloutStateReason"),
                "createdAt": str(d.get("createdAt") or "") or None,
                "updatedAt": str(d.get("updatedAt") or "") or None,
            }
        )
    events_raw = sv.get("events")
    events_list: list[Any] = events_raw if isinstance(events_raw, list) else []

    return {
        "ok": True,
        "cluster": c,
        "service": s,
        "status": sv.get("status"),
        "desiredCount": sv.get("desiredCount"),
        "runningCount": sv.get("runningCount"),
        "pendingCount": sv.get("pendingCount"),
        "taskDefinition": sv.get("taskDefinition"),
        "deployments": dep_out,
        "eventsPreview": [
            {
                "createdAt": str(e.get("createdAt") or "") or None,
                "message": str(e.get("message") or "")[:400],
            }
            for e in events_list[:8]
            if isinstance(e, dict)
        ],
    }


def list_tasks(*, cluster: str | None, service: str | None, desired_status: str | None = None, limit: int = 25) -> dict[str, Any]:
    c = _resolve_cluster(cluster)
    s = _resolve_service(service)
    lim = max(1, min(50, int(limit or 25)))
    ds = str(desired_status or "").strip().upper() or "RUNNING"
    if ds not in ("RUNNING", "PENDING", "STOPPED"):
        ds = "RUNNING"
    resp = ecs_client().list_tasks(cluster=c, serviceName=s, desiredStatus=ds, maxResults=lim)
    arns = resp.get("taskArns") if isinstance(resp, dict) else None
    task_arns = [str(x) for x in (arns if isinstance(arns, list) else []) if str(x).strip()]
    return {"ok": True, "cluster": c, "service": s, "desiredStatus": ds, "taskArns": task_arns[:lim]}


def describe_task_definition(*, task_definition: str) -> dict[str, Any]:
    td = str(task_definition or "").strip()
    if not td:
        return {"ok": False, "error": "missing_taskDefinition"}
    resp = ecs_client().describe_task_definition(taskDefinition=td, include=["TAGS"])
    t = resp.get("taskDefinition") if isinstance(resp, dict) else None
    if not isinstance(t, dict):
        return {"ok": False, "error": "not_found"}
    # Keep a compact view.
    return {
        "ok": True,
        "taskDefinitionArn": t.get("taskDefinitionArn"),
        "family": t.get("family"),
        "revision": t.get("revision"),
        "cpu": t.get("cpu"),
        "memory": t.get("memory"),
        "networkMode": t.get("networkMode"),
        "requiresCompatibilities": t.get("requiresCompatibilities"),
        "containerNames": [c.get("name") for c in (t.get("containerDefinitions") or []) if isinstance(c, dict) and c.get("name")],
    }


def update_service(
    *,
    cluster: str | None,
    service: str | None,
    force_new_deployment: bool | None = None,
    desired_count: int | None = None,
) -> dict[str, Any]:
    """
    Update an ECS service (approval-gated by caller).
    Allowlist enforced via ECS_CLUSTER/ECS_SERVICE (or explicit allowlist envs).
    """
    c = _resolve_cluster(cluster)
    s = _resolve_service(service)
    kwargs: dict[str, Any] = {"cluster": c, "service": s}
    if force_new_deployment is True:
        kwargs["forceNewDeployment"] = True
    if desired_count is not None:
        dc = int(desired_count)
        if dc < 0 or dc > 50:
            raise ValueError("desiredCount_out_of_range")
        kwargs["desiredCount"] = dc
    resp = ecs_client().update_service(**kwargs)
    svc = (resp.get("service") if isinstance(resp, dict) else None) or {}
    return {
        "ok": True,
        "cluster": c,
        "service": s,
        "status": svc.get("status"),
        "desiredCount": svc.get("desiredCount"),
        "runningCount": svc.get("runningCount"),
        "pendingCount": svc.get("pendingCount"),
        "taskDefinition": svc.get("taskDefinition"),
        "deploymentConfiguration": svc.get("deploymentConfiguration"),
    }


def metadata_introspect() -> dict[str, Any]:
    """
    Introspect ECS container metadata from the task metadata endpoint.
    Queries the ECS_CONTAINER_METADATA_URI_V4 endpoint to discover task, cluster, service,
    and environment information about the current container.
    """
    metadata_uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
    if not metadata_uri:
        return {"ok": False, "error": "not_running_in_ecs", "hint": "ECS_CONTAINER_METADATA_URI_V4 not set"}
    
    try:
        base_url = metadata_uri.rstrip("/")
        
        # Fetch task metadata
        task_data: dict[str, Any] | None = None
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{base_url}/task")
                if resp.status_code == 200:
                    task_data = resp.json() if resp.content else None
        except Exception as e:
            log.warning("ecs_metadata_task_failed", error=str(e))
        
        # Fetch container metadata
        container_data: dict[str, Any] | None = None
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{base_url}")
                if resp.status_code == 200:
                    container_data = resp.json() if resp.content else None
        except Exception as e:
            log.warning("ecs_metadata_container_failed", error=str(e))
        
        # Extract relevant fields
        result: dict[str, Any] = {
            "ok": True,
            "metadataUri": metadata_uri,
        }
        
        if task_data and isinstance(task_data, dict):
            # Extract task information (ECS metadata v4 uses camelCase)
            task_arn = task_data.get("TaskARN") or task_data.get("taskARN")
            cluster_arn = task_data.get("Cluster") or task_data.get("cluster")
            family = task_data.get("Family") or task_data.get("family")
            revision = task_data.get("Revision") or task_data.get("revision")
            
            if task_arn:
                result["taskArn"] = str(task_arn)
                # Extract cluster name from ARN if it's an ARN
                if cluster_arn:
                    result["clusterArn"] = str(cluster_arn)
                    # Extract cluster name (last part of ARN after /)
                    if "/" in cluster_arn:
                        result["cluster"] = cluster_arn.split("/")[-1]
                    else:
                        result["cluster"] = cluster_arn
            if family:
                result["taskFamily"] = str(family)
            if revision:
                result["taskRevision"] = str(revision)
            
            # Extract availability zone
            availability_zone = task_data.get("AvailabilityZone") or task_data.get("availabilityZone")
            if availability_zone:
                result["availabilityZone"] = str(availability_zone)
            
            # Extract region from task ARN if available
            if task_arn and "arn:aws:ecs:" in task_arn:
                parts = task_arn.split(":")
                if len(parts) >= 4:
                    result["region"] = parts[3]
        
        if container_data and isinstance(container_data, dict):
            # Extract container-specific info
            container_name = container_data.get("Name") or container_data.get("name")
            container_id = container_data.get("DockerId") or container_data.get("dockerId")
            
            if container_name:
                result["containerName"] = str(container_name)
            if container_id:
                result["containerId"] = str(container_id)
            
            # Note: Environment variables are not directly available via metadata endpoint v4
            # They would need to be checked via task definition or container labels
            # For security, we don't expose env var values here
        
        # Include task definition family:revision if we have both
        if result.get("taskFamily") and result.get("taskRevision"):
            result["taskDefinition"] = f"{result['taskFamily']}:{result['taskRevision']}"
        
        # Suggest log group name based on common patterns
        # Pattern: /ecs/{service-name}-{environment}
        # Try to infer service name from task family (common pattern)
        task_family = result.get("taskFamily")
        if task_family:
            # Common pattern: task family is like "northstar-job-runner-production"
            # Service name might match, or we can use task family as service name
            # Try to extract environment suffix
            env = str(settings.normalized_environment or "").strip() or "production"
            # Check if task family already has environment suffix
            if task_family.endswith(f"-{env}"):
                service_part = task_family[: -(len(env) + 1)]
                suggested_log_group = f"/ecs/{service_part}-{env}"
            else:
                # Use full task family as service name
                suggested_log_group = f"/ecs/{task_family}-{env}"
            
            result["suggestedLogGroup"] = suggested_log_group
            result["hint"] = f"Common log group pattern for this service: {suggested_log_group}. Use logs_discover_for_ecs or logs_list_available to verify."
        
        return result
        
    except Exception as e:
        log.warning("ecs_metadata_introspect_failed", error=str(e))
        return {"ok": False, "error": str(e) or "metadata_request_failed"}

