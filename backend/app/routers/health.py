from __future__ import annotations

from fastapi import APIRouter

from ..settings import settings

router = APIRouter()


@router.get("/", tags=["health"])
def health():
    # Keep shape similar to Express health endpoint
    return {
        "message": "RFP Proposal Generation System API",
        "version": "1.0.0",
        "status": "running",
        "port": settings.port,
        "environment": settings.environment,
        "dynamodb": "configured" if settings.ddb_table_name else "missing",
        "endpoints": [
            "GET /api/rfp",
            "POST /api/rfp",
            "GET /api/proposals",
            "POST /api/proposals",
            "GET /api/templates",
            "POST /api/templates",
            "GET /api/content",
            "POST /api/ai",
            "POST /api/auth/signup",
            "POST /api/auth/login",
        ],
    }
