from __future__ import annotations

import anyio
from starlette.background import BackgroundTasks


def test_async_generate_sets_status_and_updates_sections(monkeypatch):
    # Import inside test so monkeypatching module attributes is straightforward.
    from app.routers import proposals as proposals_router

    updates: list[dict] = []

    def fake_update_proposal(proposal_id: str, patch: dict):
        updates.append({"proposal_id": proposal_id, **(patch or {})})
        return {"_id": proposal_id, **(patch or {})}

    def fake_create_proposal(**kwargs):
        # Mirror the API shape used by the frontend.
        return {
            "_id": "proposal_test_1",
            "rfpId": kwargs.get("rfp_id"),
            "companyId": kwargs.get("company_id"),
            "templateId": kwargs.get("template_id"),
            "title": kwargs.get("title"),
            "sections": kwargs.get("sections") or {},
            "generationStatus": kwargs.get("generation_status"),
            "generationError": kwargs.get("generation_error"),
            "generationStartedAt": kwargs.get("generation_started_at"),
            "generationCompletedAt": kwargs.get("generation_completed_at"),
        }

    monkeypatch.setattr(proposals_router, "update_proposal", fake_update_proposal)
    monkeypatch.setattr(proposals_router, "create_proposal", fake_create_proposal)

    monkeypatch.setattr(
        proposals_router,
        "get_rfp_by_id",
        lambda _id: {
            "_id": _id,
            "title": "Example RFP",
            "clientName": "Example Client",
            "projectType": "software_development",
            "keyRequirements": ["Req A", "Req B"],
            "sectionTitles": ["Title", "Technical Approach", "Key Personnel", "References"],
        },
    )

    monkeypatch.setattr(
        proposals_router.content_repo,
        "get_company_by_company_id",
        lambda cid: {"companyId": cid, "name": "Acme", "coreCapabilities": ["X"]},
    )
    monkeypatch.setattr(
        proposals_router.content_repo,
        "list_companies",
        lambda limit=1: [{"companyId": "c1", "name": "Acme", "coreCapabilities": ["X"]}],
    )
    monkeypatch.setattr(
        proposals_router.content_repo,
        "get_team_members_by_ids",
        lambda ids: [
            {
                "memberId": ids[0],
                "nameWithCredentials": "Jane Doe, PMP",
                "position": "Program Manager",
                "isActive": True,
                "biography": "Bio",
            }
        ],
    )
    monkeypatch.setattr(
        proposals_router.content_repo,
        "get_project_references_by_ids",
        lambda ids: [
            {
                "_id": ids[0],
                "organizationName": "Example Org",
                "timePeriod": "2024",
                "contactName": "Bob",
                "contactTitle": "Director",
                "scopeOfWork": "Did work",
                "isActive": True,
                "isPublic": True,
            }
        ],
    )

    bg = BackgroundTasks()
    body = {
        "rfpId": "rfp_1",
        "templateId": "ai-template",
        "title": "My Proposal",
        "companyId": "c1",
        "customContent": {"teamMemberIds": ["m1"], "referenceIds": ["r1"]},
        "async": True,
    }

    proposal = proposals_router.generate(body, bg)
    assert proposal["generationStatus"] == "queued"
    assert "Title" in proposal["sections"]
    assert "(Generating" in str(proposal["sections"]["Title"]["content"])

    async def _run_bg():
        for t in bg.tasks:
            await t()

    # Execute queued background tasks.
    anyio.run(_run_bg)

    assert updates, "Expected update_proposal to be called during async generation"
    assert updates[0]["generationStatus"] == "running"
    assert updates[-1]["generationStatus"] == "complete"

    final_sections = updates[-1]["sections"]
    assert "Key Personnel" in final_sections
    assert "Jane Doe" in str(final_sections["Key Personnel"]["content"])
    assert "References" in final_sections
    assert "Example Org" in str(final_sections["References"]["content"])


def test_async_generate_sets_error_on_failure(monkeypatch):
    from app.routers import proposals as proposals_router

    updates: list[dict] = []

    def fake_update_proposal(proposal_id: str, patch: dict):
        updates.append({"proposal_id": proposal_id, **(patch or {})})
        return {"_id": proposal_id, **(patch or {})}

    def fake_create_proposal(**kwargs):
        return {
            "_id": "proposal_test_2",
            "rfpId": kwargs.get("rfp_id"),
            "sections": kwargs.get("sections") or {},
            "generationStatus": kwargs.get("generation_status"),
        }

    monkeypatch.setattr(proposals_router, "update_proposal", fake_update_proposal)
    monkeypatch.setattr(proposals_router, "create_proposal", fake_create_proposal)

    calls = {"n": 0}

    def rfp_then_boom(_id: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"_id": _id, "title": "RFP", "sectionTitles": ["Title"]}
        raise RuntimeError("boom")

    monkeypatch.setattr(proposals_router, "get_rfp_by_id", rfp_then_boom)
    monkeypatch.setattr(
        proposals_router.content_repo,
        "get_company_by_company_id",
        lambda cid: {"companyId": cid, "name": "Acme", "coreCapabilities": []},
    )
    monkeypatch.setattr(
        proposals_router.content_repo,
        "list_companies",
        lambda limit=1: [{"companyId": "c1", "name": "Acme", "coreCapabilities": []}],
    )

    bg = BackgroundTasks()
    body = {"rfpId": "rfp_1", "templateId": "ai-template", "title": "T", "async": True}
    proposal = proposals_router.generate(body, bg)
    assert proposal["generationStatus"] == "queued"

    async def _run_bg():
        for t in bg.tasks:
            await t()

    anyio.run(_run_bg)

    assert updates, "Expected updates even on failure"
    assert updates[-1]["generationStatus"] == "error"
    assert "generationError" in updates[-1]



