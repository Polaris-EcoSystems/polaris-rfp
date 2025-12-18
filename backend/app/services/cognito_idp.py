from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3

from ..settings import settings


@lru_cache(maxsize=1)
def client():
    return boto3.client("cognito-idp", region_name=settings.aws_region)


def sign_up(*, email: str, password: str, preferred_username: str | None = None) -> dict[str, Any]:
    attrs = [{"Name": "email", "Value": email}]
    if preferred_username:
        attrs.append({"Name": "preferred_username", "Value": preferred_username})

    return client().sign_up(
        ClientId=settings.cognito_client_id,
        Username=email,
        Password=password,
        UserAttributes=attrs,
    )


def admin_confirm_sign_up(*, user_pool_id: str, email: str) -> None:
    client().admin_confirm_sign_up(UserPoolId=user_pool_id, Username=email)


def initiate_auth(*, email: str, password: str) -> dict[str, Any]:
    return client().initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        ClientId=settings.cognito_client_id,
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )


def admin_set_password(*, user_pool_id: str, email: str, new_password: str) -> None:
    client().admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=email,
        Password=new_password,
        Permanent=True,
    )
