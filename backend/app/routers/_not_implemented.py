from __future__ import annotations

from fastapi import APIRouter, HTTPException


def make_router(name: str) -> APIRouter:
    router = APIRouter(tags=[name])

    @router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    def _catchall(path: str):
        raise HTTPException(status_code=501, detail=f"Not implemented: {name}")

    return router
