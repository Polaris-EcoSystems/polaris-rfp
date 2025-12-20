from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Window:
    # Sliding window of timestamps (seconds)
    ts: list[float]


_by_key: dict[str, _Window] = {}


def allow(*, key: str, limit: int, per_seconds: int) -> bool:
    """
    Very small in-memory rate limiter (per-process).
    """
    k = str(key or "").strip()
    if not k:
        return True
    lim = max(1, int(limit or 1))
    win = max(1, int(per_seconds or 1))
    now = time.time()

    w = _by_key.get(k)
    if not w:
        _by_key[k] = _Window(ts=[now])
        return True

    # Drop old
    cutoff = now - win
    w.ts = [t for t in w.ts if t >= cutoff]
    if len(w.ts) >= lim:
        return False
    w.ts.append(now)
    return True

