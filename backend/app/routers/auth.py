from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["auth"])


@router.post("/login")
def login():
    # TODO: Cognito InitiateAuth (USER_PASSWORD_AUTH)
    return {"error": "Not implemented"}


@router.post("/signup")
def signup():
    # TODO: Cognito SignUp
    return {"error": "Not implemented"}


@router.post("/request-password-reset")
def request_password_reset():
    # TODO: Cognito forgot-password
    return {"error": "Not implemented"}


@router.post("/reset-password")
def reset_password():
    # TODO: Cognito confirm-forgot-password
    return {"error": "Not implemented"}


@router.get("/me")
def me():
    # TODO: return current user from validated token
    return {"error": "Not implemented"}
