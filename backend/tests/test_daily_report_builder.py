from __future__ import annotations

from app.domain.agents.jobs import daily_report_builder


def test_build_northstar_daily_report_compact(monkeypatch):
    monkeypatch.setattr(
        daily_report_builder,
        "list_recent_events_global",
        lambda since_iso, limit=500: [
            {"type": "tool_call", "tool": "opportunity_patch", "rfpId": "rfp_a", "policyChecks": []},
            {"type": "tool_call", "tool": "slack_post_summary", "rfpId": "rfp_a", "policyChecks": []},
            {"type": "policy_check", "tool": "opportunity_patch", "rfpId": "rfp_b", "policyChecks": [{"status": "fail"}]},
        ],
        raising=True,
    )
    monkeypatch.setattr(
        daily_report_builder,
        "list_recent_change_proposals",
        lambda limit=100: {"data": [{"proposalId": "cp_1", "status": "pr_opened", "createdAt": "9999-01-01T00:00:00Z"}]},
        raising=True,
    )

    out = daily_report_builder.build_northstar_daily_report(hours=24)
    assert out["ok"] is True
    assert "North Star daily report" in out["slackText"]
    assert out["events"]["count"] == 3
    assert out["changeProposals"]["prsOpened"] == 1

