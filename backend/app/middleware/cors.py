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
    # CORSMiddleware doesn't support per-request logic. We keep this strict list for now,
    # then will broaden via custom middleware if needed.
    return sorted(allowed)


def make_cors_middleware(*, allowed_origins: Iterable[str]) -> CORSMiddleware:
    return CORSMiddleware(
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        expose_headers=["ETag"],
        max_age=3000,
    )
