from __future__ import annotations

from typing import Any

import httpx

from ...settings import settings
from ..github_secrets import get_secret_str as github_secret_str
from .allowlist import parse_csv, uniq


def _allowed_repos() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_github_repos))
    if explicit:
        return explicit
    repo = str(settings.github_repo or "").strip()
    return uniq([repo]) if repo else []


def _require_allowed_repo(repo: str | None) -> str:
    r = str(repo or "").strip() or str(settings.github_repo or "").strip()
    if not r:
        raise ValueError("missing_repo")
    allowed = [x for x in _allowed_repos() if x]
    if allowed and r not in allowed:
        raise ValueError("repo_not_allowed")
    return r


def _token() -> str:
    tok = github_secret_str("GITHUB_TOKEN") or github_secret_str("GH_TOKEN") or ""
    return str(tok or "").strip()


def _client() -> httpx.Client:
    return httpx.Client(timeout=20.0, follow_redirects=True)


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "polaris-rfp-agent",
    }
    tok = _token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _split_repo(repo: str) -> tuple[str, str]:
    r = str(repo or "").strip()
    if "/" not in r:
        raise ValueError("invalid_repo")
    owner, name = r.split("/", 1)
    owner = owner.strip()
    name = name.strip()
    if not owner or not name:
        raise ValueError("invalid_repo")
    return owner, name


def _get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with _client() as c:
        resp = c.get(url, headers=_headers(), params=params or {})
        data = resp.json() if resp.content else {}
        if not isinstance(data, (dict, list)):
            return {"ok": False, "error": "invalid_response", "status": resp.status_code}
        if resp.status_code >= 400:
            # GitHub uses `message`/`documentation_url`.
            if isinstance(data, dict):
                return {"ok": False, "status": resp.status_code, "error": data.get("message") or "github_error", "details": data}
            return {"ok": False, "status": resp.status_code, "error": "github_error"}
        return {"ok": True, "data": data}


def _post(url: str, json_body: dict[str, Any]) -> dict[str, Any]:
    with _client() as c:
        resp = c.post(url, headers=_headers(), json=json_body or {})
        data = resp.json() if resp.content else {}
        if not isinstance(data, (dict, list)):
            return {"ok": False, "error": "invalid_response", "status": resp.status_code}
        if resp.status_code >= 400:
            if isinstance(data, dict):
                return {"ok": False, "status": resp.status_code, "error": data.get("message") or "github_error", "details": data}
            return {"ok": False, "status": resp.status_code, "error": "github_error"}
        return {"ok": True, "data": data}


