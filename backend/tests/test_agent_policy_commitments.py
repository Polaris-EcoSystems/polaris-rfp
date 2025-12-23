from __future__ import annotations

from app.domain.agents.self_improvement.agent_policy import sanitize_opportunity_patch


def test_commitments_append_requires_provenance():
    patch, checks = sanitize_opportunity_patch(
        patch={
            "commitments_append": [
                {"text": "We will deliver by Jan 1", "provenance": {"source": "slack", "threadTs": "123"}},
                {"text": "Missing provenance"},
                "not a dict",
            ]
        },
        actor={"kind": "test"},
    )

    assert "commitments_append" in patch
    assert len(patch["commitments_append"]) == 1
    assert patch["commitments_append"][0]["provenance"]["source"] == "slack"
    assert any(c.get("status") == "fail" for c in checks)
    assert any(c.get("status") == "pass" for c in checks)

