from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3

from ..settings import settings


@lru_cache(maxsize=1)
def _ddb_resource():
    return boto3.resource("dynamodb", region_name=settings.aws_region)


def table():
    if not settings.ddb_table_name:
        raise RuntimeError("DDB_TABLE_NAME is not set")
    return _ddb_resource().Table(settings.ddb_table_name)


def put_item(item: dict[str, Any]):
    return table().put_item(Item=item)


def get_item(pk: str, sk: str) -> dict[str, Any] | None:
    resp = table().get_item(Key={"pk": pk, "sk": sk})
    return resp.get("Item")


def delete_item(pk: str, sk: str):
    return table().delete_item(Key={"pk": pk, "sk": sk})
