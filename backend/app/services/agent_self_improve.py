from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..ai.verified_calls import call_json_verified
from ..settings import settings
from .agent_events_repo import append_event, list_recent_events_global
from .agent_jobs_repo import create_job


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class PerchSuggestion(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    recommendation: str = Field(min_length=1, max_length=500)
    confidence: str = Field(default="medium", max_length=20)


class PerchReport(BaseModel):
    summary: str = Field(min_length=1, max_length=1200)
    suggestions: list[PerchSuggestion] = Field(default_factory=list, max_length=5)


def _failure_facts(*, since_iso: str, limit: int = 400) -> list[dict[str, Any]]:
    evs = list_recent_events_global(since_iso=since_iso, limit=limit)
    facts: list[dict[str, Any]] = []
    for e in evs:
        if not isinstance(e, dict):
            continue
        t = str(e.get("type") or "").strip()
        if t not in ("tool_call", "agent_job_failed"):
            continue
        payload_raw = e.get("payload")
        payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
        ok = bool(payload.get("ok")) if t == "tool_call" else False
        if t == "tool_call" and ok:
            continue
        facts.append(
            {
                "type": t,
                "createdAt": e.get("createdAt"),
                "tool": e.get("tool"),
                "rfpId": e.get("rfpId"),
                "payload": {"ok": payload.get("ok"), "durationMs": payload.get("durationMs"), "error": payload.get("error")},
            }
        )
    return facts[:400]


def run_perch_time_once(*, hours: int = 6, reschedule_minutes: int | None = 60) -> dict[str, Any]:
    """
    Use recent durable telemetry (AgentEvent) to propose small improvements.
    
    Also runs job learning to extract patterns from completed jobs and update memory.

    This does NOT mutate production state directly. It only emits an AgentEvent
    that a human (or approval-gated pipeline) can act on.
    """
    h = max(1, min(48, int(hours or 6)))
    since = _iso(_utcnow() - timedelta(hours=h))
    facts = _failure_facts(since_iso=since, limit=600)

    # If no OpenAI key, fall back to a deterministic summary.
    if not settings.openai_api_key:
        summary = f"No LLM configured. Observed {len(facts)} failure-related events in the last {h}h."
        report = {"summary": summary, "suggestions": []}
    else:
        prompt = "\n".join(
            [
                "You are an engineering agent doing perch-time self-improvement.",
                "You are given recent failure-related telemetry events. Produce:",
                "- a short summary",
                "- up to 5 actionable suggestions (each with evidence lines referencing tools/types/timestamps).",
                "",
                "Rules:",
                "- Do not invent evidence; only cite what is present in the facts.",
                "- Keep suggestions small and implementable.",
                "- If evidence is insufficient, lower confidence and say so.",
                "",
                "Facts:",
                str(facts),
            ]
        )
        parsed, _meta = call_json_verified(
            purpose="generate_content",
            response_model=PerchReport,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
            temperature=0.2,
            retries=2,
        )
        report = parsed.model_dump()

    # Run job learning to extract patterns from completed jobs
    job_learning_result = None
    try:
        from .agent_job_learning import update_memory_from_job_outcomes
        job_learning_result = update_memory_from_job_outcomes()
    except Exception:
        # Don't fail the whole perch_time run if job learning fails
        pass
    
    try:
        payload = {"hours": h, "since": since, "factsCount": len(facts), "report": report}
        if job_learning_result:
            payload["jobLearning"] = {
                "patternsAnalyzed": job_learning_result.get("patterns_analyzed", 0),
                "bestPracticesFound": job_learning_result.get("best_practices_found", 0),
                "storedCount": job_learning_result.get("stored_count", 0),
            }
        append_event(
            rfp_id="rfp_perch_time",
            type="agent_perch_time_report",
            tool="agent_self_improve",
            payload=payload,
            created_by="system",
            correlation_id=None,
        )
    except Exception:
        pass

    if reschedule_minutes is not None and int(reschedule_minutes) > 0:
        due = _iso(_utcnow() + timedelta(minutes=max(5, min(240, int(reschedule_minutes)))))
        create_job(
            job_type="agent_perch_time",
            scope={"env": settings.normalized_environment},
            payload={"hours": h, "rescheduleMinutes": int(reschedule_minutes)},
            due_at=due,
        )

    return {"ok": True, "hours": h, "since": since, "factsCount": len(facts), "report": report}

