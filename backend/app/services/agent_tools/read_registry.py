from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from boto3.dynamodb.conditions import Key
import docx2txt
from pypdf import PdfReader

from ...ai.context import clip_text, normalize_ws
from ...db.dynamodb.table import get_main_table, get_table
from ...settings import settings
from .. import content_repo
from ..proposals_repo import get_proposal_by_id, list_proposals
from ..rfps_repo import get_rfp_by_id, list_rfps
from ..s3_assets import get_object_bytes
from ..s3_assets import get_object_text as s3_get_object_text
from ..s3_assets import list_objects as s3_list_objects
from ..s3_assets import presign_get_object as s3_presign_get_object
from ..skills_repo import get_skill_index as skills_get_index
from ..skills_repo import search_skills as skills_search_index
from ..skills_store import get_skill_body_text as skills_get_body_text
from ..tenant_memory_repo import list_blocks as tenant_memory_list
from ..user_memory_repo import list_blocks as user_memory_list
from ..workflow_tasks_repo import list_tasks_for_rfp
from ..agent_memory_tools import get_memory_tools
from .external_context_tools import EXTERNAL_CONTEXT_TOOLS
from .allowlist import parse_csv, uniq, is_allowed_prefix
from .aws_cognito import admin_get_user as cognito_admin_get_user
from .aws_cognito import describe_user_pool as cognito_describe_user_pool
from .aws_cognito import list_users as cognito_list_users
from .aws_ecs import describe_service as ecs_describe_service
from .aws_ecs import describe_task_definition as ecs_describe_task_definition
from .aws_ecs import list_tasks as ecs_list_tasks
from .aws_logs import tail_log_group as logs_tail
from .aws_logs_insights import search_logs as telemetry_search_logs
from .aws_logs_insights import top_errors as telemetry_top_errors
from .aws_s3 import head_object as s3_head_object
from .aws_s3 import presign_put_object as s3_presign_put_object
from .aws_secrets import describe_secret as secrets_describe_secret
from .aws_sqs import get_queue_attributes as sqs_get_queue_attributes
from .aws_sqs import get_queue_depth as sqs_get_queue_depth
from .aws_dynamodb import describe_table as dynamodb_describe_table
from .aws_dynamodb import list_tables as dynamodb_list_tables
from ..browser_worker_client import (
    click as bw_click,
    close as bw_close,
    extract as bw_extract,
    goto as bw_goto,
    new_context as bw_new_context,
    new_page as bw_new_page,
    trace_start as bw_trace_start,
    trace_stop as bw_trace_stop,
    screenshot as bw_screenshot,
    type_text as bw_type_text,
    wait_for as bw_wait_for,
)
from .github_api import get_pull as github_get_pull
from .github_api import list_check_runs as github_list_check_runs
from .github_api import list_pulls as github_list_pulls
from .slack_read import create_canvas as slack_create_canvas
from .slack_read import get_thread as slack_get_thread
from .slack_read import list_recent_messages as slack_list_recent_messages


ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


def tool_def(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": parameters,
    }


