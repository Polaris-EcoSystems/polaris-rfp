from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3

from app.settings import settings


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


def generate_password() -> str:
    """
    Generates a strong password that satisfies common Cognito password policies.
    Used internally for behind-the-scenes user creation/confirmation.
    """
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    # Ensure we include at least one lower, one upper, and one number.
    core = "".join(secrets.choice(alphabet) for _ in range(24))
    return core + "Aa1"


def admin_create_user(
    *,
    user_pool_id: str,
    email: str,
    preferred_username: str | None = None,
) -> dict[str, Any]:
    # AdminCreateUser requires a TemporaryPassword even if we suppress messages.
    tmp = generate_password()

    attrs = [{"Name": "email", "Value": email}]
    if preferred_username:
        attrs.append({"Name": "preferred_username", "Value": preferred_username})

    return client().admin_create_user(
        UserPoolId=user_pool_id,
        Username=email,
        TemporaryPassword=tmp,
        MessageAction="SUPPRESS",
        UserAttributes=attrs,
    )


def initiate_custom_auth(
    *,
    email: str,
    client_metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Starts Cognito CUSTOM_AUTH flow (used for magic-link sign in).
    ClientMetadata is forwarded to Lambda triggers.
    """
    # IMPORTANT: ClientMetadata is only reliably forwarded to triggers for *Admin* auth APIs.
    return client().admin_initiate_auth(
        UserPoolId=settings.cognito_user_pool_id,
        ClientId=settings.cognito_client_id,
        AuthFlow="CUSTOM_AUTH",
        AuthParameters={"USERNAME": email},
        ClientMetadata=client_metadata or {},
    )


def respond_to_custom_challenge(
    *,
    session: str,
    email: str,
    answer: str,
) -> dict[str, Any]:
    return client().admin_respond_to_auth_challenge(
        UserPoolId=settings.cognito_user_pool_id,
        ClientId=settings.cognito_client_id,
        ChallengeName="CUSTOM_CHALLENGE",
        Session=session,
        ChallengeResponses={"USERNAME": email, "ANSWER": answer},
    )


def refresh_tokens(*, refresh_token: str) -> dict[str, Any]:
    """
    Refresh tokens using the app client's refresh token flow.
    Returns the raw Cognito response containing AuthenticationResult.
    """
    rt = str(refresh_token or "").strip()
    if not rt:
        raise ValueError("refresh_token is required")
    return client().admin_initiate_auth(
        UserPoolId=settings.cognito_user_pool_id,
        ClientId=settings.cognito_client_id,
        AuthFlow="REFRESH_TOKEN_AUTH",
        AuthParameters={"REFRESH_TOKEN": rt},
    )


def describe_user_pool(*, user_pool_id: str) -> dict[str, Any]:
    """
    Returns the user pool metadata including the attribute schema.
    Used by the Profile page to know which attributes are mutable/required.
    """
    return client().describe_user_pool(UserPoolId=user_pool_id)


def admin_get_user(*, user_pool_id: str, username: str) -> dict[str, Any]:
    """
    Admin read for a specific user. `username` should be the Cognito username
    (often the user's email when UsernameAttributes include email).
    """
    return client().admin_get_user(UserPoolId=user_pool_id, Username=username)


def admin_update_user_attributes(
    *,
    user_pool_id: str,
    username: str,
    attributes: dict[str, str],
) -> dict[str, Any]:
    user_attributes = [{"Name": k, "Value": v} for k, v in (attributes or {}).items()]
    return client().admin_update_user_attributes(
        UserPoolId=user_pool_id,
        Username=username,
        UserAttributes=user_attributes,
    )


def admin_delete_user_attributes(
    *,
    user_pool_id: str,
    username: str,
    attribute_names: list[str],
) -> dict[str, Any]:
    return client().admin_delete_user_attributes(
        UserPoolId=user_pool_id,
        Username=username,
        UserAttributeNames=list(attribute_names or []),
    )
