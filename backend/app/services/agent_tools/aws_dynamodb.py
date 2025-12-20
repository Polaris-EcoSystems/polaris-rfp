from __future__ import annotations

from typing import Any

from ...settings import settings
from .allowlist import parse_csv, uniq, is_allowed_exact
from .aws_clients import dynamodb_client


def _allowed_tables() -> list[str]:
    explicit = uniq(parse_csv(settings.agent_allowed_ddb_tables))
    if explicit:
        return explicit
    # Default: allow only the app's primary table.
    main = str(settings.ddb_table_name or "").strip()
    return [main] if main else []


def _require_allowed_table(table_name: str) -> str:
    tn = str(table_name or "").strip()
    if not tn:
        raise ValueError("missing_tableName")
    allowed = _allowed_tables()
    if allowed and not is_allowed_exact(tn, allowed):
        raise ValueError("table_not_allowed")
    if not allowed:
        raise ValueError("no_tables_allowed")
    return tn


def describe_table(*, table_name: str) -> dict[str, Any]:
    tn = _require_allowed_table(table_name)
    resp = dynamodb_client().describe_table(TableName=tn)
    t = (resp or {}).get("Table") if isinstance(resp, dict) else None
    table: dict[str, Any] = t if isinstance(t, dict) else {}
    # Trim to a compact, safe subset.
    gsis_raw = table.get("GlobalSecondaryIndexes")
    gsis: list[Any] = gsis_raw if isinstance(gsis_raw, list) else []
    out = {
        "TableName": table.get("TableName"),
        "TableStatus": table.get("TableStatus"),
        "ItemCount": table.get("ItemCount"),
        "TableSizeBytes": table.get("TableSizeBytes"),
        "BillingModeSummary": table.get("BillingModeSummary"),
        "KeySchema": table.get("KeySchema"),
        "AttributeDefinitions": table.get("AttributeDefinitions"),
        "GlobalSecondaryIndexes": [
            {
                "IndexName": (g or {}).get("IndexName"),
                "KeySchema": (g or {}).get("KeySchema"),
                "Projection": (g or {}).get("Projection"),
                "IndexStatus": (g or {}).get("IndexStatus"),
            }
            for g in gsis[:10]
        ],
    }
    return {"ok": True, "table": out}


def list_tables(*, limit: int = 20) -> dict[str, Any]:
    # We do not allow unfettered listing unless an allowlist is explicitly set.
    allowed = _allowed_tables()
    if not allowed:
        return {"ok": False, "error": "no_tables_allowed"}
    lim = max(1, min(100, int(limit or 20)))
    # If allowlist is set, just return it (most useful for agents).
    return {"ok": True, "tables": allowed[:lim]}

