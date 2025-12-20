from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any

import boto3

from ..observability.logging import get_logger
from ..settings import settings
from .agent_events_repo import append_event
from .change_proposals_repo import get_change_proposal, update_change_proposal
from .github_secrets import get_secret_str as github_secret_str


log = get_logger("self_modify_pipeline")


@dataclass(frozen=True)
class GhResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int


def _allowed_slack_user(user_id: str) -> bool:
    if not user_id:
        return False
    raw = str(settings.self_modify_allowed_slack_user_ids or "").strip()
    if not raw:
        return False
    allowed = {x.strip() for x in raw.split(",") if x.strip()}
    return user_id in allowed


def _run(cmd: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None, timeout_s: int = 180) -> GhResult:
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(5, int(timeout_s)),
            check=False,
            text=True,
        )
        return GhResult(ok=p.returncode == 0, stdout=p.stdout or "", stderr=p.stderr or "", exit_code=int(p.returncode))
    except subprocess.TimeoutExpired as e:
        return GhResult(ok=False, stdout=(e.stdout or "") if isinstance(e.stdout, str) else "", stderr="timeout", exit_code=124)
    except Exception as e:
        return GhResult(ok=False, stdout="", stderr=str(e) or "exec_failed", exit_code=127)


def _github_env() -> dict[str, str]:
    """
    Build env for gh/git calls.
    Expected secret keys (in Secrets Manager JSON):
    - GITHUB_TOKEN (preferred)
    - GH_TOKEN (also supported)
    """
    token = github_secret_str("GITHUB_TOKEN") or github_secret_str("GH_TOKEN") or ""
    env = dict(os.environ)
    if token:
        # gh uses GH_TOKEN (and also respects GITHUB_TOKEN in many contexts).
        env["GH_TOKEN"] = token
        env["GITHUB_TOKEN"] = token
    return env


