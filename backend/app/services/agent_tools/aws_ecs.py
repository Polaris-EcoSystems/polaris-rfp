from __future__ import annotations

from typing import Any

from ...settings import settings
from .allowlist import parse_csv, uniq
from .aws_clients import ecs_client


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
                "message": str(e.get("message") or "")[:400] if isinstance(e, dict) else "",
            }
            for e in (sv.get("events") if isinstance(sv.get("events"), list) else [])[:8]
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

