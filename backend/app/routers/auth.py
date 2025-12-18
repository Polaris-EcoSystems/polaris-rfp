from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
import base64
import os

from pydantic import BaseModel, EmailStr, Field

from ..services import cognito_idp
from ..services.magic_links_repo import (
    delete_magic_session,
    delete_magic_session_for_email,
    get_magic_session,
    get_latest_magic_session_for_email,
    put_magic_session,
    put_magic_session_for_email,
)
from ..services.password_reset import consume_password_reset, create_password_reset
from ..settings import settings

router = APIRouter(tags=["auth"])


def _sanitize_return_to(raw: str | None) -> str:
    """
    Keep returnTo as a safe in-app path.
    - Must be a relative path starting with "/"
    - Reject absolute / protocol-relative URLs
    """
    val = str(raw or "/").strip() or "/"
    # single-line only (avoid header injection / log junk)
    val = val.splitlines()[0].strip() or "/"

    low = val.lower()
    if "://" in low or low.startswith("//"):
        return "/"
    if not val.startswith("/"):
        return "/"
    # Prevent pathological lengths
    if len(val) > 2048:
        return "/"
    return val


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
    # Password login is deprecated in favor of magic-link auth.
    raise HTTPException(status_code=400, detail="Use magic link authentication")


@router.post("/signup", status_code=201)
def signup(body: SignupRequest):
    # Password signup is deprecated in favor of magic-link auth.
    raise HTTPException(status_code=400, detail="Use magic link authentication")


class MagicLinkRequest(BaseModel):
    email: EmailStr
    username: str | None = None
    returnTo: str | None = None


@router.post("/magic-link/request")
def request_magic_link(body: MagicLinkRequest):
    if not settings.cognito_client_id or not settings.cognito_user_pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")
    if not settings.magic_link_table_name:
        raise HTTPException(status_code=500, detail="Magic link is not configured")

    email = str(body.email).strip().lower()
    preferred_username = str(body.username).strip() if body.username else None
    return_to = _sanitize_return_to(body.returnTo)

    # Create a short opaque id used to look up the Cognito Session server-side.
    magic_id = base64.urlsafe_b64encode(os.urandom(24)).decode("ascii").rstrip("=")

    # Ensure the user exists (create on first login = signup + login)
    try:
        u = cognito_idp.admin_get_user(
            user_pool_id=settings.cognito_user_pool_id, username=email
        )
        status = str(u.get("UserStatus") or "")
        # Users created via AdminCreateUser can be stuck in FORCE_CHANGE_PASSWORD, which blocks auth flows.
        if status == "FORCE_CHANGE_PASSWORD":
            try:
                cognito_idp.admin_set_password(
                    user_pool_id=settings.cognito_user_pool_id,
                    email=email,
                    new_password=cognito_idp.generate_password(),
                )
            except Exception as e:
                print("magic-link: failed to convert FORCE_CHANGE_PASSWORD user:", repr(e))
    except Exception:
        # Create a confirmed user without a user-visible password.
        # We sign up with a random password and admin-confirm.
        try:
            pw = cognito_idp.generate_password()
            cognito_idp.sign_up(
                email=email,
                password=pw,
                preferred_username=preferred_username,
            )
            cognito_idp.admin_confirm_sign_up(
                user_pool_id=settings.cognito_user_pool_id, email=email
            )
        except Exception as e:
            # Enumeration-safe: still return ok (but log for operators)
            print("magic-link: user create/confirm failed:", repr(e))
            return {"ok": True}

    # Start custom auth; triggers will email the link.
    try:
        resp = cognito_idp.initiate_custom_auth(
            email=email,
            client_metadata={
                "magicId": magic_id,
                "returnTo": return_to,
                "frontendBaseUrl": settings.frontend_base_url,
            },
        )
        session = str(resp.get("Session") or "")
        if not session:
            # Still return ok; user can retry
            print("magic-link: initiate_custom_auth returned no Session")
            return {"ok": True}

        try:
            dom = email.split("@", 1)[1] if "@" in email else ""
            print(
                "magic-link: initiated",
                {"emailDomain": dom, "magicIdPrefix": magic_id[:6], "hasSession": True},
            )
        except Exception:
            pass

        put_magic_session(
            magic_id=magic_id,
            email=email,
            session=session,
            return_to=return_to,
            ttl_seconds=600,
        )
        put_magic_session_for_email(
            email=email,
            session=session,
            return_to=return_to,
            ttl_seconds=600,
        )
        return {"ok": True}
    except Exception as e:
        print("magic-link: initiate_custom_auth failed:", repr(e))
        # Enumeration-safe
        return {"ok": True}


class MagicLinkVerify(BaseModel):
    # Legacy: when mid is present on the link
    magicId: str | None = None
    # Preferred: email is present on the link
    email: EmailStr | None = None
    code: str = Field(..., min_length=4)


@router.post("/magic-link/verify")
def verify_magic_link(body: MagicLinkVerify):
    if not settings.cognito_client_id or not settings.cognito_user_pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")
    if not settings.magic_link_table_name:
        raise HTTPException(status_code=500, detail="Magic link is not configured")

    magic_id = str(body.magicId or "").strip()
    code = str(body.code).strip()

    sess = None
    email = None
    sk = None

    # Prefer email-based lookup (works even if Cognito triggers can't include magicId)
    if body.email:
        email = str(body.email).strip().lower()
        sess = get_latest_magic_session_for_email(email=email)
        if sess:
            sk = str(sess.get("sk") or "")
    elif magic_id:
        sess = get_magic_session(magic_id=magic_id)
        email = str((sess or {}).get("email") or "").strip().lower() if sess else None

    if not sess or not email:
        raise HTTPException(status_code=400, detail="Invalid or expired magic link")

    session = str(sess.get("session") or "")
    return_to = str(sess.get("returnTo") or "/")
    if not email or not session:
        if sk:
            delete_magic_session_for_email(email=email, sk=sk)
        elif magic_id:
            delete_magic_session(magic_id=magic_id)
        raise HTTPException(status_code=400, detail="Invalid or expired magic link")

    try:
        resp = cognito_idp.respond_to_custom_challenge(
            session=session,
            email=email,
            answer=code,
        )
        auth = resp.get("AuthenticationResult") or {}
        id_token = auth.get("IdToken")
        if not id_token:
            raise RuntimeError("No IdToken returned")
        if sk:
            delete_magic_session_for_email(email=email, sk=sk)
        elif magic_id:
            delete_magic_session(magic_id=magic_id)
        return {
            "access_token": id_token,
            "token_type": "bearer",
            "expires_in": "24h",
            "returnTo": return_to,
        }
    except Exception:
        # Don't leak if code incorrect; keep short
        raise HTTPException(status_code=400, detail="Invalid or expired magic link")


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
