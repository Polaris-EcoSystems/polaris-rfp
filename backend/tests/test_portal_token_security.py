from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_portal_token_hash_is_deterministic_and_uses_secret(monkeypatch):
    from app.services import contracting_repo

    # Ensure pepper exists and is stable for this test.
    contracting_repo.settings.canva_token_enc_key = "unit-test-secret"
    contracting_repo.settings.jwt_secret = None

    tok = "abc123"
    h1 = contracting_repo.hash_portal_token(tok)
    h2 = contracting_repo.hash_portal_token(tok)
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 64  # sha256 hex

    # Changing pepper should change the hash.
    contracting_repo.settings.canva_token_enc_key = "unit-test-secret-2"
    h3 = contracting_repo.hash_portal_token(tok)
    assert h3 != h1


def test_get_package_by_portal_token_rejects_expired(monkeypatch):
    from app.services import contracting_repo

    contracting_repo.settings.canva_token_enc_key = "unit-test-secret"

    token = "t1"
    token_hash = contracting_repo.hash_portal_token(token)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")

    class FakePage:
        def __init__(self, items):
            self.items = items
            self.next_token = None

    class FakeTable:
        table_name = "fake"

        def query_page(self, **kwargs):
            assert kwargs.get("index_name") == "GSI1"
            # Return an expired package.
            return FakePage(
                [
                    {
                        "pk": "CONTRACTING#c1",
                        "sk": "PACKAGE#p1",
                        "entityType": "ClientPackage",
                        "caseId": "c1",
                        "packageId": "p1",
                        "name": "Pkg",
                        "selectedFiles": [{"id": "f1", "s3Key": "k"}],
                        "portalTokenHash": token_hash,
                        "portalTokenExpiresAt": expired,
                        "revokedAt": None,
                    }
                ]
            )

    monkeypatch.setattr(contracting_repo, "get_main_table", lambda: FakeTable())

    assert contracting_repo.get_package_by_portal_token(token) is None


def test_get_package_by_portal_token_rejects_revoked(monkeypatch):
    from app.services import contracting_repo

    contracting_repo.settings.canva_token_enc_key = "unit-test-secret"

    token = "t2"
    token_hash = contracting_repo.hash_portal_token(token)

    class FakePage:
        def __init__(self, items):
            self.items = items
            self.next_token = None

    class FakeTable:
        table_name = "fake"

        def query_page(self, **kwargs):
            return FakePage(
                [
                    {
                        "pk": "CONTRACTING#c1",
                        "sk": "PACKAGE#p1",
                        "entityType": "ClientPackage",
                        "caseId": "c1",
                        "packageId": "p1",
                        "name": "Pkg",
                        "selectedFiles": [{"id": "f1", "s3Key": "k"}],
                        "portalTokenHash": token_hash,
                        "portalTokenExpiresAt": None,
                        "revokedAt": "2025-01-01T00:00:00Z",
                    }
                ]
            )

    monkeypatch.setattr(contracting_repo, "get_main_table", lambda: FakeTable())

    assert contracting_repo.get_package_by_portal_token(token) is None

