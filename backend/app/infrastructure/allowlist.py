from __future__ import annotations

from typing import Iterable


def parse_csv(raw: str | None) -> list[str]:
    """
    Parse a comma-separated list into trimmed non-empty strings.
    """
    s = str(raw or "").strip()
    if not s:
        return []
    out: list[str] = []
    for part in s.split(","):
        p = str(part or "").strip()
        if p:
            out.append(p)
    return out


def uniq(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for it in items:
        s = str(it or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def is_allowed_exact(value: str, allowed: list[str]) -> bool:
    if not allowed:
        return False
    v = str(value or "").strip()
    return bool(v) and v in allowed


def is_allowed_prefix(value: str, allowed_prefixes: list[str]) -> bool:
    """
    Prefix allowlist check. If prefixes are provided, value must start with at least one.
    """
    v = str(value or "").strip()
    if not v:
        return False
    if not allowed_prefixes:
        return False
    for p in allowed_prefixes:
        px = str(p or "").strip()
        if not px:
            continue
        if v.startswith(px):
            return True
    return False


