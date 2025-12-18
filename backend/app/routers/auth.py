from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from ..services import cognito_idp
from ..services.password_reset import consume_password_reset, create_password_reset
from ..settings import settings

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)


class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=6)


class ResetRequest(BaseModel):
    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)


@router.post("/login")
def login(body: LoginRequest):
    if not settings.cognito_client_id or not settings.cognito_user_pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")

    email = body.username.strip()
    try:
        resp = cognito_idp.initiate_auth(email=email, password=body.password)
        auth = resp.get("AuthenticationResult") or {}
        # Use IdToken as the bearer token to validate user identity (/me needs email claim).
        id_token = auth.get("IdToken")
        if not id_token:
            raise RuntimeError("No IdToken returned")
        return {"access_token": id_token, "token_type": "bearer", "expires_in": "24h"}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/signup", status_code=201)
def signup(body: SignupRequest):
    if not settings.cognito_client_id or not settings.cognito_user_pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")

    email = str(body.email).strip().lower()
    try:
        cognito_idp.sign_up(
            email=email,
            password=body.password,
            preferred_username=body.username.strip(),
        )
        # Compatibility: auto-confirm + auto-login so the UI behavior matches legacy Node.
        cognito_idp.admin_confirm_sign_up(user_pool_id=settings.cognito_user_pool_id, email=email)
        login_resp = cognito_idp.initiate_auth(email=email, password=body.password)
        auth = login_resp.get("AuthenticationResult") or {}
        id_token = auth.get("IdToken")
        if not id_token:
            raise RuntimeError("No IdToken returned")
        return {
            "message": "User created successfully",
            "access_token": id_token,
            "token_type": "bearer",
            "expires_in": "24h",
            "user": {"username": body.username.strip(), "email": email},
        }
    except Exception as e:
        # Keep legacy error shape
        raise HTTPException(status_code=400, detail="User already exists")


@router.post("/request-password-reset")
def request_password_reset(body: dict):
    # Compatibility: always 200 in production to avoid user enumeration.
    raw_email = str((body or {}).get("email") or "").strip().lower()
    if not raw_email or "@" not in raw_email:
        raise HTTPException(status_code=400, detail="Valid email is required")

    try:
        token = create_password_reset(raw_email)
        frontend_base = settings.frontend_base_url
        reset_url = f"{frontend_base}/reset-password/{token.token}"

        if settings.environment == "production":
            # TODO: send via SES (best-effort) and do not return resetUrl
            return {"ok": True}
        return {"ok": True, "resetUrl": reset_url}
    except Exception:
        # If DynamoDB isn't configured (or anything fails), keep enumeration-safe behavior.
        return (
            {"ok": True}
            if settings.environment == "production"
            else {"ok": True, "resetUrl": None}
        )


@router.post("/reset-password")
def reset_password(body: ResetRequest):
    if not settings.cognito_user_pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")

    pr = consume_password_reset(body.token)
    if not pr:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    try:
        cognito_idp.admin_set_password(
            user_pool_id=settings.cognito_user_pool_id,
            email=pr.email,
            new_password=body.password,
        )
        login_resp = cognito_idp.initiate_auth(email=pr.email, password=body.password)
        auth = login_resp.get("AuthenticationResult") or {}
        id_token = auth.get("IdToken")
        if not id_token:
            raise RuntimeError("No IdToken returned")
        return {"ok": True, "access_token": id_token, "token_type": "bearer", "expires_in": "24h"}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")


@router.get("/me")
def me(request: Request):
    # require_auth sets request.state.user
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"username": user.username, "email": user.email}