def _post_allow_empty(url: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    with _client() as c:
        resp = c.post(url, headers=_headers(), json=json_body or {})
        if resp.status_code in (200, 201, 202, 204) and not resp.content:
            return {"ok": True, "data": {}}
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            if isinstance(data, dict):
                return {"ok": False, "status": resp.status_code, "error": data.get("message") or "github_error", "details": data}
            return {"ok": False, "status": resp.status_code, "error": "github_error"}
        return {"ok": True, "data": data}


def get_pull(*, repo: str | None, number: int) -> dict[str, Any]:
    r = _require_allowed_repo(repo)
    owner, name = _split_repo(r)
    n = int(number)
    res = _get(f"https://api.github.com/repos/{owner}/{name}/pulls/{n}")
    if not res.get("ok"):
        return res
    pr = res.get("data")
    if not isinstance(pr, dict):
        return {"ok": False, "error": "invalid_response"}
    return {
        "ok": True,
        "repo": r,
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": pr.get("state"),
        "draft": pr.get("draft"),
        "merged": pr.get("merged"),
        "mergeable": pr.get("mergeable"),
        "user": (pr.get("user") or {}).get("login") if isinstance(pr.get("user"), dict) else None,
        "url": pr.get("html_url"),
        "base": (pr.get("base") or {}).get("ref") if isinstance(pr.get("base"), dict) else None,
        "head": (pr.get("head") or {}).get("ref") if isinstance(pr.get("head"), dict) else None,
        "headSha": (pr.get("head") or {}).get("sha") if isinstance(pr.get("head"), dict) else None,
        "labels": [x.get("name") for x in (pr.get("labels") or []) if isinstance(x, dict) and x.get("name")][:25],
        "updatedAt": pr.get("updated_at"),
    }


def list_pulls(*, repo: str | None, state: str = "open", limit: int = 10) -> dict[str, Any]:
    r = _require_allowed_repo(repo)
    owner, name = _split_repo(r)
    st = str(state or "open").strip().lower()
    if st not in ("open", "closed", "all"):
        st = "open"
    lim = max(1, min(25, int(limit or 10)))
    res = _get(
        f"https://api.github.com/repos/{owner}/{name}/pulls",
        params={"state": st, "per_page": lim, "sort": "updated", "direction": "desc"},
    )
    if not res.get("ok"):
        return res
    rows = res.get("data")
    prs = rows if isinstance(rows, list) else []
    out: list[dict[str, Any]] = []
    for pr in prs[:lim]:
        if not isinstance(pr, dict):
            continue
        out.append(
            {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "draft": pr.get("draft"),
                "url": pr.get("html_url"),
                "user": (pr.get("user") or {}).get("login") if isinstance(pr.get("user"), dict) else None,
                "updatedAt": pr.get("updated_at"),
            }
        )
    return {"ok": True, "repo": r, "state": st, "pulls": out}


def list_check_runs(*, repo: str | None, ref: str, filter: str = "latest") -> dict[str, Any]:
    r = _require_allowed_repo(repo)
    owner, name = _split_repo(r)
    rf = str(ref or "").strip()
    if not rf:
        return {"ok": False, "error": "missing_ref"}
    flt = str(filter or "latest").strip().lower()
    if flt not in ("latest", "all"):
        flt = "latest"
    res = _get(
        f"https://api.github.com/repos/{owner}/{name}/commits/{rf}/check-runs",
        params={"filter": flt, "per_page": 50},
    )
    if not res.get("ok"):
        return res
    data = res.get("data")
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_response"}
    runs = data.get("check_runs")
    rows = runs if isinstance(runs, list) else []
    out: list[dict[str, Any]] = []
    for cr in rows[:25]:
        if not isinstance(cr, dict):
            continue
        out.append(
            {
                "name": cr.get("name"),
                "status": cr.get("status"),
                "conclusion": cr.get("conclusion"),
                "startedAt": cr.get("started_at"),
                "completedAt": cr.get("completed_at"),
                "url": cr.get("html_url"),
            }
        )
    return {"ok": True, "repo": r, "ref": rf, "checkRuns": out}


def create_issue(*, repo: str | None, title: str, body: str | None = None) -> dict[str, Any]:
    r = _require_allowed_repo(repo)
    owner, name = _split_repo(r)
    t = str(title or "").strip()
    if not t:
        return {"ok": False, "error": "missing_title"}
    b = str(body or "").strip() or None
    payload: dict[str, Any] = {"title": t[:240]}
    if b:
        payload["body"] = b[:4000]
    res = _post(f"https://api.github.com/repos/{owner}/{name}/issues", json_body=payload)
    if not res.get("ok"):
        return res
    it = res.get("data")
    if not isinstance(it, dict):
        return {"ok": False, "error": "invalid_response"}
    return {"ok": True, "repo": r, "number": it.get("number"), "url": it.get("html_url"), "title": it.get("title")}


def comment_on_issue_or_pr(*, repo: str | None, number: int, body: str) -> dict[str, Any]:
    r = _require_allowed_repo(repo)
    owner, name = _split_repo(r)
    n = int(number)
    if n <= 0:
        return {"ok": False, "error": "missing_number"}
    b = str(body or "").strip()
    if not b:
        return {"ok": False, "error": "missing_body"}
    res = _post(
        f"https://api.github.com/repos/{owner}/{name}/issues/{n}/comments",
        json_body={"body": b[:4000]},
    )
    if not res.get("ok"):
        return res
    it = res.get("data")
    if not isinstance(it, dict):
        return {"ok": False, "error": "invalid_response"}
    return {"ok": True, "repo": r, "number": n, "commentUrl": it.get("html_url")}


def add_labels(*, repo: str | None, number: int, labels: list[str]) -> dict[str, Any]:
    r = _require_allowed_repo(repo)
    owner, name = _split_repo(r)
    n = int(number)
    if n <= 0:
        return {"ok": False, "error": "missing_number"}
    labs = [str(x).strip() for x in (labels or []) if str(x).strip()][:25]
    if not labs:
        return {"ok": False, "error": "missing_labels"}
    res = _post(f"https://api.github.com/repos/{owner}/{name}/issues/{n}/labels", json_body={"labels": labs})
    if not res.get("ok"):
        return res
    return {"ok": True, "repo": r, "number": n, "labels": labs}


def rerun_workflow_run(*, repo: str | None, run_id: int) -> dict[str, Any]:
    r = _require_allowed_repo(repo)
    owner, name = _split_repo(r)
    rid = int(run_id)
    if rid <= 0:
        return {"ok": False, "error": "missing_runId"}
    res = _post_allow_empty(f"https://api.github.com/repos/{owner}/{name}/actions/runs/{rid}/rerun", json_body={})
    if not res.get("ok"):
        return res
    return {"ok": True, "repo": r, "runId": rid}


def dispatch_workflow(
    *,
    repo: str | None,
    workflow: str,
    ref: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    r = _require_allowed_repo(repo)
    owner, name = _split_repo(r)
    wf = str(workflow or "").strip()
    rf = str(ref or "").strip()
    if not wf:
        return {"ok": False, "error": "missing_workflow"}
    if not rf:
        return {"ok": False, "error": "missing_ref"}
    payload: dict[str, Any] = {"ref": rf}
    if isinstance(inputs, dict) and inputs:
        payload["inputs"] = {str(k)[:50]: str(v)[:200] for k, v in list(inputs.items())[:20]}
    res = _post_allow_empty(f"https://api.github.com/repos/{owner}/{name}/actions/workflows/{wf}/dispatches", json_body=payload)
    if not res.get("ok"):
        return res
    return {"ok": True, "repo": r, "workflow": wf, "ref": rf}