def _frontend_url(path: str) -> str:
    base = str(settings.frontend_base_url or "").rstrip("/")
    p = str(path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    return base + p


def _rfp_url(rfp_id: str) -> str:
    return _frontend_url(f"/rfps/{str(rfp_id or '').strip()}")


def _proposal_url(pid: str) -> str:
    return _frontend_url(f"/proposals/{str(pid or '').strip()}")


def _safe_json(obj: Any, *, max_chars: int = 25_000) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = json.dumps({"ok": False, "error": "serialization_failed"})
    return clip_text(s, max_chars=max_chars)


def _slim_value(v: Any, *, depth: int = 0, max_depth: int = 3) -> Any:
    """
    Best-effort payload slimming for tool outputs.
    Prevents huge DynamoDB/S3 blobs from flooding the model context.
    """
    if depth >= max_depth:
        if isinstance(v, str):
            return clip_text(v, max_chars=600)
        if isinstance(v, (int, float, bool)) or v is None:
            return v
        return str(type(v).__name__)
    if isinstance(v, str):
        return clip_text(v, max_chars=1800)
    if isinstance(v, bytes):
        return f"<bytes:{len(v)}>"
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        out: list[Any] = []
        for it in v[:30]:
            out.append(_slim_value(it, depth=depth + 1, max_depth=max_depth))
        if len(v) > 30:
            out.append(f"<truncated:{len(v) - 30}>")
        return out
    if isinstance(v, dict):
        out2: dict[str, Any] = {}
        keys = list(v.keys())
        try:
            keys = sorted(keys, key=lambda x: str(x))
        except Exception:
            pass
        for k in keys[:60]:
            kk = str(k)
            if kk in ("rawText", "text", "content", "body", "html"):
                out2[kk] = clip_text(str(v.get(k) or ""), max_chars=1200)
                continue
            out2[kk] = _slim_value(v.get(k), depth=depth + 1, max_depth=max_depth)
        if len(keys) > 60:
            out2["_truncatedKeys"] = len(keys) - 60
        return out2
    return clip_text(str(v), max_chars=600)


def _slim_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    out = _slim_value(item, depth=0, max_depth=3)
    return out if isinstance(out, dict) else None


def _allowed_ddb_tables() -> list[str]:
    """
    Constrain raw DynamoDB inspection to known app tables only.
    """
    names: list[str] = []
    for v in (settings.ddb_table_name, settings.magic_link_table_name):
        s = str(v or "").strip()
        if s:
            names.append(s)
    out: list[str] = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


def _resolve_ddb_table(table_name: str | None):
    t = str(table_name or "").strip() or (str(settings.ddb_table_name or "").strip() or None)
    if not t:
        # Preserve existing failure mode for missing configuration.
        return get_main_table()
    allowed = _allowed_ddb_tables()
    if allowed and t not in allowed:
        raise ValueError(f"table_not_allowed: {t}")
    return get_table(t)


def _allowed_s3_prefixes() -> list[str]:
    """
    Prefix allowlist for the assets bucket.
    Defaults are derived from the app's key namespaces + CloudFormation.
    """
    explicit = uniq(parse_csv(settings.agent_allowed_s3_prefixes))
    if explicit:
        return explicit
    # Default allowlist (keep narrow; expand via env var if needed).
    return ["rfp/", "team/", "contracting/", "agent/"]


def _require_allowed_s3_key(key: str) -> str:
    k = str(key or "").strip()
    if not k:
        raise ValueError("missing_key")
    allowed = _allowed_s3_prefixes()
    if allowed and not is_allowed_prefix(k, allowed):
        raise ValueError("s3_key_not_allowed")
    return k


def _require_allowed_s3_prefix(prefix: str) -> str:
    p = str(prefix or "").strip()
    if not p:
        raise ValueError("missing_prefix")
    allowed = _allowed_s3_prefixes()
    if allowed and not is_allowed_prefix(p, allowed):
        raise ValueError("s3_prefix_not_allowed")
    return p


def _tenant_id_default(email_domain: str | None = None) -> str:
    # Prefer explicit domain if provided, else fall back to app-wide allowed domain.
    dom = str(email_domain or "").strip().lower()
    if dom and "@" in dom:
        dom = dom.split("@", 1)[1].strip().lower()
    return dom or str(getattr(settings, "allowed_email_domain", "") or "").strip().lower() or "default"


def _clip_block(block: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    b = dict(block or {})
    content = str(b.get("content") or "")
    if len(content) > max_chars:
        b["content"] = content[:max_chars] + "…"
        b["contentTruncated"] = True
    else:
        b["contentTruncated"] = False
    return b


def _user_memory_load_tool(args: dict[str, Any]) -> dict[str, Any]:
    user_sub = str(args.get("userSub") or "").strip()
    if not user_sub:
        return {"ok": False, "error": "missing_userSub"}
    limit = max(1, min(50, int(args.get("limit") or 25)))
    max_chars = max(500, min(20_000, int(args.get("maxChars") or 5000)))
    try:
        blocks = user_memory_list(user_sub=user_sub, limit=limit)
        slim = [_clip_block(b, max_chars=max_chars) for b in blocks[:limit] if isinstance(b, dict)]
        return {"ok": True, "userSub": user_sub, "blocks": slim}
    except Exception as e:
        return {"ok": False, "error": str(e) or "user_memory_load_failed"}


def _tenant_memory_load_tool(args: dict[str, Any]) -> dict[str, Any]:
    tenant_id = str(args.get("tenantId") or "").strip().lower() or None
    email_domain = str(args.get("emailDomain") or "").strip().lower() or None
    tid = tenant_id or _tenant_id_default(email_domain)
    limit = max(1, min(50, int(args.get("limit") or 25)))
    max_chars = max(500, min(20_000, int(args.get("maxChars") or 5000)))
    try:
        blocks = tenant_memory_list(tenant_id=tid, limit=limit)
        slim = [_clip_block(b, max_chars=max_chars) for b in blocks[:limit] if isinstance(b, dict)]
        return {"ok": True, "tenantId": tid, "blocks": slim}
    except Exception as e:
        return {"ok": False, "error": str(e) or "tenant_memory_load_failed"}


def _memory_search_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = normalize_ws(str(args.get("query") or ""), max_chars=200)
    if not q:
        return {"ok": False, "error": "missing_query"}
    ql = q.lower()
    limit = max(1, min(25, int(args.get("limit") or 10)))
    # Scope
    user_sub = str(args.get("userSub") or "").strip() or None
    tenant_id = str(args.get("tenantId") or "").strip().lower() or None
    email_domain = str(args.get("emailDomain") or "").strip().lower() or None
    tid = tenant_id or (_tenant_id_default(email_domain) if (tenant_id is None) else tenant_id)

    hits: list[dict[str, Any]] = []

    def _search_blocks(blocks: list[dict[str, Any]], *, scope: str) -> None:
        nonlocal hits
        for b in blocks:
            if not isinstance(b, dict):
                continue
            title = str(b.get("title") or "")
            content = str(b.get("content") or "")
            hay = (title + "\n" + content).lower()
            if ql not in hay:
                continue
            # Snippet
            idx = hay.find(ql)
            start = max(0, idx - 80)
            end = min(len(content), idx + 220)
            snippet = content[start:end].strip()
            hits.append(
                {
                    "scope": scope,
                    "blockId": b.get("blockId"),
                    "title": title[:240],
                    "snippet": (snippet[:400] + "…") if len(snippet) > 400 else snippet,
                }
            )
            if len(hits) >= limit:
                return

    try:
        if user_sub:
            _search_blocks(user_memory_list(user_sub=user_sub, limit=50), scope="user")
        if len(hits) < limit and tid:
            _search_blocks(tenant_memory_list(tenant_id=tid, limit=50), scope="tenant")
    except Exception as e:
        return {"ok": False, "error": str(e) or "memory_search_failed"}

    return {"ok": True, "query": q, "hits": hits[:limit]}


# --- Skills tools (SkillIndex in Dynamo + SkillBody in S3) ---


def _skills_search_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = normalize_ws(str(args.get("query") or ""), max_chars=200) or None
    tags = args.get("tags") if isinstance(args.get("tags"), list) else None
    limit = int(args.get("limit") or 10)
    next_token = str(args.get("nextToken") or "").strip() or None
    try:
        return skills_search_index(query=q, tags=tags, limit=limit, next_token=next_token)
    except Exception as e:
        return {"ok": False, "error": str(e) or "skills_search_failed"}


def _skills_get_tool(args: dict[str, Any]) -> dict[str, Any]:
    sid = str(args.get("skillId") or "").strip()
    if not sid:
        return {"ok": False, "error": "missing_skillId"}
    try:
        sk = skills_get_index(skill_id=sid)
        if not sk:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "skill": sk}
    except Exception as e:
        return {"ok": False, "error": str(e) or "skills_get_failed"}


def _skills_load_tool(args: dict[str, Any]) -> dict[str, Any]:
    sid = str(args.get("skillId") or "").strip()
    if not sid:
        return {"ok": False, "error": "missing_skillId"}
    max_chars = max(2000, min(50_000, int(args.get("maxChars") or 20_000)))
    try:
        sk = skills_get_index(skill_id=sid)
        if not sk:
            return {"ok": False, "error": "not_found"}
        s3_key = str(sk.get("s3Key") or "").strip()
        if not s3_key:
            return {"ok": False, "error": "skill_missing_s3Key"}
        # Enforce S3 prefix allowlist before loading.
        _require_allowed_s3_key(s3_key)
        body = skills_get_body_text(key=s3_key, max_bytes=2 * 1024 * 1024, max_chars=max_chars)
        if not body.get("ok"):
            return body
        return {"ok": True, "skill": sk, "body": body.get("text")}
    except Exception as e:
        return {"ok": False, "error": str(e) or "skills_load_failed"}


# --- Browser worker tools (Playwright) ---


def _browser_new_context_tool(args: dict[str, Any]) -> dict[str, Any]:
    ua = str(args.get("userAgent") or "").strip() or None
    vw = args.get("viewportWidth")
    vh = args.get("viewportHeight")
    try:
        return bw_new_context(user_agent=ua, viewport_width=int(vw) if vw is not None else None, viewport_height=int(vh) if vh is not None else None)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_new_context_failed"}


def _browser_new_page_tool(args: dict[str, Any]) -> dict[str, Any]:
    cid = str(args.get("contextId") or "").strip()
    try:
        return bw_new_page(context_id=cid)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_new_page_failed"}


def _browser_goto_tool(args: dict[str, Any]) -> dict[str, Any]:
    pid = str(args.get("pageId") or "").strip()
    url = str(args.get("url") or "").strip()
    wait_until = str(args.get("waitUntil") or "").strip() or None
    timeout_ms = args.get("timeoutMs")
    try:
        return bw_goto(page_id=pid, url=url, wait_until=wait_until, timeout_ms=int(timeout_ms) if timeout_ms is not None else None)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_goto_failed"}


def _browser_click_tool(args: dict[str, Any]) -> dict[str, Any]:
    pid = str(args.get("pageId") or "").strip()
    sel = str(args.get("selector") or "").strip()
    timeout_ms = args.get("timeoutMs")
    try:
        return bw_click(page_id=pid, selector=sel, timeout_ms=int(timeout_ms) if timeout_ms is not None else None)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_click_failed"}


def _browser_type_tool(args: dict[str, Any]) -> dict[str, Any]:
    pid = str(args.get("pageId") or "").strip()
    sel = str(args.get("selector") or "").strip()
    txt = str(args.get("text") or "")
    clear_first = bool(args.get("clearFirst") is True)
    timeout_ms = args.get("timeoutMs")
    try:
        return bw_type_text(page_id=pid, selector=sel, text=txt, clear_first=clear_first, timeout_ms=int(timeout_ms) if timeout_ms is not None else None)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_type_failed"}


def _browser_wait_for_tool(args: dict[str, Any]) -> dict[str, Any]:
    pid = str(args.get("pageId") or "").strip()
    sel = str(args.get("selector") or "").strip() or None
    text = str(args.get("text") or "").strip() or None
    timeout_ms = args.get("timeoutMs")
    try:
        return bw_wait_for(page_id=pid, selector=sel, text=text, timeout_ms=int(timeout_ms) if timeout_ms is not None else None)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_wait_for_failed"}


def _browser_extract_tool(args: dict[str, Any]) -> dict[str, Any]:
    pid = str(args.get("pageId") or "").strip()
    sel = str(args.get("selector") or "").strip()
    mode = str(args.get("mode") or "").strip() or None
    attr = str(args.get("attribute") or "").strip() or None
    try:
        return bw_extract(page_id=pid, selector=sel, mode=mode, attribute=attr)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_extract_failed"}


def _browser_screenshot_tool(args: dict[str, Any]) -> dict[str, Any]:
    pid = str(args.get("pageId") or "").strip()
    full_page = bool(args.get("fullPage") is True)
    name = str(args.get("name") or "").strip() or None
    try:
        return bw_screenshot(page_id=pid, full_page=full_page, name=name)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_screenshot_failed"}


def _browser_close_tool(args: dict[str, Any]) -> dict[str, Any]:
    cid = str(args.get("contextId") or "").strip() or None
    pid = str(args.get("pageId") or "").strip() or None
    try:
        return bw_close(context_id=cid, page_id=pid)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_close_failed"}


def _browser_trace_start_tool(args: dict[str, Any]) -> dict[str, Any]:
    cid = str(args.get("contextId") or "").strip()
    screenshots = bool(args.get("screenshots") is True)
    snapshots = bool(args.get("snapshots") is True)
    sources = bool(args.get("sources") is True)
    try:
        return bw_trace_start(context_id=cid, screenshots=screenshots, snapshots=snapshots, sources=sources)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_trace_start_failed"}


def _browser_trace_stop_tool(args: dict[str, Any]) -> dict[str, Any]:
    cid = str(args.get("contextId") or "").strip()
    name = str(args.get("name") or "").strip() or None
    try:
        return bw_trace_stop(context_id=cid, name=name)
    except Exception as e:
        return {"ok": False, "error": str(e) or "browser_trace_stop_failed"}


# --- Telemetry tools (CloudWatch Logs Insights, bounded) ---


def _telemetry_search_logs_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = normalize_ws(str(args.get("query") or ""), max_chars=2000)
    groups = args.get("logGroupNames") if isinstance(args.get("logGroupNames"), list) else None
    since = str(args.get("sinceIso") or "").strip() or None
    until = str(args.get("untilIso") or "").strip() or None
    limit = int(args.get("limit") or 50)
    try:
        return telemetry_search_logs(query=q, log_group_names=groups, since_iso=since, until_iso=until, limit=limit, timeout_s=15)
    except Exception as e:
        return {"ok": False, "error": str(e) or "telemetry_search_logs_failed"}


def _telemetry_top_errors_tool(args: dict[str, Any]) -> dict[str, Any]:
    lg = str(args.get("logGroupName") or "").strip()
    lookback = int(args.get("lookbackMinutes") or 60)
    limit = int(args.get("limit") or 10)
    try:
        return telemetry_top_errors(log_group_name=lg, lookback_minutes=lookback, limit=limit)
    except Exception as e:
        return {"ok": False, "error": str(e) or "telemetry_top_errors_failed"}


def _dynamodb_describe_table_tool(args: dict[str, Any]) -> dict[str, Any]:
    tn = str(args.get("tableName") or "").strip()
    if not tn:
        return {"ok": False, "error": "missing_tableName"}
    try:
        return dynamodb_describe_table(table_name=tn)
    except Exception as e:
        return {"ok": False, "error": str(e) or "dynamodb_describe_table_failed"}


def _dynamodb_list_tables_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 20)
    try:
        return dynamodb_list_tables(limit=limit)
    except Exception as e:
        return {"ok": False, "error": str(e) or "dynamodb_list_tables_failed"}


