from __future__ import annotations

from typing import Any


def test_skill_body_key_is_under_agent_prefix():
    from app.skills.storage.skills_store import skill_body_key

    k = skill_body_key(skill_id="sk_abc123", version=2)
    assert k.startswith("agent/skills/")
    assert "/v2.json" in k


def test_skills_search_tool_calls_repo(monkeypatch):
    from app.tools.registry import read_registry

    called: dict[str, Any] = {"ok": False}

    def _fake_search(**kwargs):
        called["ok"] = True
        assert kwargs["limit"] == 3
        return {"ok": True, "data": [{"skillId": "sk_1"}], "nextToken": None}

    monkeypatch.setattr(read_registry, "skills_search_index", _fake_search)

    out = read_registry._skills_search_tool({"query": "skill", "limit": 3})
    assert called["ok"] is True
    assert out["ok"] is True
    assert out["data"][0]["skillId"] == "sk_1"

