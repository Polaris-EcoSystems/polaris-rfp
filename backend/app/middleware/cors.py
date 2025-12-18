from __future__ import annotations

from typing import Iterable

from fastapi.middleware.cors import CORSMiddleware


def build_allowed_origins(*, frontend_base_url: str, frontend_url: str | None, frontend_urls: str | None) -> list[str]:
    allowed: set[str] = {
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "https://rfp.polariseco.com",
    }

    if frontend_base_url:
        allowed.add(frontend_base_url)

    for v in [frontend_url, frontend_urls]:
        if not v:
            continue
        for origin in [s.strip() for s in str(v).split(",") if s.strip()]:
            allowed.add(origin)

    # Note: Express implementation also allowed any *.amplifyapp.com and *.polariseco.com
    # We keep this strict list and add an allow_origin_regex separately for wildcard support.
    return sorted(allowed)


def build_allowed_origin_regex() -> str:
    """
    CORSMiddleware supports a single allow_origin_regex, which we use to safely support:
      - Amplify preview domains: *.amplifyapp.com
      - Polaris subdomains: *.polariseco.com
    while still allowing credentials (cookies/Authorization).

    Notes:
    - This intentionally matches the *registrable* domains (amplifyapp.com, polariseco.com),
      not suffixes like "evilpolariseco.com".
    - Port is permitted for dev/staging custom setups.
    """
    return r"^https?://([a-z0-9-]+\.)*(amplifyapp\.com|polariseco\.com)(:\d+)?$"


def make_cors_middleware(*, allowed_origins: Iterable[str]) -> CORSMiddleware:
    return CORSMiddleware(
        allow_origins=list(allowed_origins),
        allow_origin_regex=build_allowed_origin_regex(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        expose_headers=["ETag"],
        max_age=3000,
    )
