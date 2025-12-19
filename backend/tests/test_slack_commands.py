from __future__ import annotations

import hashlib
import hmac
import time

from fastapi.testclient import TestClient

from app.main import create_app


def _slack_signature(*, secret: str, timestamp: str, body: bytes) -> str:
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def test_slack_commands_help_ok():
    # Patch signing secret on the imported settings singleton used by the router.
    from app.routers import integrations_slack

    integrations_slack.settings.slack_signing_secret = "test-signing-secret"

    app = create_app()
    client = TestClient(app)

    body = b"text=help"
    ts = str(int(time.time()))
    sig = _slack_signature(secret="test-signing-secret", timestamp=ts, body=body)

    r = client.post(
        "/api/integrations/slack/commands",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("response_type") == "ephemeral"
    assert "Polaris RFP Slack commands" in str(payload.get("text") or "")


def test_slack_commands_missing_signature_denied():
    from app.routers import integrations_slack

    integrations_slack.settings.slack_signing_secret = "test-signing-secret"

    app = create_app()
    client = TestClient(app)

    r = client.post(
        "/api/integrations/slack/commands",
        data=b"text=help",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 401


def test_slack_interactions_block_action_ack_ok():
    from app.routers import integrations_slack

    integrations_slack.settings.slack_signing_secret = "test-signing-secret"

    app = create_app()
    client = TestClient(app)

    payload = {
        "type": "block_actions",
        "user": {"id": "U123"},
        "channel": {"id": "C123"},
        "response_url": "https://example.com/response-url",
        "actions": [{"action_id": "polaris_list_rfp_proposals", "value": "rfp_123"}],
    }
    body = ("payload=" + __import__("json").dumps(payload)).encode("utf-8")
    ts = str(int(time.time()))
    sig = _slack_signature(secret="test-signing-secret", timestamp=ts, body=body)

    r = client.post(
        "/api/integrations/slack/interactions",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 200
    assert r.json().get("response_type") == "ephemeral"

