from __future__ import annotations

from fastapi.testclient import TestClient


def _authed_client(monkeypatch) -> TestClient:
    from app.main import create_app

    # Bypass Cognito verification for tests.
    from app.middleware import auth as auth_mw

    class _User:
        sub = "user_test_123"

    monkeypatch.setattr(auth_mw, "verify_bearer_token", lambda _tok: _User())
    app = create_app()
    return TestClient(app)


def test_ai_agent_ask_requires_question(monkeypatch):
    c = _authed_client(monkeypatch)
    r = c.post("/api/ai/ask", headers={"Authorization": "Bearer test"}, json={})
    assert r.status_code == 400


def test_ai_agent_ask_returns_answer(monkeypatch):
    c = _authed_client(monkeypatch)

    from app.routers import ai_agent as router_mod
    from app.services.slack_agent import SlackAgentAnswer

    def _fake_run(**_kwargs):
        return SlackAgentAnswer(text="hello", blocks=None, meta={"x": 1})

    monkeypatch.setattr(router_mod, "run_slack_agent_question", _fake_run)

    r = c.post("/api/ai/ask", headers={"Authorization": "Bearer test"}, json={"question": "hi"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["ok"] is True
    assert payload["text"] == "hello"


def test_ai_agent_propose_confirm_cancel_happy_path(monkeypatch):
    c = _authed_client(monkeypatch)

    from app.routers import ai_agent as router_mod

    # Stub persistence
    store = {
        "sa_test": {
            "actionId": "sa_test",
            "kind": "complete_task",
            "payload": {"args": {"taskId": "t_1"}, "requestedByUserSub": "user_test_123"},
        }
    }

    monkeypatch.setattr(router_mod, "create_action", lambda **_kw: store["sa_test"])
    monkeypatch.setattr(router_mod, "get_action", lambda aid: store.get(aid))
    monkeypatch.setattr(router_mod, "mark_action_done", lambda **_kw: {"ok": True})
    monkeypatch.setattr(router_mod, "execute_action", lambda **_kw: {"ok": True, "action": "complete_task"})

    r1 = c.post(
        "/api/ai/propose",
        headers={"Authorization": "Bearer test"},
        json={"kind": "complete_task", "args": {"taskId": "t_1"}, "summary": "complete"},
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    r2 = c.post("/api/ai/confirm", headers={"Authorization": "Bearer test"}, json={"actionId": "sa_test"})
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["result"]["ok"] is True

    r3 = c.post("/api/ai/cancel", headers={"Authorization": "Bearer test"}, json={"actionId": "sa_test"})
    assert r3.status_code == 200
    assert r3.json()["ok"] is True