def open_pr_for_change_proposal(
    *,
    proposal_id: str,
    actor_slack_user_id: str,
    rfp_id: str | None = None,
) -> dict[str, Any]:
    if not bool(settings.self_modify_enabled):
        return {"ok": False, "error": "self_modify_disabled"}
    if not _allowed_slack_user(str(actor_slack_user_id or "").strip()):
        return {"ok": False, "error": "not_authorized"}

    repo = str(settings.github_repo or "").strip()
    base = str(settings.github_base_branch or "main").strip() or "main"
    if not repo:
        return {"ok": False, "error": "missing_GITHUB_REPO"}

    cp = get_change_proposal(proposal_id)
    if not cp:
        return {"ok": False, "error": "change_proposal_not_found"}

    patch = str(cp.get("patch") or "")
    title = str(cp.get("title") or "Change proposal").strip() or "Change proposal"
    body = (str(cp.get("summary") or "").strip() or "Automated change proposal.").strip()

    # Create a branch name deterministically.
    branch = f"agent/cp-{str(proposal_id).strip()}"

    env = _github_env()
    env["GIT_TERMINAL_PROMPT"] = "0"

    # Basic preflight
    gh = _run(["gh", "--version"], env=env, timeout_s=30)
    if not gh.ok:
        return {"ok": False, "error": "gh_not_available", "details": gh.stderr.strip() or gh.stdout.strip()}

    git = _run(["git", "--version"], env=env, timeout_s=30)
    if not git.ok:
        return {"ok": False, "error": "git_not_available", "details": git.stderr.strip() or git.stdout.strip()}

    repo_path_cfg = str(settings.self_modify_repo_path or "").strip()
    tmpdir: tempfile.TemporaryDirectory[str] | None = None
    repo_path = repo_path_cfg
    try:
        if not repo_path:
            tmpdir = tempfile.TemporaryDirectory(prefix="northstar_repo_")
            repo_path = tmpdir.name
            cl = _run(["gh", "repo", "clone", repo, repo_path, "--", "--depth", "1"], env=env, timeout_s=180)
            if not cl.ok:
                return {"ok": False, "error": "gh_repo_clone_failed", "details": cl.stderr.strip()[:1200]}

        # Ensure repo is clean.
        st = _run(["git", "status", "--porcelain"], cwd=repo_path, env=env, timeout_s=30)
        if not st.ok:
            return {"ok": False, "error": "git_status_failed", "details": st.stderr.strip()}
        if (st.stdout or "").strip():
            return {"ok": False, "error": "working_tree_dirty"}

        # Fetch + checkout base
        _run(["git", "fetch", "origin", base], cwd=repo_path, env=env, timeout_s=120)
        co = _run(["git", "checkout", base], cwd=repo_path, env=env, timeout_s=60)
        if not co.ok:
            return {"ok": False, "error": "git_checkout_failed", "details": co.stderr.strip()}
        _run(["git", "reset", "--hard", f"origin/{base}"], cwd=repo_path, env=env, timeout_s=60)

        # Create/reset branch
        _run(["git", "checkout", "-B", branch], cwd=repo_path, env=env, timeout_s=60)

        # Ensure commit identity (repo-local config only).
        _run(["git", "config", "user.email", "northstar@polariseco.com"], cwd=repo_path, env=env, timeout_s=30)
        _run(["git", "config", "user.name", "North Star"], cwd=repo_path, env=env, timeout_s=30)

        # Apply patch
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".patch") as f:
            f.write(patch)
            patch_path = f.name
        try:
            ap = _run(["git", "apply", "--whitespace=nowarn", patch_path], cwd=repo_path, env=env, timeout_s=60)
            if not ap.ok:
                update_change_proposal(proposal_id, {"status": "failed", "error": ap.stderr.strip() or "git_apply_failed"})
                return {"ok": False, "error": "git_apply_failed", "details": ap.stderr.strip()[:1200]}
        finally:
            try:
                os.unlink(patch_path)
            except Exception:
                pass

        # Commit changes (only if there are changes)
        st2 = _run(["git", "status", "--porcelain"], cwd=repo_path, env=env, timeout_s=30)
        if not (st2.stdout or "").strip():
            return {"ok": False, "error": "patch_applied_no_changes"}

        _run(["git", "add", "-A"], cwd=repo_path, env=env, timeout_s=60)
        msg = f"agent: {title} ({proposal_id})"
        cm = _run(["git", "commit", "-m", msg], cwd=repo_path, env=env, timeout_s=60)
        if not cm.ok:
            return {"ok": False, "error": "git_commit_failed", "details": cm.stderr.strip()[:1200]}

        # Push branch
        ps = _run(["git", "push", "-u", "origin", branch], cwd=repo_path, env=env, timeout_s=180)
        if not ps.ok:
            return {"ok": False, "error": "git_push_failed", "details": ps.stderr.strip()[:1200]}

        # Create PR
        pr = _run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repo,
                "--base",
                base,
                "--head",
                branch,
                "--title",
                title,
                "--body",
                body,
            ],
            cwd=repo_path,
            env=env,
            timeout_s=120,
        )
        if not pr.ok:
            return {"ok": False, "error": "gh_pr_create_failed", "details": pr.stderr.strip()[:1200]}

        pr_url = (pr.stdout or "").strip().splitlines()[-1].strip()
        update_change_proposal(proposal_id, {"status": "pr_opened", "prUrl": pr_url})
        try:
            rid = str(rfp_id or cp.get("rfpId") or "").strip()
            if rid:
                append_event(
                    rfp_id=rid,
                    type="self_modify_pr_opened",
                    tool="self_modify_open_pr",
                    payload={"proposalId": proposal_id, "prUrl": pr_url, "repo": repo, "base": base, "branch": branch},
                )
        except Exception:
            pass
        return {"ok": True, "proposalId": proposal_id, "prUrl": pr_url, "branch": branch, "base": base}
    finally:
        try:
            if tmpdir:
                tmpdir.cleanup()
        except Exception:
            pass


