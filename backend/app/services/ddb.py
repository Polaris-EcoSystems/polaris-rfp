from __future__ import annotations

"""Backward-compatible DynamoDB helpers.

This module previously held the canonical DynamoDB helpers for the service.
We now have a more robust abstraction in `app.db.dynamodb`, but some modules
still import `app.services.ddb`.

Keep this file as a small compatibility shim to avoid boot failures, and to
provide a single migration point.

"""

from typing import Any

from ..db.dynamodb.table import get_main_table


def put_item(item: dict[str, Any]):
    return get_main_table().put_item(item=item)


def get_item(pk: str, sk: str) -> dict[str, Any] | None:
    return get_main_table().get_item(key={"pk": pk, "sk": sk})


def delete_item(pk: str, sk: str):
    return get_main_table().delete_item(key={"pk": pk, "sk": sk})


def table():
    # Compatibility: return the underlying boto3 Table resource.
    return get_main_table()._table