def _s3_head_object_tool(args: dict[str, Any]) -> dict[str, Any]:
    k = str(args.get("key") or "").strip()
    if not k:
        return {"ok": False, "error": "missing_key"}
    try:
        return s3_head_object(key=k)
    except Exception as e:
        return {"ok": False, "error": str(e) or "s3_head_object_failed"}


def _s3_presign_put_tool(args: dict[str, Any]) -> dict[str, Any]:
    k = str(args.get("key") or "").strip()
    ct = str(args.get("contentType") or "").strip() or None
    exp = int(args.get("expiresIn") or 900)
    if not k:
        return {"ok": False, "error": "missing_key"}
    try:
        return s3_presign_put_object(key=k, content_type=ct, expires_in=exp)
    except Exception as e:
        return {"ok": False, "error": str(e) or "s3_presign_put_failed"}


def _slack_list_recent_messages_tool(args: dict[str, Any]) -> dict[str, Any]:
    ch = str(args.get("channel") or "").strip()
    limit = int(args.get("limit") or 15)
    try:
        return slack_list_recent_messages(channel=ch, limit=limit)
    except Exception as e:
        return {"ok": False, "error": str(e) or "slack_list_recent_messages_failed"}


def _slack_get_thread_tool(args: dict[str, Any]) -> dict[str, Any]:
    ch = str(args.get("channel") or "").strip()
    ts = str(args.get("threadTs") or "").strip()
    limit = int(args.get("limit") or 25)
    try:
        return slack_get_thread(channel=ch, thread_ts=ts, limit=limit)
    except Exception as e:
        return {"ok": False, "error": str(e) or "slack_get_thread_failed"}


def _slack_create_canvas_tool(args: dict[str, Any]) -> dict[str, Any]:
    ch = str(args.get("channel") or "").strip()
    title = str(args.get("title") or "").strip()
    markdown = str(args.get("markdown") or "").strip()
    try:
        return slack_create_canvas(channel=ch, title=title, markdown=markdown)
    except Exception as e:
        return {"ok": False, "error": str(e) or "slack_create_canvas_failed"}


# --- Existing platform browsing tools ---


def _list_rfps_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 10)
    limit = max(1, min(25, limit))
    resp = list_rfps(page=1, limit=limit, next_token=None)
    data = resp.get("data") if isinstance(resp, dict) else None
    rows = data if isinstance(data, list) else []
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("_id") or r.get("rfpId") or "").strip()
        out.append(
            {
                "rfpId": rid,
                "title": str(r.get("title") or "RFP").strip(),
                "clientName": str(r.get("clientName") or "").strip(),
                "projectType": str(r.get("projectType") or "").strip(),
                "submissionDeadline": str(r.get("submissionDeadline") or "").strip(),
                "fitScore": r.get("fitScore"),
                "url": _rfp_url(rid) if rid else None,
            }
        )
    return {"ok": True, "data": out}


def _search_rfps_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = normalize_ws(str(args.get("query") or ""), max_chars=400)
    if not q:
        return {"ok": False, "error": "missing_query"}
    limit = int(args.get("limit") or 10)
    limit = max(1, min(15, limit))
    resp = list_rfps(page=1, limit=200, next_token=None)
    rows = (resp or {}).get("data") if isinstance(resp, dict) else None
    data = rows if isinstance(rows, list) else []
    hits: list[dict[str, Any]] = []
    ql = q.lower()
    for r in data:
        if not isinstance(r, dict):
            continue
        hay = f"{r.get('title') or ''} {r.get('clientName') or ''} {r.get('projectType') or ''}".lower()
        if ql in hay:
            rid = str(r.get("_id") or r.get("rfpId") or "").strip()
            hits.append(
                {
                    "rfpId": rid,
                    "title": str(r.get("title") or "RFP").strip(),
                    "clientName": str(r.get("clientName") or "").strip(),
                    "projectType": str(r.get("projectType") or "").strip(),
                    "submissionDeadline": str(r.get("submissionDeadline") or "").strip(),
                    "url": _rfp_url(rid) if rid else None,
                }
            )
        if len(hits) >= limit:
            break
    return {"ok": True, "query": q, "data": hits}


def _get_rfp_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    r = get_rfp_by_id(rid)
    if not r:
        return {"ok": False, "error": "not_found"}
    raw = str(r.get("rawText") or "")
    r2 = dict(r)
    r2["rawText"] = clip_text(raw, max_chars=9000)
    r2["url"] = _rfp_url(rid)
    return {"ok": True, "rfp": r2}


def _list_proposals_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 10)
    limit = max(1, min(25, limit))
    resp = list_proposals(page=1, limit=limit, next_token=None)
    rows = (resp or {}).get("data") if isinstance(resp, dict) else None
    data = rows if isinstance(rows, list) else []
    out: list[dict[str, Any]] = []
    for p in data[:limit]:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("_id") or p.get("proposalId") or "").strip()
        out.append(
            {
                "proposalId": pid,
                "title": str(p.get("title") or "Proposal").strip(),
                "status": str(p.get("status") or "").strip(),
                "rfpId": str(p.get("rfpId") or "").strip(),
                "url": _proposal_url(pid) if pid else None,
            }
        )
    return {"ok": True, "data": out}


