from __future__ import annotations

import pytest


def test_browser_worker_client_denies_when_allowlist_missing(monkeypatch):
    from app.settings import settings
    from app.services import browser_worker_client as bw

    monkeypatch.setattr(settings, "agent_allowed_browser_domains", None)
    monkeypatch.setattr(settings, "browser_worker_url", "http://localhost:9999")

    with pytest.raises(ValueError):
        bw.goto(page_id="pg_1", url="https://example.com")


def test_browser_worker_client_blocks_disallowed_domain(monkeypatch):
    from app.settings import settings
    from app.services import browser_worker_client as bw

    monkeypatch.setattr(settings, "agent_allowed_browser_domains", "allowed.com")
    monkeypatch.setattr(settings, "browser_worker_url", "http://localhost:9999")

    with pytest.raises(ValueError):
        bw.goto(page_id="pg_1", url="https://not-allowed.com")

