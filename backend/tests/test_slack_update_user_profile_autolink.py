from __future__ import annotations

from types import SimpleNamespace


def test_execute_action_update_user_profile_autolinks_from_slack(monkeypatch):
    """
    If a Slack user is *not* manually linked (no UserProfile and no slackUserId GSI),
    `execute_action(update_user_profile)` should still work by resolving Slack -> email -> Cognito sub.
    """
    from app.services import slack_action_executor as sae

    # No profile exists yet.
    monkeypatch.setattr(sae, "get_user_profile", lambda *, user_sub: None)
    monkeypatch.setattr(sae, "get_user_profile_by_slack_user_id", lambda *, slack_user_id: None)

    calls: list[dict] = []

    def _fake_upsert(*, user_sub: str, email: str | None, updates: dict):
        calls.append({"user_sub": user_sub, "email": email, "updates": dict(updates or {})})
        # Return the shape expected by slack_action_executor.
        ai_prefs = updates.get("aiPreferences") if isinstance(updates.get("aiPreferences"), dict) else {}
        return {
            "_id": user_sub,
            "userSub": user_sub,
            "email": email,
            "slackUserId": updates.get("slackUserId"),
            "preferredName": updates.get("preferredName"),
            "aiPreferences": ai_prefs,
            "aiMemorySummary": updates.get("aiMemorySummary"),
        }

    monkeypatch.setattr(sae, "upsert_user_profile", _fake_upsert)

    # Patch resolve_actor_context at its module import location.
    from app.services import slack_actor_context as sac

    monkeypatch.setattr(
        sac,
        "resolve_actor_context",
        lambda **kwargs: SimpleNamespace(user_sub="sub_123", email="wes.ladd@polariseco.com"),
    )

    res = sae.execute_action(
        action_id="sa_test",
        kind="update_user_profile",
        args={
            "_actorSlackUserId": "U072S0H9318",
            "_requestedBySlackUserId": "U072S0H9318",
            "aiPreferencesMerge": {
                "redTeamRequired": True,
                "format": "Exec summary + appendix",
            },
        },
    )

    assert res["ok"] is True
    assert res["action"] == "update_user_profile"
    assert res["updated"] is True
    assert res["userSub"] == "sub_123"
    assert calls, "Expected upsert_user_profile to be called"
    assert calls[-1]["email"] == "wes.ladd@polariseco.com"
    assert calls[-1]["updates"]["slackUserId"] == "U072S0H9318"
    assert calls[-1]["updates"]["aiPreferences"]["redTeamRequired"] is True
