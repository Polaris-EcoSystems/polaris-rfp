from __future__ import annotations

from datetime import datetime, timezone


def test_next_daily_digest_due_iso_before_8am_chicago():
    from app.services.agent_daily_digest import next_daily_digest_due_iso

    now = datetime(2025, 12, 20, 12, 0, 0, tzinfo=timezone.utc)  # 06:00 CT
    due = next_daily_digest_due_iso(now_utc=now, tz_name="America/Chicago")
    assert due.startswith("2025-12-20T14:00:00")  # 08:00 CT == 14:00 UTC


def test_next_daily_digest_due_iso_after_8am_chicago():
    from app.services.agent_daily_digest import next_daily_digest_due_iso

    now = datetime(2025, 12, 20, 16, 0, 0, tzinfo=timezone.utc)  # 10:00 CT
    due = next_daily_digest_due_iso(now_utc=now, tz_name="America/Chicago")
    assert due.startswith("2025-12-21T14:00:00")

