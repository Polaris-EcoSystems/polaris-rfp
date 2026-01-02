from __future__ import annotations

from fastapi import APIRouter

from app.settings import settings

router = APIRouter()

def _openai_capabilities() -> dict[str, object]:
    try:
        import openai
        from openai import OpenAI

        try:
            client = OpenAI(api_key="__redacted__", max_retries=0, timeout=5)
            has_responses = bool(getattr(client, "responses", None)) and callable(
                getattr(getattr(client, "responses", None), "create", None)
            )
        except Exception:
            has_responses = False

        return {
            "sdk_version": str(getattr(openai, "__version__", "") or "unknown"),
            "has_responses": bool(has_responses),
        }
    except Exception:
        return {"sdk_version": None, "has_responses": False}


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
        "openai": _openai_capabilities(),
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
