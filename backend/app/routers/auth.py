from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
import base64
import os
import time

from pydantic import BaseModel, EmailStr, Field
from botocore.exceptions import ClientError

from ..observability.logging import get_logger
from ..services import cognito_idp
from ..services.magic_links_repo import (
    delete_magic_session,
    delete_magic_session_for_email,
    get_magic_session,
    get_latest_magic_session_for_email,
    get_recent_magic_sessions_for_email,
    put_magic_session,
    put_magic_session_for_email,
)
from ..services.password_reset import consume_password_reset, create_password_reset
from ..services.sessions_repo import (
    cache_access_token,
    delete_session,
    get_session,
    list_sessions_for_user,
    put_session,
    release_refresh_lock,
    touch_session,
    try_acquire_refresh_lock,
    try_get_recent_cached_access_token,
)
from ..services.token_crypto import decrypt_string, encrypt_string
from ..settings import settings
from ..auth.cognito import verify_bearer_token

router = APIRouter(tags=["auth"])
log = get_logger("auth")

def _is_allowed_email(email: str) -> bool:
    raw = str(email or "").strip().lower()
    if not raw or "@" not in raw:
        return False
    dom = raw.split("@", 1)[1]
    allowed = str(settings.allowed_email_domain or "").strip().lower()
    return bool(allowed) and dom == allowed

