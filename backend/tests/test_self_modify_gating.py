from __future__ import annotations

from app.domain.agents.self_improvement import self_modify_pipeline
from app.settings import settings


def test_self_modify_disabled_blocks_open_pr(monkeypatch):
    monkeypatch.setattr(settings, "self_modify_enabled", False, raising=False)
    res = self_modify_pipeline.open_pr_for_change_proposal(
        proposal_id="cp_test",
        actor_slack_user_id="U123",
        rfp_id="rfp_test123",
    )
    assert res["ok"] is False
    assert res["error"] == "self_modify_disabled"


def test_self_modify_requires_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "self_modify_enabled", True, raising=False)
    monkeypatch.setattr(settings, "self_modify_allowed_slack_user_ids", None, raising=False)
    res = self_modify_pipeline.open_pr_for_change_proposal(
        proposal_id="cp_test",
        actor_slack_user_id="U123",
        rfp_id="rfp_test123",
    )
    assert res["ok"] is False
    assert res["error"] == "not_authorized"

