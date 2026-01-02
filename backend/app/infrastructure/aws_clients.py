from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config

from app.settings import settings


@lru_cache(maxsize=1)
def botocore_config() -> Config:
    # Conservative timeouts; adaptive retries.
    return Config(
        retries={"max_attempts": 10, "mode": "adaptive"},
        connect_timeout=2,
        read_timeout=12,
    )


@lru_cache(maxsize=1)
def s3_client():
    return boto3.client("s3", region_name=settings.aws_region, config=botocore_config())


@lru_cache(maxsize=1)
def sqs_client():
    return boto3.client("sqs", region_name=settings.aws_region, config=botocore_config())


@lru_cache(maxsize=1)
def ecs_client():
    return boto3.client("ecs", region_name=settings.aws_region, config=botocore_config())


@lru_cache(maxsize=1)
def logs_client():
    return boto3.client("logs", region_name=settings.aws_region, config=botocore_config())


@lru_cache(maxsize=1)
def secretsmanager_client():
    return boto3.client("secretsmanager", region_name=settings.aws_region, config=botocore_config())


@lru_cache(maxsize=1)
def cognito_idp_client(region: str | None = None):
    reg = str(region or settings.cognito_region or settings.aws_region or "us-east-1").strip() or "us-east-1"
    return boto3.client("cognito-idp", region_name=reg, config=botocore_config())


@lru_cache(maxsize=1)
def dynamodb_client():
    return boto3.client("dynamodb", region_name=settings.aws_region, config=botocore_config())