def _reject_if_disallowed_email(email: str) -> None:
    if _is_allowed_email(email):
        return
    raise HTTPException(
        status_code=400,
        detail=f"Email must be a @{settings.allowed_email_domain} address",
    )


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
    _reject_if_disallowed_email(email)
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
        # If the user exists but is not confirmed, confirm them so custom auth works.
        # This can happen if a user was created via a different flow or left UNCONFIRMED.
        if status == "UNCONFIRMED":
            try:
                cognito_idp.admin_confirm_sign_up(
                    user_pool_id=settings.cognito_user_pool_id, email=email
                )
            except Exception as e:
                # Enumeration-safe: still return ok (but log for operators)
                log.warning(
                    "magic_link_user_confirm_failed",
                    email_domain=email.split("@", 1)[1] if "@" in email else None,
                    error=str(e),
                )
        # Users created via AdminCreateUser can be stuck in FORCE_CHANGE_PASSWORD, which blocks auth flows.
        if status == "FORCE_CHANGE_PASSWORD":
            try:
                cognito_idp.admin_set_password(
                    user_pool_id=settings.cognito_user_pool_id,
                    email=email,
                    new_password=cognito_idp.generate_password(),
                )
            except Exception as e:
                log.warning(
                    "magic_link_force_change_password_convert_failed",
                    email_domain=email.split("@", 1)[1] if "@" in email else None,
                    error=str(e),
                )
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
            log.warning(
                "magic_link_user_create_or_confirm_failed",
                email_domain=email.split("@", 1)[1] if "@" in email else None,
                error=str(e),
            )
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
            log.warning(
                "magic_link_initiate_custom_auth_missing_session",
                email_domain=email.split("@", 1)[1] if "@" in email else None,
                magic_id_prefix=magic_id[:6],
            )
            return {"ok": True}

        try:
            dom = email.split("@", 1)[1] if "@" in email else ""
            log.info(
                "magic_link_initiated",
                email_domain=dom or None,
                magic_id_prefix=magic_id[:6],
                has_session=True,
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
        log.warning(
            "magic_link_initiate_custom_auth_failed",
            email_domain=email.split("@", 1)[1] if "@" in email else None,
            magic_id_prefix=magic_id[:6],
            error=str(e),
        )
        # Enumeration-safe
        return {"ok": True}


class MagicLinkVerify(BaseModel):
    # Legacy: when mid is present on the link
    magicId: str | None = None
    # Preferred: email is present on the link
    email: EmailStr | None = None
    code: str = Field(..., min_length=4)
    remember: bool | None = None


@router.post("/magic-link/verify")
def verify_magic_link(body: MagicLinkVerify, request: Request):
    if not settings.cognito_client_id or not settings.cognito_user_pool_id:
        raise HTTPException(status_code=500, detail="Cognito is not configured")
    if not settings.magic_link_table_name:
        raise HTTPException(status_code=500, detail="Magic link is not configured")

    magic_id = str(body.magicId or "").strip()
    code = str(body.code).strip()

    # Prefer magicId when present (pins to a specific Cognito Session).
    # If not present (email-only links), we may have multiple sessions for an email.
    email: str | None = None
    candidates: list[dict] = []
    magic_item: dict | None = None

    if magic_id:
        magic_item = get_magic_session(magic_id=magic_id)
        email = (
            str((magic_item or {}).get("email") or "").strip().lower()
            if magic_item
            else None
        )
        if email:
            _reject_if_disallowed_email(email)
        # If we have an email, also allow fallbacks to email sessions (helps if MAGIC# was pruned).
        if email:
            candidates = get_recent_magic_sessions_for_email(email=email, limit=5)
        if magic_item:
            candidates = [magic_item, *candidates]
    elif body.email:
        email = str(body.email).strip().lower()
        _reject_if_disallowed_email(email)
        candidates = get_recent_magic_sessions_for_email(email=email, limit=5)

    if not candidates or not email:
        raise HTTPException(status_code=400, detail="Invalid or expired magic link")

    # Try each candidate session until Cognito accepts the challenge.
    last_err: Exception | None = None
    for idx, sess in enumerate(candidates):
        session = str((sess or {}).get("session") or "")
        return_to = str((sess or {}).get("returnTo") or "/")
        if not session:
            continue

        try:
            def _respond() -> dict:
                return cognito_idp.respond_to_custom_challenge(
                    session=session,
                    email=email,
                    answer=code,
                )

            try:
                resp = _respond()
            except Exception as e:
                # If the user exists but is not confirmed, Cognito will reject the challenge.
                # Confirm and retry once (does not leak code validity; still returns generic error on failure).
                if type(e).__name__ == "UserNotConfirmedException" or "UserNotConfirmedException" in str(
                    e
                ):
                    try:
                        cognito_idp.admin_confirm_sign_up(
                            user_pool_id=settings.cognito_user_pool_id, email=email
                        )
                        resp = _respond()
                    except Exception:
                        raise e
                else:
                    raise e
            auth = resp.get("AuthenticationResult") or {}
            id_token = auth.get("IdToken")
            access_token = auth.get("AccessToken")
            refresh_token = auth.get("RefreshToken")
            if not access_token:
                raise RuntimeError("No AccessToken returned")
            if not id_token:
                raise RuntimeError("No IdToken returned")

            # Cleanup the specific consumed session(s).
            sk = str((sess or {}).get("sk") or "")
            if sk and email:
                delete_magic_session_for_email(email=email, sk=sk)
            if magic_id:
                delete_magic_session(magic_id=magic_id)

            # Create a refreshable server-side session when Cognito provides a refresh token.
            # This enables silent refresh without exposing refresh tokens to the browser.
            sid: str | None = None
            session_expires_at: int | None = None
            try:
                if refresh_token:
                    raw_sid = base64.urlsafe_b64encode(os.urandom(24)).decode("ascii").rstrip("=")
                    sid = raw_sid

                    remember = bool(body.remember) if body.remember is not None else True
                    ttl_seconds = 60 * 60 * 24 * 30 if remember else 60 * 60 * 8
                    session_expires_at = int(time.time()) + int(ttl_seconds)

                    # Best-effort: attach identifying info for debugging/auditing.
                    sub = None
                    em = None
                    try:
                        # Prefer id token for user info at login time (it includes email/name).
                        vu = verify_bearer_token(str(id_token))
                        sub = getattr(vu, "sub", None)
                        em = getattr(vu, "email", None)
                    except Exception:
                        pass

                    ua = request.headers.get("user-agent") or request.headers.get("User-Agent") or None
                    ip = None
                    try:
                        xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
                        if xff:
                            ip = str(xff).split(",")[0].strip()
                        else:
                            ip = getattr(getattr(request, "client", None), "host", None)
                    except Exception:
                        ip = None

                    put_session(
                        sid=sid,
                        refresh_token_enc=str(encrypt_string(str(refresh_token)) or ""),
                        expires_at=session_expires_at,
                        session_kind="remember" if remember else "normal",
                        sub=str(sub) if sub else None,
                        email=str(em) if em else (str(email) if email else None),
                        user_agent=ua,
                        ip=str(ip) if ip else None,
                    )

                    # Enforce multi-device cap (newest-first; keep newest 5).
                    try:
                        if sub:
                            items = list_sessions_for_user(sub=str(sub), limit=25)
                            if len(items) > 5:
                                # items are newest-first; delete overflow (oldest).
                                for it in items[5:]:
                                    try:
                                        old_sid = str(it.get("sid") or "")
                                        if old_sid and old_sid != sid:
                                            delete_session(sid=old_sid)
                                    except Exception:
                                        continue
                    except Exception:
                        # never block login
                        pass
            except Exception as e:
                # Do not fail login if session persistence fails; log for operators.
                try:
                    log.warning(
                        "session_persist_failed",
                        error_type=type(e).__name__,
                        error=str(e)[:300] if str(e) else None,
                    )
                except Exception:
                    pass

            return {
                # API auth token (preferred): Cognito AccessToken
                "access_token": access_token,
                "token_type": "bearer",
                # For backwards compatibility, keep a human-ish string.
                "expires_in": "24h",
                "returnTo": return_to,
                "sid": sid,
                "session_expires_at": session_expires_at,
            }
        except Exception as e:
            last_err = e
            # Safe operator logs (no code leakage)
            try:
                dom = email.split("@", 1)[1] if email and "@" in email else None
                log.info(
                    "magic_link_verify_cognito_rejected",
                    email_domain=dom,
                    magic_id_prefix=magic_id[:6] if magic_id else None,
                    attempt_index=idx,
                    attempt_count=len(candidates),
                    error_type=type(e).__name__,
                    error=str(e)[:300] if str(e) else None,
                )
            except Exception:
                pass
            continue

    # Don't leak whether code was wrong vs session mismatch.
    # But do emit a final operator log so we can see systemic issues.
    try:
        dom = email.split("@", 1)[1] if email and "@" in email else None
        log.warning(
            "magic_link_verify_failed",
            email_domain=dom,
            magic_id_prefix=magic_id[:6] if magic_id else None,
            attempt_count=len(candidates),
            last_error_type=type(last_err).__name__ if last_err else None,
        )
    except Exception:
        pass
    raise HTTPException(status_code=400, detail="Invalid or expired magic link")


@router.post("/request-password-reset")
def request_password_reset(body: dict):
    # Compatibility: always 200 in production to avoid user enumeration.
    raw_email = str((body or {}).get("email") or "").strip().lower()
    if not raw_email or "@" not in raw_email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    _reject_if_disallowed_email(raw_email)

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

    claims = getattr(user, "claims", {}) or {}
    given_name = str(claims.get("given_name") or "").strip() or None
    family_name = str(claims.get("family_name") or "").strip() or None
    name = str(claims.get("name") or "").strip() or None

    display_name = None
    if name:
        display_name = name
    else:
        parts = [p for p in [given_name, family_name] if p]
        if parts:
            display_name = " ".join(parts)

    return {
        "sub": getattr(user, "sub", None),
        "username": user.username,
        "email": user.email,
        "given_name": given_name,
        "family_name": family_name,
        "display_name": display_name or user.username,
    }


@router.post("/session/refresh")
def refresh_session(request: Request):
    """
    Refresh session tokens using a server-side stored refresh token.

    Security model:
    - The browser never sees the refresh token.
    - This endpoint is intended to be called by the Next.js BFF.
    """
    sid = (
        request.headers.get("x-session-id")
        or request.headers.get("X-Session-Id")
        or request.headers.get("x-sessionid")
        or ""
    ).strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Missing session id")

    item = get_session(sid=sid)
    if not item:
        raise HTTPException(status_code=401, detail="Unauthorized")

    now = int(time.time())
    try:
        if int(item.get("expiresAt") or 0) <= now:
            # Absolute session window expired.
            try:
                delete_session(sid=sid)
            except Exception:
                pass
            raise HTTPException(status_code=401, detail="Unauthorized")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

    rt_enc = str(item.get("refreshTokenEnc") or "")
    rt = decrypt_string(rt_enc)
    if not rt:
        # Can't refresh without a refresh token.
        try:
            delete_session(sid=sid)
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Unauthorized")

    acquired_lock = False
    try:
        # Stampede protection:
        # - If another request is already refreshing, try to reuse the newly-minted token.
        # - Otherwise acquire a short-lived lock and perform the refresh.
        if not try_acquire_refresh_lock(sid=sid, lock_seconds=10):
            # Wait briefly for the in-flight refresh to complete.
            for _ in range(10):
                tok = try_get_recent_cached_access_token(sid=sid, max_age_seconds=120)
                if tok:
                    touch_session(sid=sid, last_seen_at=now)
                    return {
                        "ok": True,
                        "access_token": tok,
                        "token_type": "bearer",
                        "session_expires_at": int(item.get("expiresAt") or 0),
                    }
                time.sleep(0.15)

            # As a fallback, if we have *any* cached token, return it to avoid hard failures.
            tok = try_get_recent_cached_access_token(sid=sid, max_age_seconds=60 * 10)
            if tok:
                touch_session(sid=sid, last_seen_at=now)
                return {
                    "ok": True,
                    "access_token": tok,
                    "token_type": "bearer",
                    "session_expires_at": int(item.get("expiresAt") or 0),
                }

        acquired_lock = True
        resp = cognito_idp.refresh_tokens(refresh_token=str(rt))
        auth = resp.get("AuthenticationResult") or {}
        access_token = auth.get("AccessToken")
        if not access_token:
            raise RuntimeError("No AccessToken returned")

        new_rt = auth.get("RefreshToken")
        if new_rt:
            touch_session(
                sid=sid,
                refresh_token_enc=str(encrypt_string(str(new_rt)) or ""),
                last_seen_at=now,
            )
        else:
            touch_session(sid=sid, last_seen_at=now)

        # Cache the new token so concurrent refresh callers can reuse it without
        # hitting Cognito.
        cache_access_token(sid=sid, access_token=str(access_token))

        return {
            "ok": True,
            "access_token": access_token,
            "token_type": "bearer",
            "session_expires_at": int(item.get("expiresAt") or 0),
        }
    except HTTPException:
        raise
    except ClientError as e:
        # Distinguish between auth failure vs transient Cognito errors.
        code = ""
        try:
            code = str((e.response or {}).get("Error", {}).get("Code") or "").strip()
        except Exception:
            code = ""

        # Always release lock if we acquired it.
        if acquired_lock:
            try:
                release_refresh_lock(sid=sid)
            except Exception:
                pass

        if code in ("NotAuthorizedException", "InvalidRefreshTokenException"):
            # Refresh token invalid/expired/revoked -> delete session.
            try:
                delete_session(sid=sid)
            except Exception:
                pass
            raise HTTPException(status_code=401, detail="Unauthorized")

        # Transient/unavailable: keep session and tell caller to retry.
        if code in ("TooManyRequestsException", "ThrottlingException", "ServiceUnavailableException"):
            raise HTTPException(status_code=503, detail="Auth refresh temporarily unavailable")

        # Unknown ClientError: treat as transient to avoid logging users out.
        raise HTTPException(status_code=503, detail="Auth refresh temporarily unavailable")
    except Exception as e:
        # Unknown failures: do not delete session; return 503 to avoid surprise logouts.
        if acquired_lock:
            try:
                release_refresh_lock(sid=sid)
            except Exception:
                pass
        raise HTTPException(status_code=503, detail="Auth refresh temporarily unavailable")
    finally:
        # Best-effort: ensure lock is released when we acquired it.
        if acquired_lock:
            try:
                release_refresh_lock(sid=sid)
            except Exception:
                pass


@router.post("/session/logout")
def logout_session(request: Request):
    sid = (
        request.headers.get("x-session-id")
        or request.headers.get("X-Session-Id")
        or request.headers.get("x-sessionid")
        or ""
    ).strip()
    if sid:
        try:
            delete_session(sid=sid)
        except Exception:
            pass
    return {"ok": True}


class RevokeSessionRequest(BaseModel):
    sid: str = Field(..., min_length=8)


@router.get("/sessions")
def list_sessions(request: Request):
    user = getattr(request.state, "user", None)
    sub = getattr(user, "sub", None)
    if not sub:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Optional: BFF can pass current sid to mark it in the response.
    current_sid = (
        request.headers.get("x-session-id")
        or request.headers.get("X-Session-Id")
        or ""
    ).strip()

    items = list_sessions_for_user(sub=str(sub), limit=25)
    out: list[dict[str, Any]] = []
    for it in items:
        sid = str(it.get("sid") or "")
        out.append(
            {
                "sid": sid,
                "sessionKind": str(it.get("sessionKind") or "normal"),
                "createdAt": int(it.get("createdAt") or 0),
                "lastSeenAt": int(it.get("lastSeenAt") or 0),
                "ipPrefix": it.get("ipPrefix") or None,
                "userAgent": it.get("userAgent") or None,
                "isCurrent": bool(current_sid and sid and sid == current_sid),
            }
        )
    return {"data": out}


@router.post("/sessions/revoke")
def revoke_session(body: RevokeSessionRequest, request: Request):
    user = getattr(request.state, "user", None)
    sub = getattr(user, "sub", None)
    if not sub:
        raise HTTPException(status_code=401, detail="Unauthorized")

    sid = str(body.sid or "").strip()
    it = get_session(sid=sid)
    if not it:
        return {"ok": True}
    if str(it.get("sub") or "") != str(sub):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        delete_session(sid=sid)
    except Exception:
        pass
    return {"ok": True}


@router.post("/sessions/revoke-all")
def revoke_all_sessions(request: Request):
    user = getattr(request.state, "user", None)
    sub = getattr(user, "sub", None)
    if not sub:
        raise HTTPException(status_code=401, detail="Unauthorized")

    keep_sid = (
        request.headers.get("x-session-id")
        or request.headers.get("X-Session-Id")
        or ""
    ).strip()

    items = list_sessions_for_user(sub=str(sub), limit=25)
    for it in items:
        sid = str(it.get("sid") or "").strip()
        if not sid:
            continue
        if keep_sid and sid == keep_sid:
            continue
        try:
            delete_session(sid=sid)
        except Exception:
            continue
    return {"ok": True}
