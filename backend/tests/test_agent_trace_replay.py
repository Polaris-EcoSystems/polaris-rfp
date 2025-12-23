from __future__ import annotations


def test_replay_tool_call_trace_flags_unknown_tools():
    from app.domain.agents.jobs.agent_trace_replay import replay_tool_call_trace

    trace = [
        {"tool": "opportunity_load", "durationMs": 12, "argsKeys": ["rfpId"]},
        {"tool": "totally_not_a_tool", "durationMs": 5, "argsKeys": []},
    ]
    res = replay_tool_call_trace(records=trace, allowed_tools={"opportunity_load"})
    assert res["ok"] is False
    assert any(v["code"] == "tool_not_allowed" for v in res["violations"])


def test_replay_tool_call_trace_accepts_valid_trace():
    from app.domain.agents.jobs.agent_trace_replay import replay_tool_call_trace

    trace = [
        {"tool": "opportunity_load", "durationMs": 12, "argsKeys": ["rfpId"]},
        {"tool": "opportunity_patch", "durationMs": 30, "argsKeys": ["patch", "correlationId"]},
    ]
    res = replay_tool_call_trace(records=trace, allowed_tools={"opportunity_load", "opportunity_patch"})
    assert res["ok"] is True

