from __future__ import annotations

from app.ai.verification import chain, require_contains, require_max_chars, require_nonempty, require_regex


def test_chain_returns_first_error():
    v = chain(require_nonempty(), require_contains(needle="x"))
    assert v("") == "output must be non-empty"
    assert v("abc") == "output must contain 'x'"
    assert v("x") is None


def test_require_regex():
    v = require_regex(pattern=r"\brfp_[a-z0-9]{4,}\b")
    assert v("hello") is not None
    assert v("rfp_abcd") is None


def test_require_max_chars():
    v = require_max_chars(n=3)
    assert v("abcd") is not None
    assert v("abc") is None

