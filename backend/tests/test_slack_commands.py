from __future__ import annotations

import hashlib
import hmac
import time
import json

from fastapi.testclient import TestClient

from app.main import create_app


def _slack_signature(*, secret: str, timestamp: str, body: bytes) -> str:
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def test_slack_commands_help_ok():
    # Patch signing secret on the imported settings singleton used by the router.
    from app.routers import integrations_slack

    integrations_slack.settings.slack_enabled = True
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
    assert payload.get("response_type") == "in_channel"
    assert "Polaris RFP Slack commands" in str(payload.get("text") or "")
    assert "/polaris upload" in str(payload.get("text") or "")


def test_slack_commands_missing_signature_denied():
    from app.routers import integrations_slack

    integrations_slack.settings.slack_enabled = True
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

    integrations_slack.settings.slack_enabled = True
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


def test_slack_commands_secret_arn_path_ok():
    """
    When SLACK_SECRET_ARN is used in production, settings.slack_signing_secret may be unset.
    The router should fall back to Secrets Manager JSON key SLACK_SIGNING_SECRET.

    We stub get_secret_str() to avoid AWS calls in tests.
    """
    from app.routers import integrations_slack

    integrations_slack.settings.slack_enabled = True
    integrations_slack.settings.slack_signing_secret = None

    original_get_secret_str = integrations_slack.get_secret_str
    try:
        integrations_slack.get_secret_str = lambda k: "test-signing-secret" if k == "SLACK_SIGNING_SECRET" else None

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
        assert r.json().get("response_type") == "in_channel"
    finally:
        integrations_slack.get_secret_str = original_get_secret_str


def test_slack_events_app_mention_replies_ok():
    from app.routers import integrations_slack

    integrations_slack.settings.slack_enabled = True
    integrations_slack.settings.slack_signing_secret = "test-signing-secret"

    called: dict[str, object] = {}

    def _fake_chat_post_message_result(**kwargs):
        called.update(kwargs)
        return {"ok": True}

    original_chat_post = integrations_slack.chat_post_message_result
    original_answer = integrations_slack._answer_slack_question
    try:
        integrations_slack.chat_post_message_result = _fake_chat_post_message_result
        integrations_slack._answer_slack_question = lambda *, question: "ANSWER: " + str(question)

        app = create_app()
        client = TestClient(app)

        payload = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "text": "<@U_APP> What can you do for me?",
                "ts": "1700000000.000100",
            },
        }
        body = json.dumps(payload).encode("utf-8")
        ts = str(int(time.time()))
        sig = _slack_signature(secret="test-signing-secret", timestamp=ts, body=body)

        r = client.post(
            "/api/integrations/slack/events",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True
        assert str(called.get("channel") or "") == "C123"
        assert str(called.get("thread_ts") or "") == "1700000000.000100"
        assert "answer:" in str(called.get("text") or "").lower()
    finally:
        integrations_slack.chat_post_message_result = original_chat_post
        integrations_slack._answer_slack_question = original_answer


def test_slack_events_app_mention_help_menu_on_hi():
    from app.routers import integrations_slack

    integrations_slack.settings.slack_enabled = True
    integrations_slack.settings.slack_signing_secret = "test-signing-secret"

    called: dict[str, object] = {}

    def _fake_chat_post_message_result(**kwargs):
        called.update(kwargs)
        return {"ok": True}

    original_chat_post = integrations_slack.chat_post_message_result
    try:
        integrations_slack.chat_post_message_result = _fake_chat_post_message_result

        app = create_app()
        client = TestClient(app)

        payload = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "text": "Hi <@U_APP>",
                "ts": "1700000000.000100",
            },
        }
        body = json.dumps(payload).encode("utf-8")
        ts = str(int(time.time()))
        sig = _slack_signature(secret="test-signing-secret", timestamp=ts, body=body)

        r = client.post(
            "/api/integrations/slack/events",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True
        assert "polaris ask" in str(called.get("text") or "").lower()
    finally:
        integrations_slack.chat_post_message_result = original_chat_post


def test_slack_events_app_mention_dm_me_team_members():
    from app.routers import integrations_slack

    integrations_slack.settings.slack_enabled = True
    integrations_slack.settings.slack_signing_secret = "test-signing-secret"

    posted: list[dict[str, object]] = []

    def _fake_chat_post_message_result(**kwargs):
        posted.append(dict(kwargs))
        return {"ok": True}

    original_chat_post = integrations_slack.chat_post_message_result
    original_open_dm = integrations_slack.open_dm_channel
    original_list_team = integrations_slack.content_repo.list_team_members
    try:
        integrations_slack.chat_post_message_result = _fake_chat_post_message_result
        integrations_slack.open_dm_channel = lambda *, user_id: "D123"
        integrations_slack.content_repo.list_team_members = lambda *, limit=200: [
            {"name": "Alice", "title": "PM"},
            {"name": "Bob", "title": "Engineer"},
        ]

        app = create_app()
        client = TestClient(app)

        payload = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "text": "<@U_APP> dm me list of team members",
                "ts": "1700000000.000100",
            },
        }
        body = json.dumps(payload).encode("utf-8")
        ts = str(int(time.time()))
        sig = _slack_signature(secret="test-signing-secret", timestamp=ts, body=body)

        r = client.post(
            "/api/integrations/slack/events",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # We should DM the user (channel D123) and also ack in-thread in C123.
        assert any(str(p.get("channel")) == "D123" for p in posted)
        assert any(str(p.get("channel")) == "C123" for p in posted)
        dm_msgs = [p for p in posted if str(p.get("channel")) == "D123"]
        assert dm_msgs
        assert any("team members" in str(m.get("text") or "").lower() for m in dm_msgs)
    finally:
        integrations_slack.chat_post_message_result = original_chat_post
        integrations_slack.open_dm_channel = original_open_dm
        integrations_slack.content_repo.list_team_members = original_list_team


def test_slack_events_retry_does_not_reply():
    from app.routers import integrations_slack

    integrations_slack.settings.slack_enabled = True
    integrations_slack.settings.slack_signing_secret = "test-signing-secret"

    def _boom(**_kwargs):
        raise AssertionError("Should not attempt to post on Slack retry")

    original_chat_post = integrations_slack.chat_post_message_result
    try:
        integrations_slack.chat_post_message_result = _boom

        app = create_app()
        client = TestClient(app)

        payload = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "text": "Hi <@U_APP>",
                "ts": "1700000000.000100",
            },
        }
        body = json.dumps(payload).encode("utf-8")
        ts = str(int(time.time()))
        sig = _slack_signature(secret="test-signing-secret", timestamp=ts, body=body)

        r = client.post(
            "/api/integrations/slack/events",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
                "X-Slack-Retry-Num": "1",
                "X-Slack-Retry-Reason": "http_timeout",
            },
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True
    finally:
        integrations_slack.chat_post_message_result = original_chat_post



