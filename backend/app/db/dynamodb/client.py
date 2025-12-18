from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config

from ...settings import settings


@lru_cache(maxsize=1)
def botocore_config() -> Config:
    # Keep botocore retries enabled (adaptive is best-effort); we still do an app-layer
    # retry for a narrow set of known-safe transient failures.
    return Config(
        retries={"max_attempts": 10, "mode": "adaptive"},
        connect_timeout=2,
        read_timeout=10,
    )


@lru_cache(maxsize=1)
def dynamodb_resource():
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        config=botocore_config(),
    )


@lru_cache(maxsize=1)
def dynamodb_client():
    return boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        config=botocore_config(),
    )


def table_resource(table_name: str):
    return dynamodb_resource().Table(table_name)
