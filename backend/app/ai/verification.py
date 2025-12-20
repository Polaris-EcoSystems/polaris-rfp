from __future__ import annotations

import re
from typing import Callable


Validator = Callable[[str], str | None]


def chain(*validators: Validator) -> Validator:
    """
    Compose multiple validators. Returns the first error message, else None.
    """

    def _v(text: str) -> str | None:
        for fn in validators:
            msg = fn(text)
            if msg:
                return msg
        return None

    return _v


def require_nonempty(*, what: str = "output") -> Validator:
    def _v(text: str) -> str | None:
        if not str(text or "").strip():
            return f"{what} must be non-empty"
        return None

    return _v


def require_contains(*, needle: str, what: str = "output") -> Validator:
    n = str(needle or "")

    def _v(text: str) -> str | None:
        t = str(text or "")
        if n and n not in t:
            return f"{what} must contain {n!r}"
        return None

    return _v


def require_regex(*, pattern: str, flags: int = 0, what: str = "output") -> Validator:
    rx = re.compile(pattern, flags=flags)

    def _v(text: str) -> str | None:
        if not rx.search(str(text or "")):
            return f"{what} must match /{pattern}/"
        return None

    return _v


def require_max_chars(*, n: int, what: str = "output") -> Validator:
    lim = max(1, int(n or 1))

    def _v(text: str) -> str | None:
        t = str(text or "")
        if len(t) > lim:
            return f"{what} must be <= {lim} chars (got {len(t)})"
        return None

    return _v


def forbid_contains(*, needles: list[str], what: str = "output") -> Validator:
    ns = [str(x) for x in (needles or []) if str(x)]

    def _v(text: str) -> str | None:
        t = str(text or "")
        for n in ns:
            if n and n in t:
                return f"{what} must not contain {n!r}"
        return None

    return _v


def forbid_regex(*, pattern: str, flags: int = 0, what: str = "output") -> Validator:
    rx = re.compile(pattern, flags=flags)

    def _v(text: str) -> str | None:
        if rx.search(str(text or "")):
            return f"{what} must not match /{pattern}/"
        return None

    return _v

