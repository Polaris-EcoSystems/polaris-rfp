from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..settings import settings
from ..observability.logging import get_logger

log = get_logger("agent_memory_opensearch")

# OpenSearch index name
MEMORIES_INDEX = "memories"


def _get_opensearch_endpoint() -> str:
    """
    Get the OpenSearch endpoint URL.
    
    Raises:
        ValueError: If OPENSEARCH_ENDPOINT is not configured
    """
    endpoint = settings.opensearch_endpoint
    if not endpoint:
        raise ValueError("OPENSEARCH_ENDPOINT is not set")
    return endpoint.rstrip("/")


def _get_opensearch_url(path: str = "") -> str:
    """Build full OpenSearch URL for a given path."""
    base = _get_opensearch_endpoint()
    if path.startswith("/"):
        path = path[1:]
    return f"{base}/{path}"


def _opensearch_request(
    method: str,
    path: str,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Make a request to OpenSearch.
    
    Note: This assumes OpenSearch is configured without authentication for now.
    In production, you might need to use AWS SigV4 signing or basic auth.
    """
    url = _get_opensearch_url(path)
    
    kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": {"Content-Type": "application/json"},
        "timeout": 5,
    }
    
    if data is not None:
        kwargs["data"] = json.dumps(data)
    
    if params:
        kwargs["params"] = params
    
    try:
        with httpx.Client(timeout=5.0) as client:
            # Build request kwargs
            req_kwargs: dict[str, Any] = {"headers": {"Content-Type": "application/json"}}
            if data is not None:
                req_kwargs["content"] = json.dumps(data)
            if params:
                req_kwargs["params"] = params
            
            response = client.request(method=method, url=url, **req_kwargs)
            response.raise_for_status()
            if response.content:
                return response.json()
            return None
    except Exception as e:
        log.warning("opensearch_request_failed", method=method, path=path, error=str(e))
        raise


def ensure_index_exists() -> None:
    """
    Ensure the memories index exists with proper mapping.
    
    Creates the index if it doesn't exist. This is safe to call multiple times.
    The index will only be created once; subsequent calls will detect it exists.
    
    Raises:
        Exception: If OpenSearch is unavailable or index creation fails
    """
    index_url = _get_opensearch_url(MEMORIES_INDEX)
    
    # Check if index exists
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.head(index_url)
            if response.status_code == 200:
                return  # Index already exists
    except Exception:
        pass
    
    # Create index with mapping
    mapping = {
        "mappings": {
            "properties": {
                "memoryId": {"type": "keyword"},
                "memoryType": {"type": "keyword"},
                "scopeId": {"type": "keyword"},
                "content": {"type": "text", "analyzer": "standard"},
                "tags": {"type": "keyword"},
                "keywords": {"type": "keyword"},
                "createdAt": {"type": "date"},
                "accessCount": {"type": "integer"},
                "lastAccessedAt": {"type": "date"},
                "summary": {"type": "text", "analyzer": "standard"},
                "compressed": {"type": "boolean"},
                # Provenance fields for traceability
                "cognitoUserId": {"type": "keyword"},
                "slackUserId": {"type": "keyword"},
                "slackChannelId": {"type": "keyword"},
                "slackThreadTs": {"type": "keyword"},
                "slackTeamId": {"type": "keyword"},
                "rfpId": {"type": "keyword"},
                "source": {"type": "keyword"},
            }
        }
    }
    
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.put(index_url, json=mapping)
            response.raise_for_status()
            log.info("opensearch_index_created", index=MEMORIES_INDEX)
    except Exception as e:
        log.error("opensearch_index_creation_failed", index=MEMORIES_INDEX, error=str(e))
        raise


def index_memory(memory: dict[str, Any]) -> None:
    """
    Index a memory in OpenSearch for full-text search.
    
    This operation is best-effort and non-blocking. Failures are logged but do not
    raise exceptions to avoid blocking memory storage operations.
    
    Args:
        memory: Memory dict from DynamoDB (should include memoryId, content, tags, keywords, provenance fields, etc.)
    """
    if not memory.get("memoryId"):
        log.warning("opensearch_index_skipped_no_memory_id")
        return
    
    ensure_index_exists()
    
    memory_id = str(memory.get("memoryId"))
    doc = {
        "memoryId": memory_id,
        "memoryType": memory.get("memoryType"),
        "scopeId": memory.get("scopeId"),
        "content": memory.get("content", ""),
        "tags": memory.get("tags", []),
        "keywords": memory.get("keywords", []),
        "createdAt": memory.get("createdAt"),
        "accessCount": memory.get("accessCount", 0),
        "lastAccessedAt": memory.get("lastAccessedAt"),
        "summary": memory.get("summary"),
        "compressed": memory.get("compressed", False),
        # Provenance fields for traceability
        "cognitoUserId": memory.get("cognitoUserId"),
        "slackUserId": memory.get("slackUserId"),
        "slackChannelId": memory.get("slackChannelId"),
        "slackThreadTs": memory.get("slackThreadTs"),
        "slackTeamId": memory.get("slackTeamId"),
        "rfpId": memory.get("rfpId"),
        "source": memory.get("source"),
    }
    
    # Use memoryId as document ID for easy updates/deletes
    doc_url = _get_opensearch_url(f"{MEMORIES_INDEX}/_doc/{memory_id}")
    
    try:
        start_time = time.time()
        with httpx.Client(timeout=5.0) as client:
            response = client.put(doc_url, json=doc)
            response.raise_for_status()
        duration_ms = int((time.time() - start_time) * 1000)
        log.info("opensearch_indexed", memory_id=memory_id, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
        log.warning("opensearch_index_failed", memory_id=memory_id, error=str(e), duration_ms=duration_ms)
        # Don't raise - indexing failures shouldn't block memory storage


def delete_memory_index(memory_id: str) -> None:
    """Delete a memory from OpenSearch index."""
    doc_url = _get_opensearch_url(f"{MEMORIES_INDEX}/_doc/{memory_id}")
    
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.delete(doc_url)
            # 404 is OK (document doesn't exist)
            if response.status_code not in (200, 404):
                response.raise_for_status()
    except Exception as e:
        log.warning("opensearch_delete_failed", memory_id=memory_id, error=str(e))
        # Don't raise - deletion failures are not critical


def search_memories(
    *,
    query_text: str | None = None,
    keywords: list[str] | None = None,
    tags: list[str] | None = None,
    scope_id: str | None = None,
    memory_type: str | None = None,
    limit: int = 50,
    # Provenance filters
    cognito_user_id: str | None = None,
    slack_user_id: str | None = None,
    slack_channel_id: str | None = None,
    rfp_id: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search memories in OpenSearch.
    
    Args:
        query_text: Full-text search query
        keywords: Match any of these keywords
        tags: Match any of these tags
        scope_id: Filter by scope
        memory_type: Filter by memory type
        limit: Maximum number of results
    
    Returns:
        List of memory documents (includes memoryId for lookup in DynamoDB)
    """
    ensure_index_exists()
    
    # Build query
    must_clauses: list[dict[str, Any]] = []
    should_clauses: list[dict[str, Any]] = []
    
    # Full-text search on content
    if query_text:
        must_clauses.append({
            "multi_match": {
                "query": query_text,
                "fields": ["content^2", "summary", "keywords"],
                "type": "best_fields",
                "operator": "or",
            }
        })
    
    # Keyword matching
    if keywords:
        keyword_filters = [{"term": {"keywords": kw.lower()}} for kw in keywords]
        should_clauses.extend(keyword_filters)
    
    # Tag matching
    if tags:
        tag_filters = [{"term": {"tags": tag.lower()}} for tag in tags]
        should_clauses.extend(tag_filters)
    
    # Filters (must match)
    if scope_id:
        must_clauses.append({"term": {"scopeId": scope_id}})
    
    if memory_type:
        must_clauses.append({"term": {"memoryType": memory_type}})
    
    # Provenance filters
    if cognito_user_id:
        must_clauses.append({"term": {"cognitoUserId": cognito_user_id}})
    if slack_user_id:
        must_clauses.append({"term": {"slackUserId": slack_user_id}})
    if slack_channel_id:
        must_clauses.append({"term": {"slackChannelId": slack_channel_id}})
    if rfp_id:
        must_clauses.append({"term": {"rfpId": rfp_id}})
    if source:
        must_clauses.append({"term": {"source": source}})
    
    # Build final query
    query: dict[str, Any] = {
        "bool": {
            "must": must_clauses,
        }
    }
    
    if should_clauses:
        query["bool"]["should"] = should_clauses
        query["bool"]["minimum_should_match"] = 1
    
    search_body = {
        "size": min(limit, 100),
        "query": query,
        "sort": [
            {"createdAt": {"order": "desc"}},  # Most recent first
            {"accessCount": {"order": "desc"}},  # Then by access count
        ],
    }
    
    search_url = _get_opensearch_url(f"{MEMORIES_INDEX}/_search")
    
    try:
        start_time = time.time()
        with httpx.Client(timeout=5.0) as client:
            response = client.post(search_url, json=search_body)
            response.raise_for_status()
            result = response.json()
        duration_ms = int((time.time() - start_time) * 1000)
        
        hits = result.get("hits", {}).get("hits", [])
        total_hits = result.get("hits", {}).get("total", {})
        total_count = total_hits.get("value", len(hits)) if isinstance(total_hits, dict) else len(hits)
        
        memories: list[dict[str, Any]] = []
        for hit in hits:
            source_raw = hit.get("_source", {})
            if isinstance(source_raw, dict):
                memories.append(source_raw)
        
        log.info(
            "opensearch_search_completed",
            query_length=len(query_text or ""),
            result_count=len(memories),
            total_hits=total_count,
            duration_ms=duration_ms,
            scope_id=scope_id,
            memory_type=memory_type,
            has_provenance_filters=bool(cognito_user_id or slack_user_id or slack_channel_id or rfp_id or source),
        )
        
        return memories
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
        log.warning("opensearch_search_failed", error=str(e), duration_ms=duration_ms)
        return []
