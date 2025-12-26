from __future__ import annotations

from app.repositories.rfp_opportunity_state_repo import _merge_state, default_state


def test_commitments_are_add_only():
    base = default_state(rfp_id="rfp_test123")
    base["commitments"] = [{"fact": "A"}]

    # Attempt overwrite should be ignored
    out = _merge_state(base, {"commitments": [{"fact": "B"}]})
    assert out["commitments"] == [{"fact": "A"}]

    # Append should work
    out2 = _merge_state(base, {"commitments_append": [{"fact": "B"}]})
    assert out2["commitments"] == [{"fact": "A"}, {"fact": "B"}]


def test_dict_fields_merge_not_replace():
    base = default_state(rfp_id="rfp_test123")
    base["comms"] = {"lastSlackSummaryAt": "t1"}
    out = _merge_state(base, {"comms": {"foo": "bar"}})
    assert out["comms"]["lastSlackSummaryAt"] == "t1"
    assert out["comms"]["foo"] == "bar"