def get_pr_checks(*, pr_url_or_number: str) -> dict[str, Any]:
    """
    Fetch check status via gh. Returns a compact summary.
    """
    repo = str(settings.github_repo or "").strip()
    if not repo:
        return {"ok": False, "error": "missing_GITHUB_REPO"}
    env = _github_env()
    ref = str(pr_url_or_number or "").strip()
    if not ref:
        return {"ok": False, "error": "missing_pr_ref"}

    cmd = ["gh", "pr", "view", ref, "--repo", repo, "--json", "number,state,mergeable,reviewDecision,checks,headRefName,baseRefName,url"]
    res = _run(cmd, env=env, timeout_s=60)
    if not res.ok:
        return {"ok": False, "error": "gh_pr_view_failed", "details": res.stderr.strip()[:1200]}
    try:
        data = json.loads(res.stdout)
    except Exception:
        return {"ok": False, "error": "invalid_json"}

    checks = data.get("checks") if isinstance(data, dict) else None
    checks_list = checks if isinstance(checks, list) else []
    counts = {"total": 0, "pass": 0, "fail": 0, "pending": 0}
    for c in checks_list:
        if not isinstance(c, dict):
            continue
        counts["total"] += 1
        st = str(c.get("state") or "").lower()
        if st in ("success", "passed"):
            counts["pass"] += 1
        elif st in ("failure", "failed", "error", "cancelled", "timed_out"):
            counts["fail"] += 1
        else:
            counts["pending"] += 1

    return {
        "ok": True,
        "pr": {
            "number": data.get("number"),
            "state": data.get("state"),
            "mergeable": data.get("mergeable"),
            "reviewDecision": data.get("reviewDecision"),
            "headRefName": data.get("headRefName"),
            "baseRefName": data.get("baseRefName"),
            "url": data.get("url"),
        },
        "checksSummary": counts,
        "checks": checks_list[:50],
    }


def verify_ecs_rollout(*, timeout_s: int = 600, poll_s: int = 10) -> dict[str, Any]:
    """
    Verify ECS service rollout stability (best-effort).
    Requires ECS_CLUSTER and ECS_SERVICE settings and task role permissions.
    """
    cluster = str(settings.ecs_cluster or "").strip()
    service = str(settings.ecs_service or "").strip()
    if not cluster or not service:
        return {"ok": False, "error": "missing_ecs_target"}

    ecs = boto3.client("ecs", region_name=settings.aws_region)
    deadline = time.time() + max(30, min(3600, int(timeout_s or 600)))

    last: dict[str, Any] | None = None
    while time.time() < deadline:
        resp = ecs.describe_services(cluster=cluster, services=[service])
        svcs = resp.get("services") if isinstance(resp, dict) else None
        svc = (svcs or [None])[0] if isinstance(svcs, list) and svcs else None
        if not isinstance(svc, dict):
            return {"ok": False, "error": "service_not_found"}
        last = svc

        deployments = svc.get("deployments") if isinstance(svc.get("deployments"), list) else []
        primary = None
        for d in deployments:
            if isinstance(d, dict) and str(d.get("status") or "").upper() == "PRIMARY":
                primary = d
                break

        desired = int(svc.get("desiredCount") or 0)
        running = int(svc.get("runningCount") or 0)
        rollout_state = str((primary or {}).get("rolloutState") or "").upper()

        stable = (
            desired == running
            and rollout_state in ("COMPLETED", "")
            and len([d for d in deployments if isinstance(d, dict)]) <= 1
        )
        if stable:
            return {
                "ok": True,
                "cluster": cluster,
                "service": service,
                "desiredCount": desired,
                "runningCount": running,
                "rolloutState": rollout_state or None,
                "serviceArn": svc.get("serviceArn"),
            }

        time.sleep(max(2, min(30, int(poll_s or 10))))

    # Timed out
    return {
        "ok": False,
        "error": "timeout",
        "cluster": cluster,
        "service": service,
        "last": {
            "desiredCount": int((last or {}).get("desiredCount") or 0) if isinstance(last, dict) else None,
            "runningCount": int((last or {}).get("runningCount") or 0) if isinstance(last, dict) else None,
            "deployments": (last or {}).get("deployments") if isinstance(last, dict) else None,
        },
    }

