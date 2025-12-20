from __future__ import annotations


def test_user_memory_load_tool_requires_user_sub():
    from app.services.agent_tools import read_registry

    out = read_registry._user_memory_load_tool({})
    assert out["ok"] is False
    assert out["error"] == "missing_userSub"


def test_memory_search_tool_requires_query():
    from app.services.agent_tools import read_registry

    out = read_registry._memory_search_tool({})
    assert out["ok"] is False
    assert out["error"] == "missing_query"

