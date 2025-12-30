from __future__ import annotations

from types import SimpleNamespace


def test_call_text_skips_gpt5_when_responses_api_unavailable(monkeypatch):
    """
    If the installed OpenAI SDK doesn't expose `client.responses`, GPT-5 family models
    must NOT be called via chat.completions (OpenAI rejects them as "not a chat model").
    We should fall back to a chat-capable model instead.
    """
    from app.ai import client as ai_client

    # Ensure "configured"
    ai_client.settings.openai_api_key = "test"

    # Force model order: GPT-5 first, then a chat model.
    monkeypatch.setattr(ai_client, "_models_to_try", lambda _purpose: ["gpt-5.2", "gpt-4o-mini"])
    monkeypatch.setattr(ai_client, "_supports_responses_api", lambda _c: False)
    monkeypatch.setattr(ai_client.time, "sleep", lambda _s: None)

    calls: list[str] = []

    class _FakeChatCompletions:
        def create(self, *, model: str, **_kwargs):
            calls.append(model)
            # Minimal OpenAI SDK-shaped response
            msg = SimpleNamespace(content="ok")
            choice = SimpleNamespace(message=msg)
            return SimpleNamespace(choices=[choice], usage=None)

    fake = SimpleNamespace(chat=SimpleNamespace(completions=_FakeChatCompletions()))
    monkeypatch.setattr(ai_client, "_client", lambda timeout_s=60: fake)

    out, meta = ai_client.call_text(purpose="slack_agent", messages=[{"role": "user", "content": "hi"}], retries=1)
    assert out == "ok"
    assert meta.model == "gpt-4o-mini"
    assert calls == ["gpt-4o-mini"]


def test_call_text_chat_success_path_returns_output(monkeypatch):
    """
    Regression test: successful chat.completions calls must return output (no indentation bugs).
    """
    from app.ai import client as ai_client

    ai_client.settings.openai_api_key = "test"
    monkeypatch.setattr(ai_client, "_models_to_try", lambda _purpose: ["gpt-4o-mini"])
    monkeypatch.setattr(ai_client.time, "sleep", lambda _s: None)

    class _FakeChatCompletions:
        def create(self, *, model: str, **_kwargs):
            msg = SimpleNamespace(content=f"model={model}")
            choice = SimpleNamespace(message=msg)
            return SimpleNamespace(choices=[choice], usage=None)

    fake = SimpleNamespace(chat=SimpleNamespace(completions=_FakeChatCompletions()))
    monkeypatch.setattr(ai_client, "_client", lambda timeout_s=60: fake)

    out, meta = ai_client.call_text(purpose="text_edit", messages=[{"role": "user", "content": "hi"}], retries=1)
    assert out == "model=gpt-4o-mini"
    assert meta.model == "gpt-4o-mini"


