from __future__ import annotations

import re
from typing import Iterable


def clip_text(text: str, *, max_chars: int) -> str:
    s = str(text or "")
    if max_chars <= 0:
        return ""
    return s if len(s) <= max_chars else s[:max_chars]


def normalize_ws(text: str, *, max_chars: int) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return clip_text(s, max_chars=max_chars)


def split_paragraphs(text: str, *, max_paragraphs: int = 4000) -> list[str]:
    # Split on blank lines, keep ordering.
    raw = str(text or "").replace("\r\n", "\n")
    parts = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p and p.strip()]
    if len(parts) > max_paragraphs:
        return parts[:max_paragraphs]
    return parts


def top_k_paragraphs_by_keyword(
    *,
    text: str,
    query: str,
    k: int = 12,
    max_chars_each: int = 1200,
) -> list[str]:
    """
    Very lightweight relevance selector:
    - score paragraphs by how many query tokens they contain (case-insensitive substring)
    - return top K paragraphs, preserving original order (to keep context coherent)

    This is not semantic search; it’s a fast deterministic heuristic that reduces prompt size.
    """
    q = normalize_ws(query, max_chars=4000).lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", q) if len(t) >= 3]
    if not toks:
        return []

    paras = split_paragraphs(text)
    scored: list[tuple[int, int]] = []
    for idx, p in enumerate(paras):
        low = p.lower()
        score = 0
        for t in toks[:16]:
            if t in low:
                score += 1
        if score:
            scored.append((score, idx))

    if not scored:
        return []

    scored.sort(key=lambda x: (-x[0], x[1]))
    top = sorted([idx for _s, idx in scored[: max(1, int(k))]])
    out: list[str] = []
    for idx in top:
        out.append(clip_text(paras[idx], max_chars=max_chars_each))
    return out


def build_rfp_prompt_context(
    *,
    raw_text: str,
    source_name: str,
    max_chars: int,
    query: str | None = None,
) -> str:
    """
    Build a bounded context section for prompts that need RFP text.
    """
    text = str(raw_text or "").strip()
    if not text:
        return ""

    if query:
        picked = top_k_paragraphs_by_keyword(text=text, query=query, k=12, max_chars_each=1200)
        if picked:
            body = "\n\n".join(picked)
            return clip_text(
                f"SOURCE_NAME: {str(source_name or '').strip()}\n\nRFP_TEXT_EXCERPTS:\n{body}",
                max_chars=max_chars,
            )

    # Fallback: simple head clip
    return clip_text(
        f"SOURCE_NAME: {str(source_name or '').strip()}\n\nRFP_TEXT:\n{clip_text(text, max_chars=max_chars)}",
        max_chars=max_chars,
    )

