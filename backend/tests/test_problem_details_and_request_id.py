from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_request_id_is_generated_and_returned():
    app = create_app()
    client = TestClient(app)

    r = client.get("/")
    assert r.status_code == 200
    assert "X-Request-Id" in r.headers
    assert r.headers["X-Request-Id"]


def test_request_id_is_propagated_from_client():
    app = create_app()
    client = TestClient(app)

    r = client.get("/", headers={"X-Request-Id": "abc-123"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-Id") == "abc-123"


def test_validation_errors_are_problem_json():
    app = create_app()
    client = TestClient(app)

    # Missing required body fields => pydantic validation error
    r = client.post("/api/auth/magic-link/verify", json={})
    assert r.status_code == 422
    assert r.headers.get("content-type", "").startswith("application/problem+json")
    body = r.json()
    assert body["title"] == "Validation Failed"
    assert body["status"] == 422
    assert "errors" in body and isinstance(body["errors"], list)
    assert body.get("requestId")


def test_404_is_problem_json():
    app = create_app()
    client = TestClient(app)

    r = client.get("/this-route-does-not-exist")
    assert r.status_code == 404
    assert r.headers.get("content-type", "").startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 404
    assert body.get("requestId")


def test_auth_denied_is_problem_json():
    app = create_app()
    client = TestClient(app)

    r = client.get("/api/auth/me")
    assert r.status_code in (401, 500)  # 500 possible if auth config missing in env
    assert r.headers.get("content-type", "").startswith("application/problem+json")
    body = r.json()
    assert body["status"] == r.status_code
    assert body.get("requestId")