def _search_proposals_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = normalize_ws(str(args.get("query") or ""), max_chars=400)
    if not q:
        return {"ok": False, "error": "missing_query"}
    limit = int(args.get("limit") or 10)
    limit = max(1, min(15, limit))
    resp = list_proposals(page=1, limit=200, next_token=None)
    rows = (resp or {}).get("data") if isinstance(resp, dict) else None
    data = rows if isinstance(rows, list) else []
    hits: list[dict[str, Any]] = []
    ql = q.lower()
    for p in data:
        if not isinstance(p, dict):
            continue
        hay = f"{p.get('title') or ''} {p.get('status') or ''} {p.get('rfpId') or ''}".lower()
        if ql in hay:
            pid = str(p.get("_id") or p.get("proposalId") or "").strip()
            hits.append(
                {
                    "proposalId": pid,
                    "title": str(p.get("title") or "Proposal").strip(),
                    "status": str(p.get("status") or "").strip(),
                    "rfpId": str(p.get("rfpId") or "").strip(),
                    "url": _proposal_url(pid) if pid else None,
                }
            )
        if len(hits) >= limit:
            break
    return {"ok": True, "query": q, "data": hits}


def _get_proposal_tool(args: dict[str, Any]) -> dict[str, Any]:
    pid = str(args.get("proposalId") or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_proposalId"}
    p = get_proposal_by_id(pid, include_sections=True)
    if not p:
        return {"ok": False, "error": "not_found"}
    p2 = dict(p)
    secs = p2.get("sections")
    if isinstance(secs, dict):
        slim: dict[str, Any] = {}
        for k, v in list(secs.items())[:80]:
            if isinstance(v, dict):
                c = v.get("content")
                slim[str(k)] = {
                    **{kk: vv for kk, vv in v.items() if kk != "content"},
                    "contentPreview": clip_text(str(c or ""), max_chars=700),
                }
            else:
                slim[str(k)] = {"contentPreview": clip_text(str(v or ""), max_chars=700)}
        p2["sections"] = slim
    p2["url"] = _proposal_url(pid)
    return {"ok": True, "proposal": p2}


def _list_tasks_for_rfp_tool(args: dict[str, Any]) -> dict[str, Any]:
    rid = str(args.get("rfpId") or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_rfpId"}
    resp = list_tasks_for_rfp(rfp_id=rid, limit=200, next_token=None)
    return {"ok": True, **(resp if isinstance(resp, dict) else {"data": []})}


def _get_company_tool(args: dict[str, Any]) -> dict[str, Any]:
    cid = str(args.get("companyId") or "").strip()
    if not cid:
        return {"ok": False, "error": "missing_companyId"}
    c = content_repo.get_company_by_company_id(cid)
    if not c:
        return {"ok": False, "error": "not_found"}
    c2 = dict(c)
    for k in ("description", "coverLetter", "firmQualificationsAndExperience"):
        if k in c2:
            c2[k] = clip_text(str(c2.get(k) or ""), max_chars=2500)
    return {"ok": True, "company": c2}


def _get_team_member_tool(args: dict[str, Any]) -> dict[str, Any]:
    mid = str(args.get("memberId") or "").strip()
    if not mid:
        return {"ok": False, "error": "missing_memberId"}
    m = content_repo.get_team_member_by_id(mid)
    if not m:
        return {"ok": False, "error": "not_found"}
    m2 = dict(m)
    # Clip long text fields
    for k in ("biography",):
        if k in m2:
            m2[k] = clip_text(str(m2.get(k) or ""), max_chars=2500)
    # Clip bio profiles
    if "bioProfiles" in m2 and isinstance(m2["bioProfiles"], list):
        for bp in m2["bioProfiles"]:
            if isinstance(bp, dict):
                for k in ("bio", "experience"):
                    if k in bp:
                        bp[k] = clip_text(str(bp.get(k) or ""), max_chars=1500)
    return {"ok": True, "teamMember": m2}


def _list_team_members_tool(args: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(100, int(args.get("limit") or 50)))
    members = content_repo.list_team_members(limit=limit)
    # Clip long fields for list view
    slim: list[dict[str, Any]] = []
    for m in members:
        if not isinstance(m, dict):
            continue
        m2 = dict(m)
        # Only include key fields for list view
        m2.pop("biography", None)
        if "bioProfiles" in m2:
            m2.pop("bioProfiles", None)
        slim.append(m2)
    return {"ok": True, "teamMembers": slim}


def _extract_resume_text_tool(args: dict[str, Any]) -> dict[str, Any]:
    """
    Extract text from a resume file in S3 (PDF or DOCX format).
    Returns the extracted text for analysis.
    """
    s3_key = str(args.get("s3Key") or "").strip()
    if not s3_key:
        return {"ok": False, "error": "missing_s3Key"}
    
    max_bytes = max(5 * 1024 * 1024, min(20 * 1024 * 1024, int(args.get("maxBytes") or 10 * 1024 * 1024)))
    max_chars = max(5000, min(100_000, int(args.get("maxChars") or 50_000)))
    
    try:
        data = get_object_bytes(key=s3_key, max_bytes=max_bytes)
        if not data:
            return {"ok": False, "error": "empty_file"}
        
        # Determine file type from extension or content
        s3_key_lower = s3_key.lower()
        is_pdf = s3_key_lower.endswith(".pdf") or data[:4] == b"%PDF"
        is_docx = s3_key_lower.endswith((".docx", ".doc")) or (
            len(data) > 4 and data[:2] == b"PK"  # DOCX is a ZIP file
        )
        
        text = ""
        
        if is_pdf:
            try:
                reader = PdfReader(io.BytesIO(data))
                parts: list[str] = []
                for page in reader.pages:
                    try:
                        parts.append(page.extract_text() or "")
                    except Exception:
                        continue
                text = "\n".join([p for p in parts if p]).strip()
            except Exception as e:
                return {"ok": False, "error": f"pdf_extraction_failed: {str(e)}"}
        
        elif is_docx:
            try:
                # docx2txt.process requires a file path, so we use a temp file
                with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                    tmp.write(data)
                    tmp_path = tmp.name
                try:
                    text = docx2txt.process(tmp_path) or ""
                    text = text.strip()
                finally:
                    # Clean up temp file
                    try:
                        Path(tmp_path).unlink(missing_ok=True)
                    except Exception:
                        pass
            except Exception as e:
                return {"ok": False, "error": f"docx_extraction_failed: {str(e)}"}
        
        else:
            # Try UTF-8 decode for plain text
            try:
                text = data.decode("utf-8", errors="replace").strip()
            except Exception:
                return {"ok": False, "error": "unsupported_format"}
        
        if not text:
            return {"ok": False, "error": "no_text_extracted"}
        
        # Clip if too long
        if len(text) > max_chars:
            text = text[:max_chars] + "…"
        
        return {"ok": True, "s3Key": s3_key, "text": text, "extractedChars": len(text)}
    
    except Exception as e:
        return {"ok": False, "error": str(e) or "extraction_failed"}


# --- Generic storage inspection tools (bounded, allowlisted) ---


def _ddb_get_item_tool(args: dict[str, Any]) -> dict[str, Any]:
    table_name = str(args.get("tableName") or "").strip() or None
    pk = str((args.get("pk") or "")).strip()
    sk = str((args.get("sk") or "")).strip()
    if not pk or not sk:
        return {"ok": False, "error": "missing_pk_or_sk"}
    try:
        t = _resolve_ddb_table(table_name)
    except Exception as e:
        return {"ok": False, "error": str(e) or "invalid_table"}
    it = t.get_item(key={"pk": pk, "sk": sk})
    if not it:
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "tableName": str(getattr(t, "table_name", "") or table_name or ""), "item": _slim_item(it)}


def _ddb_query_pk_tool(args: dict[str, Any]) -> dict[str, Any]:
    table_name = str(args.get("tableName") or "").strip() or None
    pk = str((args.get("pk") or "")).strip()
    if not pk:
        return {"ok": False, "error": "missing_pk"}
    sk_prefix = str((args.get("skBeginsWith") or "")).strip() or None
    limit = max(1, min(50, int(args.get("limit") or 25)))
    next_token = str(args.get("nextToken") or "").strip() or None
    scan_fwd = bool(args.get("scanIndexForward") is True)

    expr = Key("pk").eq(pk)
    if sk_prefix:
        expr = expr & Key("sk").begins_with(sk_prefix)
    try:
        t = _resolve_ddb_table(table_name)
    except Exception as e:
        return {"ok": False, "error": str(e) or "invalid_table"}
    pg = t.query_page(
        key_condition_expression=expr,
        index_name=None,
        limit=limit,
        scan_index_forward=scan_fwd,
        next_token=next_token,
    )
    items = [x for x in (_slim_item(it) for it in (pg.items or [])) if isinstance(x, dict)]
    return {
        "ok": True,
        "tableName": str(getattr(t, "table_name", "") or table_name or ""),
        "pk": pk,
        "skBeginsWith": sk_prefix,
        "items": items,
        "nextToken": pg.next_token,
    }


def _ddb_query_gsi1_tool(args: dict[str, Any]) -> dict[str, Any]:
    table_name = str(args.get("tableName") or "").strip() or None
    gpk = str((args.get("gsi1pk") or "")).strip()
    if not gpk:
        return {"ok": False, "error": "missing_gsi1pk"}
    gsk_prefix = str((args.get("gsi1skBeginsWith") or "")).strip() or None
    limit = max(1, min(50, int(args.get("limit") or 25)))
    next_token = str(args.get("nextToken") or "").strip() or None
    scan_fwd = bool(args.get("scanIndexForward") is True)

    expr = Key("gsi1pk").eq(gpk)
    if gsk_prefix:
        expr = expr & Key("gsi1sk").begins_with(gsk_prefix)
    try:
        t = _resolve_ddb_table(table_name)
    except Exception as e:
        return {"ok": False, "error": str(e) or "invalid_table"}
    pg = t.query_page(
        index_name="GSI1",
        key_condition_expression=expr,
        limit=limit,
        scan_index_forward=scan_fwd,
        next_token=next_token,
    )
    items = [x for x in (_slim_item(it) for it in (pg.items or [])) if isinstance(x, dict)]
    return {
        "ok": True,
        "tableName": str(getattr(t, "table_name", "") or table_name or ""),
        "gsi1pk": gpk,
        "gsi1skBeginsWith": gsk_prefix,
        "items": items,
        "nextToken": pg.next_token,
    }


def _s3_list_objects_tool(args: dict[str, Any]) -> dict[str, Any]:
    prefix_raw = str(args.get("prefix") or "").strip()
    limit = max(1, min(50, int(args.get("limit") or 25)))
    next_token = str(args.get("nextToken") or "").strip() or None
    try:
        prefix = _require_allowed_s3_prefix(prefix_raw)
        return s3_list_objects(prefix=prefix, limit=limit, continuation_token=next_token)
    except Exception as e:
        return {"ok": False, "error": str(e) or "s3_list_failed"}


def _s3_get_object_text_tool(args: dict[str, Any]) -> dict[str, Any]:
    key_raw = str(args.get("key") or "").strip()
    max_bytes = max(1, min(10 * 1024 * 1024, int(args.get("maxBytes") or (2 * 1024 * 1024))))
    max_chars = max(1000, min(50_000, int(args.get("maxChars") or 20_000)))
    try:
        key = _require_allowed_s3_key(key_raw)
        return s3_get_object_text(key=key, max_bytes=max_bytes, max_chars=max_chars)
    except Exception as e:
        return {"ok": False, "error": str(e) or "s3_get_failed"}


def _s3_presign_get_tool(args: dict[str, Any]) -> dict[str, Any]:
    key_raw = str(args.get("key") or "").strip()
    expires_in = max(60, min(24 * 3600, int(args.get("expiresIn") or 3600)))
    try:
        key = _require_allowed_s3_key(key_raw)
        return {"ok": True, **s3_presign_get_object(key=key, expires_in=expires_in)}
    except Exception as e:
        return {"ok": False, "error": str(e) or "s3_presign_failed"}


# --- AWS service inspection tools ---


def _sqs_get_queue_depth_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = str(args.get("queueUrl") or "").strip()
    try:
        return sqs_get_queue_depth(queue_url=q)
    except Exception as e:
        return {"ok": False, "error": str(e) or "sqs_failed"}


def _sqs_get_queue_attributes_tool(args: dict[str, Any]) -> dict[str, Any]:
    q = str(args.get("queueUrl") or "").strip()
    attrs = args.get("attributes") if isinstance(args.get("attributes"), list) else None
    try:
        return sqs_get_queue_attributes(queue_url=q, attributes=attrs)
    except Exception as e:
        return {"ok": False, "error": str(e) or "sqs_failed"}


def _ecs_describe_service_tool(args: dict[str, Any]) -> dict[str, Any]:
    cluster = str(args.get("cluster") or "").strip() or None
    service = str(args.get("service") or "").strip() or None
    try:
        return ecs_describe_service(cluster=cluster, service=service)
    except Exception as e:
        return {"ok": False, "error": str(e) or "ecs_failed"}


def _ecs_list_tasks_tool(args: dict[str, Any]) -> dict[str, Any]:
    cluster = str(args.get("cluster") or "").strip() or None
    service = str(args.get("service") or "").strip() or None
    desired = str(args.get("desiredStatus") or "").strip() or None
    limit = int(args.get("limit") or 25)
    try:
        return ecs_list_tasks(cluster=cluster, service=service, desired_status=desired, limit=limit)
    except Exception as e:
        return {"ok": False, "error": str(e) or "ecs_failed"}


def _ecs_describe_task_definition_tool(args: dict[str, Any]) -> dict[str, Any]:
    td = str(args.get("taskDefinition") or "").strip()
    try:
        return ecs_describe_task_definition(task_definition=td)
    except Exception as e:
        return {"ok": False, "error": str(e) or "ecs_failed"}


def _cognito_describe_user_pool_tool(args: dict[str, Any]) -> dict[str, Any]:
    up = str(args.get("userPoolId") or "").strip() or None
    try:
        return cognito_describe_user_pool(user_pool_id=up)
    except Exception as e:
        return {"ok": False, "error": str(e) or "cognito_failed"}


def _cognito_admin_get_user_tool(args: dict[str, Any]) -> dict[str, Any]:
    up = str(args.get("userPoolId") or "").strip() or None
    username = str(args.get("username") or "").strip()
    try:
        return cognito_admin_get_user(user_pool_id=up, username=username)
    except Exception as e:
        return {"ok": False, "error": str(e) or "cognito_failed"}


def _cognito_list_users_tool(args: dict[str, Any]) -> dict[str, Any]:
    up = str(args.get("userPoolId") or "").strip() or None
    limit = int(args.get("limit") or 20)
    next_token = str(args.get("nextToken") or "").strip() or None
    flt = str(args.get("filter") or "").strip() or None
    try:
        return cognito_list_users(user_pool_id=up, limit=limit, pagination_token=next_token, filter=flt)
    except Exception as e:
        return {"ok": False, "error": str(e) or "cognito_failed"}


def _secrets_describe_tool(args: dict[str, Any]) -> dict[str, Any]:
    sid = str(args.get("secretId") or "").strip()
    try:
        return secrets_describe_secret(secret_id=sid)
    except Exception as e:
        return {"ok": False, "error": str(e) or "secrets_failed"}


def _logs_tail_tool(args: dict[str, Any]) -> dict[str, Any]:
    lg = str(args.get("logGroupName") or "").strip()
    lookback = int(args.get("lookbackMinutes") or 15)
    limit = int(args.get("limit") or 50)
    try:
        return logs_tail(log_group_name=lg, lookback_minutes=lookback, limit=limit)
    except Exception as e:
        return {"ok": False, "error": str(e) or "logs_failed"}


def _github_list_pulls_tool(args: dict[str, Any]) -> dict[str, Any]:
    repo = str(args.get("repo") or "").strip() or None
    state = str(args.get("state") or "").strip() or "open"
    limit = int(args.get("limit") or 10)
    try:
        return github_list_pulls(repo=repo, state=state, limit=limit)
    except Exception as e:
        return {"ok": False, "error": str(e) or "github_failed"}


def _github_get_pull_tool(args: dict[str, Any]) -> dict[str, Any]:
    repo = str(args.get("repo") or "").strip() or None
    num = int(args.get("number") or 0)
    if num <= 0:
        return {"ok": False, "error": "missing_number"}
    try:
        return github_get_pull(repo=repo, number=num)
    except Exception as e:
        return {"ok": False, "error": str(e) or "github_failed"}


def _github_list_check_runs_tool(args: dict[str, Any]) -> dict[str, Any]:
    repo = str(args.get("repo") or "").strip() or None
    ref = str(args.get("ref") or "").strip()
    flt = str(args.get("filter") or "").strip() or "latest"
    try:
        return github_list_check_runs(repo=repo, ref=ref, filter=flt)
    except Exception as e:
        return {"ok": False, "error": str(e) or "github_failed"}


# Merge memory tools into the registry
_memory_tools = get_memory_tools()

READ_TOOLS: dict[str, tuple[dict[str, Any], ToolFn]] = {
    **_memory_tools,
    **EXTERNAL_CONTEXT_TOOLS,  # External context tools (news, weather, research, etc.)
    "slack_list_recent_messages": (
        tool_def(
            "slack_list_recent_messages",
            "List recent messages in a Slack channel (read-only; bounded).",
            {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "minLength": 1, "maxLength": 40},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["channel"],
                "additionalProperties": False,
            },
        ),
        _slack_list_recent_messages_tool,
    ),
    "slack_get_thread": (
        tool_def(
            "slack_get_thread",
            "Fetch a Slack thread (replies) for a channel + threadTs (bounded).",
            {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "minLength": 1, "maxLength": 40},
                    "threadTs": {"type": "string", "minLength": 1, "maxLength": 40},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["channel", "threadTs"],
                "additionalProperties": False,
            },
        ),
        _slack_get_thread_tool,
    ),
    "slack_create_canvas": (
        tool_def(
            "slack_create_canvas",
            "Create a Slack canvas in a channel. Canvases are rich documents that can contain markdown, tables, images, mentions, and more. The markdown supports Slack-specific elements like user mentions (![](@U123456)), channel mentions (![](#C123456)), emojis, links, lists, checkboxes, and tables. Use this to create project status pages, onboarding guides, newsletters, or any structured content in a channel.",
            {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "minLength": 1, "maxLength": 40, "description": "The channel ID where the canvas should be created"},
                    "title": {"type": "string", "minLength": 1, "maxLength": 255, "description": "The title of the canvas"},
                    "markdown": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 100000,
                        "description": "Markdown content for the canvas. Supports standard markdown plus Slack-specific elements: user mentions (![](@U123456)), channel mentions (![](#C123456)), emojis, tables, checkboxes, links, lists, headings (h1-h3), code blocks, quotes, and more.",
                    },
                },
                "required": ["channel", "title", "markdown"],
                "additionalProperties": False,
            },
        ),
        _slack_create_canvas_tool,
    ),
    "dynamodb_describe_table": (
        tool_def(
            "dynamodb_describe_table",
            "Describe a DynamoDB table (allowlisted).",
            {
                "type": "object",
                "properties": {"tableName": {"type": "string", "minLength": 1, "maxLength": 255}},
                "required": ["tableName"],
                "additionalProperties": False,
            },
        ),
        _dynamodb_describe_table_tool,
    ),
    "dynamodb_list_tables": (
        tool_def(
            "dynamodb_list_tables",
            "List allowed DynamoDB tables (from allowlist; does not enumerate AWS).",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "required": [],
                "additionalProperties": False,
            },
        ),
        _dynamodb_list_tables_tool,
    ),
    "s3_head_object": (
        tool_def(
            "s3_head_object",
            "Get S3 object metadata (allowlisted prefixes; no body).",
            {
                "type": "object",
                "properties": {"key": {"type": "string", "minLength": 1, "maxLength": 2048}},
                "required": ["key"],
                "additionalProperties": False,
            },
        ),
        _s3_head_object_tool,
    ),
    "s3_presign_put": (
        tool_def(
            "s3_presign_put",
            "Create a presigned PUT URL for an allowlisted S3 key.",
            {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1, "maxLength": 2048},
                    "contentType": {"type": "string", "maxLength": 200},
                    "expiresIn": {"type": "integer", "minimum": 60, "maximum": 3600},
                },
                "required": ["key"],
                "additionalProperties": False,
            },
        ),
        _s3_presign_put_tool,
    ),
    "telemetry_search_logs": (
        tool_def(
            "telemetry_search_logs",
            "Run a bounded CloudWatch Logs Insights query (allowlisted groups).",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "logGroupNames": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
                    "sinceIso": {"type": "string", "maxLength": 64},
                    "untilIso": {"type": "string", "maxLength": 64},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        _telemetry_search_logs_tool,
    ),
    "telemetry_top_errors": (
        tool_def(
            "telemetry_top_errors",
            "Summarize top error signatures in a log group over a lookback window.",
            {
                "type": "object",
                "properties": {
                    "logGroupName": {"type": "string", "minLength": 1, "maxLength": 512},
                    "lookbackMinutes": {"type": "integer", "minimum": 5, "maximum": 360},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["logGroupName"],
                "additionalProperties": False,
            },
        ),
        _telemetry_top_errors_tool,
    ),
    "browser_new_context": (
        tool_def(
            "browser_new_context",
            "Create a new isolated browser context (Playwright worker).",
            {
                "type": "object",
                "properties": {
                    "userAgent": {"type": "string", "maxLength": 300},
                    "viewportWidth": {"type": "integer", "minimum": 320, "maximum": 3840},
                    "viewportHeight": {"type": "integer", "minimum": 240, "maximum": 2160},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _browser_new_context_tool,
    ),
    "browser_new_page": (
        tool_def(
            "browser_new_page",
            "Create a new page in an existing browser context.",
            {
                "type": "object",
                "properties": {"contextId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["contextId"],
                "additionalProperties": False,
            },
        ),
        _browser_new_page_tool,
    ),
    "browser_goto": (
        tool_def(
            "browser_goto",
            "Navigate to a URL (domain allowlisted).",
            {
                "type": "object",
                "properties": {
                    "pageId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "url": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "waitUntil": {"type": "string", "maxLength": 40},
                    "timeoutMs": {"type": "integer", "minimum": 1000, "maximum": 120000},
                },
                "required": ["pageId", "url"],
                "additionalProperties": False,
            },
        ),
        _browser_goto_tool,
    ),
    "browser_click": (
        tool_def(
            "browser_click",
            "Click an element by selector.",
            {
                "type": "object",
                "properties": {
                    "pageId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "selector": {"type": "string", "minLength": 1, "maxLength": 600},
                    "timeoutMs": {"type": "integer", "minimum": 1000, "maximum": 120000},
                },
                "required": ["pageId", "selector"],
                "additionalProperties": False,
            },
        ),
        _browser_click_tool,
    ),
    "browser_type": (
        tool_def(
            "browser_type",
            "Type into an input/textarea by selector.",
            {
                "type": "object",
                "properties": {
                    "pageId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "selector": {"type": "string", "minLength": 1, "maxLength": 600},
                    "text": {"type": "string", "minLength": 1, "maxLength": 5000},
                    "clearFirst": {"type": "boolean"},
                    "timeoutMs": {"type": "integer", "minimum": 1000, "maximum": 120000},
                },
                "required": ["pageId", "selector", "text"],
                "additionalProperties": False,
            },
        ),
        _browser_type_tool,
    ),
    "browser_wait_for": (
        tool_def(
            "browser_wait_for",
            "Wait for a selector or visible text.",
            {
                "type": "object",
                "properties": {
                    "pageId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "selector": {"type": "string", "maxLength": 600},
                    "text": {"type": "string", "maxLength": 400},
                    "timeoutMs": {"type": "integer", "minimum": 1000, "maximum": 120000},
                },
                "required": ["pageId"],
                "additionalProperties": False,
            },
        ),
        _browser_wait_for_tool,
    ),
    "browser_extract": (
        tool_def(
            "browser_extract",
            "Extract text/html/attribute from the first element matching selector.",
            {
                "type": "object",
                "properties": {
                    "pageId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "selector": {"type": "string", "minLength": 1, "maxLength": 600},
                    "mode": {"type": "string", "maxLength": 20},
                    "attribute": {"type": "string", "maxLength": 80},
                },
                "required": ["pageId", "selector"],
                "additionalProperties": False,
            },
        ),
        _browser_extract_tool,
    ),
    "browser_screenshot": (
        tool_def(
            "browser_screenshot",
            "Capture a screenshot and store it in S3 under agent/ prefix.",
            {
                "type": "object",
                "properties": {
                    "pageId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "fullPage": {"type": "boolean"},
                    "name": {"type": "string", "maxLength": 120},
                },
                "required": ["pageId"],
                "additionalProperties": False,
            },
        ),
        _browser_screenshot_tool,
    ),
    "browser_trace_start": (
        tool_def(
            "browser_trace_start",
            "Start Playwright tracing on a browser context.",
            {
                "type": "object",
                "properties": {
                    "contextId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "screenshots": {"type": "boolean"},
                    "snapshots": {"type": "boolean"},
                    "sources": {"type": "boolean"},
                },
                "required": ["contextId"],
                "additionalProperties": False,
            },
        ),
        _browser_trace_start_tool,
    ),
    "browser_trace_stop": (
        tool_def(
            "browser_trace_stop",
            "Stop Playwright tracing and upload the trace zip to S3 (agent/ prefix).",
            {
                "type": "object",
                "properties": {
                    "contextId": {"type": "string", "minLength": 1, "maxLength": 120},
                    "name": {"type": "string", "maxLength": 120},
                },
                "required": ["contextId"],
                "additionalProperties": False,
            },
        ),
        _browser_trace_stop_tool,
    ),
    "browser_close": (
        tool_def(
            "browser_close",
            "Close a page and/or context to free resources.",
            {
                "type": "object",
                "properties": {
                    "contextId": {"type": "string", "maxLength": 120},
                    "pageId": {"type": "string", "maxLength": 120},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _browser_close_tool,
    ),
    "user_memory_load": (
        tool_def(
            "user_memory_load",
            "Load durable user memory blocks for a userSub (clipped).",
            {
                "type": "object",
                "properties": {
                    "userSub": {"type": "string", "minLength": 1, "maxLength": 120},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "maxChars": {"type": "integer", "minimum": 500, "maximum": 20000},
                },
                "required": ["userSub"],
                "additionalProperties": False,
            },
        ),
        _user_memory_load_tool,
    ),
    "tenant_memory_load": (
        tool_def(
            "tenant_memory_load",
            "Load durable tenant memory blocks (shared org knowledge), clipped.",
            {
                "type": "object",
                "properties": {
                    "tenantId": {"type": "string", "maxLength": 120},
                    "emailDomain": {"type": "string", "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "maxChars": {"type": "integer", "minimum": 500, "maximum": 20000},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _tenant_memory_load_tool,
    ),
    "memory_search": (
        tool_def(
            "memory_search",
            "[LEGACY] Search user+tenant memory blocks by keyword (bounded). For new structured agent memories, use agent_memory_search.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 200},
                    "userSub": {"type": "string", "maxLength": 120},
                    "tenantId": {"type": "string", "maxLength": 120},
                    "emailDomain": {"type": "string", "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        _memory_search_tool,
    ),
    "skills_search": (
        tool_def(
            "skills_search",
            "Search available skills by name prefix and/or tags (metadata only; does not load bodies).",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 200},
                    "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 25},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                    "nextToken": {"type": "string", "maxLength": 2000},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _skills_search_tool,
    ),
    "skills_get": (
        tool_def(
            "skills_get",
            "Get SkillIndex metadata for a skillId (does not load body).",
            {
                "type": "object",
                "properties": {"skillId": {"type": "string", "minLength": 1, "maxLength": 60}},
                "required": ["skillId"],
                "additionalProperties": False,
            },
        ),
        _skills_get_tool,
    ),
    "skills_load": (
        tool_def(
            "skills_load",
            "Load a skill body from S3 (clipped). Use after selecting via skills_search/get.",
            {
                "type": "object",
                "properties": {
                    "skillId": {"type": "string", "minLength": 1, "maxLength": 60},
                    "maxChars": {"type": "integer", "minimum": 2000, "maximum": 50000},
                },
                "required": ["skillId"],
                "additionalProperties": False,
            },
        ),
        _skills_load_tool,
    ),
    "list_rfps": (
        tool_def(
            "list_rfps",
            "List recent RFPs (returns compact fields + links).",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 25}},
                "required": [],
                "additionalProperties": False,
            },
        ),
        _list_rfps_tool,
    ),
    "search_rfps": (
        tool_def(
            "search_rfps",
            "Search RFPs by keywords over title/client/type (returns compact fields + links).",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 400},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 15},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        _search_rfps_tool,
    ),
    "get_rfp": (
        tool_def(
            "get_rfp",
            "Fetch one RFP by ID (includes clipped rawText).",
            {
                "type": "object",
                "properties": {"rfpId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["rfpId"],
                "additionalProperties": False,
            },
        ),
        _get_rfp_tool,
    ),
    "list_proposals": (
        tool_def(
            "list_proposals",
            "List recent proposals (compact fields + links).",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 25}},
                "required": [],
                "additionalProperties": False,
            },
        ),
        _list_proposals_tool,
    ),
    "search_proposals": (
        tool_def(
            "search_proposals",
            "Search proposals by keywords over title/status/rfpId (compact fields + links).",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 400},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 15},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        _search_proposals_tool,
    ),
    "get_proposal": (
        tool_def(
            "get_proposal",
            "Fetch one proposal by ID (includes clipped section previews).",
            {
                "type": "object",
                "properties": {"proposalId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["proposalId"],
                "additionalProperties": False,
            },
        ),
        _get_proposal_tool,
    ),
    "list_tasks_for_rfp": (
        tool_def(
            "list_tasks_for_rfp",
            "List workflow tasks for a given RFP.",
            {
                "type": "object",
                "properties": {"rfpId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["rfpId"],
                "additionalProperties": False,
            },
        ),
        _list_tasks_for_rfp_tool,
    ),
    "get_company": (
        tool_def(
            "get_company",
            "Fetch a company from the content library by companyId.",
            {
                "type": "object",
                "properties": {"companyId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["companyId"],
                "additionalProperties": False,
            },
        ),
        _get_company_tool,
    ),
    "get_team_member": (
        tool_def(
            "get_team_member",
            "Fetch a team member from the content library by memberId. Returns biography, bioProfiles, position, and other details.",
            {
                "type": "object",
                "properties": {"memberId": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["memberId"],
                "additionalProperties": False,
            },
        ),
        _get_team_member_tool,
    ),
    "list_team_members": (
        tool_def(
            "list_team_members",
            "List team members from the content library (returns compact list without full biography details).",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "required": [],
                "additionalProperties": False,
            },
        ),
        _list_team_members_tool,
    ),
    "extract_resume_text": (
        tool_def(
            "extract_resume_text",
            "Extract text from a resume file stored in S3 (supports PDF and DOCX formats). Returns extracted text for analysis.",
            {
                "type": "object",
                "properties": {
                    "s3Key": {"type": "string", "minLength": 1, "maxLength": 500},
                    "maxBytes": {"type": "integer", "minimum": 1024, "maximum": 20 * 1024 * 1024},
                    "maxChars": {"type": "integer", "minimum": 1000, "maximum": 200_000},
                },
                "required": ["s3Key"],
                "additionalProperties": False,
            },
        ),
        _extract_resume_text_tool,
    ),
    "ddb_get_item": (
        tool_def(
            "ddb_get_item",
            "Get one item from DynamoDB by (pk, sk). Defaults to main table; tableName is allowlisted.",
            {
                "type": "object",
                "properties": {
                    "tableName": {"type": "string", "maxLength": 400},
                    "pk": {"type": "string", "minLength": 1, "maxLength": 400},
                    "sk": {"type": "string", "minLength": 1, "maxLength": 400},
                },
                "required": ["pk", "sk"],
                "additionalProperties": False,
            },
        ),
        _ddb_get_item_tool,
    ),
    "ddb_query_pk": (
        tool_def(
            "ddb_query_pk",
            "Query DynamoDB by pk (optionally begins_with on sk). Defaults to main table; tableName is allowlisted.",
            {
                "type": "object",
                "properties": {
                    "tableName": {"type": "string", "maxLength": 400},
                    "pk": {"type": "string", "minLength": 1, "maxLength": 400},
                    "skBeginsWith": {"type": "string", "maxLength": 400},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "nextToken": {"type": "string", "maxLength": 2000},
                    "scanIndexForward": {"type": "boolean"},
                },
                "required": ["pk"],
                "additionalProperties": False,
            },
        ),
        _ddb_query_pk_tool,
    ),
    "ddb_query_gsi1": (
        tool_def(
            "ddb_query_gsi1",
            "Query DynamoDB GSI1 by gsi1pk (optionally begins_with on gsi1sk). Defaults to main table; tableName is allowlisted.",
            {
                "type": "object",
                "properties": {
                    "tableName": {"type": "string", "maxLength": 400},
                    "gsi1pk": {"type": "string", "minLength": 1, "maxLength": 400},
                    "gsi1skBeginsWith": {"type": "string", "maxLength": 400},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "nextToken": {"type": "string", "maxLength": 2000},
                    "scanIndexForward": {"type": "boolean"},
                },
                "required": ["gsi1pk"],
                "additionalProperties": False,
            },
        ),
        _ddb_query_gsi1_tool,
    ),
    "s3_list_objects": (
        tool_def(
            "s3_list_objects",
            "List objects in the assets S3 bucket (optionally under a prefix).",
            {
                "type": "object",
                "properties": {
                    "prefix": {"type": "string", "maxLength": 1024},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "nextToken": {"type": "string", "maxLength": 2000},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _s3_list_objects_tool,
    ),
    "s3_get_object_text": (
        tool_def(
            "s3_get_object_text",
            "Get a small S3 object and decode it as UTF-8 text (best for JSON/MD/TXT).",
            {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1, "maxLength": 2048},
                    "maxBytes": {"type": "integer", "minimum": 1, "maximum": 10485760},
                    "maxChars": {"type": "integer", "minimum": 1000, "maximum": 50000},
                },
                "required": ["key"],
                "additionalProperties": False,
            },
        ),
        _s3_get_object_text_tool,
    ),
    "s3_presign_get": (
        tool_def(
            "s3_presign_get",
            "Create a presigned GET URL for an S3 key in the assets bucket.",
            {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1, "maxLength": 2048},
                    "expiresIn": {"type": "integer", "minimum": 60, "maximum": 86400},
                },
                "required": ["key"],
                "additionalProperties": False,
            },
        ),
        _s3_presign_get_tool,
    ),
    "sqs_get_queue_depth": (
        tool_def(
            "sqs_get_queue_depth",
            "Fetch SQS queue approximate depth (allowlisted queue URLs only).",
            {
                "type": "object",
                "properties": {"queueUrl": {"type": "string", "minLength": 1, "maxLength": 2000}},
                "required": ["queueUrl"],
                "additionalProperties": False,
            },
        ),
        _sqs_get_queue_depth_tool,
    ),
    "sqs_get_queue_attributes": (
        tool_def(
            "sqs_get_queue_attributes",
            "Fetch SQS queue attributes (allowlisted queue URLs only).",
            {
                "type": "object",
                "properties": {
                    "queueUrl": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "attributes": {"type": "array", "items": {"type": "string"}, "maxItems": 25},
                },
                "required": ["queueUrl"],
                "additionalProperties": False,
            },
        ),
        _sqs_get_queue_attributes_tool,
    ),
    "ecs_describe_service": (
        tool_def(
            "ecs_describe_service",
            "Describe an ECS service (allowlisted cluster/service; defaults to configured ECS_CLUSTER/ECS_SERVICE).",
            {
                "type": "object",
                "properties": {
                    "cluster": {"type": "string", "maxLength": 200},
                    "service": {"type": "string", "maxLength": 200},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _ecs_describe_service_tool,
    ),
    "ecs_list_tasks": (
        tool_def(
            "ecs_list_tasks",
            "List ECS tasks for a service (allowlisted cluster/service; defaults to configured).",
            {
                "type": "object",
                "properties": {
                    "cluster": {"type": "string", "maxLength": 200},
                    "service": {"type": "string", "maxLength": 200},
                    "desiredStatus": {"type": "string", "maxLength": 20},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _ecs_list_tasks_tool,
    ),
    "ecs_describe_task_definition": (
        tool_def(
            "ecs_describe_task_definition",
            "Describe an ECS task definition (compact fields).",
            {
                "type": "object",
                "properties": {"taskDefinition": {"type": "string", "minLength": 1, "maxLength": 400}},
                "required": ["taskDefinition"],
                "additionalProperties": False,
            },
        ),
        _ecs_describe_task_definition_tool,
    ),
    "cognito_describe_user_pool": (
        tool_def(
            "cognito_describe_user_pool",
            "Describe the Cognito user pool (allowlisted; defaults to configured COGNITO_USER_POOL_ID).",
            {
                "type": "object",
                "properties": {"userPoolId": {"type": "string", "maxLength": 120}},
                "required": [],
                "additionalProperties": False,
            },
        ),
        _cognito_describe_user_pool_tool,
    ),
    "cognito_admin_get_user": (
        tool_def(
            "cognito_admin_get_user",
            "AdminGetUser in Cognito (allowlisted pool).",
            {
                "type": "object",
                "properties": {
                    "userPoolId": {"type": "string", "maxLength": 120},
                    "username": {"type": "string", "minLength": 1, "maxLength": 256},
                },
                "required": ["username"],
                "additionalProperties": False,
            },
        ),
        _cognito_admin_get_user_tool,
    ),
    "cognito_list_users": (
        tool_def(
            "cognito_list_users",
            "List Cognito users (tight limits; allowlisted pool).",
            {
                "type": "object",
                "properties": {
                    "userPoolId": {"type": "string", "maxLength": 120},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "nextToken": {"type": "string", "maxLength": 1200},
                    "filter": {"type": "string", "maxLength": 250},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _cognito_list_users_tool,
    ),
    "secrets_describe": (
        tool_def(
            "secrets_describe",
            "Describe a Secrets Manager secret (metadata only; allowlisted).",
            {
                "type": "object",
                "properties": {"secretId": {"type": "string", "minLength": 1, "maxLength": 400}},
                "required": ["secretId"],
                "additionalProperties": False,
            },
        ),
        _secrets_describe_tool,
    ),
    "logs_tail": (
        tool_def(
            "logs_tail",
            "Tail CloudWatch Logs for an allowlisted log group (bounded lookback + lines).",
            {
                "type": "object",
                "properties": {
                    "logGroupName": {"type": "string", "minLength": 1, "maxLength": 400},
                    "lookbackMinutes": {"type": "integer", "minimum": 1, "maximum": 180},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": ["logGroupName"],
                "additionalProperties": False,
            },
        ),
        _logs_tail_tool,
    ),
    "github_list_pulls": (
        tool_def(
            "github_list_pulls",
            "List recent pull requests for an allowlisted GitHub repo (defaults to configured GITHUB_REPO).",
            {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "maxLength": 200},
                    "state": {"type": "string", "maxLength": 20},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        _github_list_pulls_tool,
    ),
    "github_get_pull": (
        tool_def(
            "github_get_pull",
            "Fetch one pull request by number for an allowlisted repo.",
            {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "maxLength": 200},
                    "number": {"type": "integer", "minimum": 1, "maximum": 1000000},
                },
                "required": ["number"],
                "additionalProperties": False,
            },
        ),
        _github_get_pull_tool,
    ),
    "github_list_check_runs": (
        tool_def(
            "github_list_check_runs",
            "List check runs for a given ref/SHA on an allowlisted repo.",
            {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "maxLength": 200},
                    "ref": {"type": "string", "minLength": 1, "maxLength": 200},
                    "filter": {"type": "string", "maxLength": 20},
                },
                "required": ["ref"],
                "additionalProperties": False,
            },
        ),
        _github_list_check_runs_tool,
    ),
}

