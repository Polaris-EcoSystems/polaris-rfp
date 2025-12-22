from __future__ import annotations

import pytest


def test_s3_allowlist_blocks_disallowed_prefix(monkeypatch):
    from app.settings import settings
    from app.tools.categories.aws import aws_s3

    monkeypatch.setattr(settings, "agent_allowed_s3_prefixes", "team/")

    called = {"delete": False}

    def _boom(*_args, **_kwargs):
        called["delete"] = True
        raise AssertionError("should not call real s3 delete")

    # If allowlist works, aws_s3 should raise before calling s3_assets.delete_object.
    from app.services import s3_assets
    monkeypatch.setattr(s3_assets, "delete_object", _boom)

    with pytest.raises(ValueError):
        aws_s3.delete_object(key="rfp/uploads/sha256/abc.pdf")

    assert called["delete"] is False


def test_sqs_allowlist_blocks_unknown_queue(monkeypatch):
    from app.settings import settings
    from app.tools.categories.aws import aws_sqs

    monkeypatch.setattr(settings, "agent_allowed_sqs_queue_urls", "https://example.com/allowed")

    with pytest.raises(ValueError):
        aws_sqs.get_queue_depth(queue_url="https://example.com/not-allowed")


def test_github_allowlist_blocks_unknown_repo(monkeypatch):
    from app.settings import settings
    from app.infrastructure.github import github_api

    monkeypatch.setattr(settings, "agent_allowed_github_repos", "good-org/good-repo")

    with pytest.raises(ValueError):
        github_api.list_pulls(repo="bad-org/bad-repo", state="open", limit=5)

