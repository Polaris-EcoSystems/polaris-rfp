from __future__ import annotations

import re
from pathlib import Path

from app.main import create_app


def _normalize_template(p: str) -> str:
    p = str(p or "").split("?", 1)[0]
    # Normalize both FastAPI `{id}` and our extracted `{var}` to `{}` tokens.
    p = re.sub(r"\{[^}]+\}", "{}", p)
    # In template literals we sometimes append `?foo=...`; after ${} normalization it can
    # leave a trailing "{}" right after the path segment. Strip it.
    p = re.sub(r"\{\}\s*$", "", p)
    return p

def _parse_string_literal(src: str, i: int) -> tuple[str | None, int]:
    """
    Parse a JS/TS string literal starting at src[i] where src[i] is one of ', ", `.
    Returns (content, next_index_after_literal) or (None, i) if parsing fails.
    """
    if i < 0 or i >= len(src):
        return None, i
    q = src[i]
    if q not in ("'", '"', "`"):
        return None, i
    i += 1
    out: list[str] = []
    while i < len(src):
        ch = src[i]
        if ch == q:
            return "".join(out), i + 1
        # Handle escapes for ' and "
        if q in ("'", '"') and ch == "\\" and i + 1 < len(src):
            out.append(src[i + 1])
            i += 2
            continue
        # For template literals, just accumulate raw; we'll normalize ${...} later.
        out.append(ch)
        i += 1
    return None, i


def _extract_call_span(src: str, open_paren_idx: int) -> tuple[int, int] | None:
    """
    Given index of an opening '(' in src, return (start, end_exclusive) span for the
    balanced parenthesis region, skipping anything inside string literals.
    """
    if open_paren_idx < 0 or open_paren_idx >= len(src) or src[open_paren_idx] != "(":
        return None
    depth = 0
    i = open_paren_idx
    in_s = False
    in_d = False
    in_b = False
    esc = False
    while i < len(src):
        ch = src[i]
        if esc:
            esc = False
            i += 1
            continue
        if in_s:
            if ch == "\\":
                esc = True
            elif ch == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            if ch == "\\":
                esc = True
            elif ch == '"':
                in_d = False
            i += 1
            continue
        if in_b:
            # Template literal: treat everything as string; ignore parentheses inside.
            if ch == "`":
                in_b = False
            i += 1
            continue

        if ch == "'":
            in_s = True
        elif ch == '"':
            in_d = True
        elif ch == "`":
            in_b = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return open_paren_idx, i + 1
        i += 1
    return None


def _extract_proxy_url_string_from_call(call_src: str) -> str | None:
    """
    Extract the first string literal argument to proxyUrl(...) within a call substring.
    Allows whitespace/newlines between proxyUrl( and the literal.
    """
    j = call_src.find("proxyUrl")
    if j < 0:
        return None
    j = call_src.find("(", j)
    if j < 0:
        return None
    j += 1
    while j < len(call_src) and call_src[j].isspace():
        j += 1
    lit, _next = _parse_string_literal(call_src, j)
    return lit


def _skip_ts_generics(src: str, i: int) -> int:
    """
    If src[i] is '<', skip a TypeScript generic argument list like <T> or <{...}>.
    Best-effort: counts nested angle brackets; ignores strings inside.
    Returns the first index after the closing '>' (or the original i if not a generic).
    """
    if i < 0 or i >= len(src) or src[i] != "<":
        return i
    depth = 0
    in_s = in_d = in_b = False
    esc = False
    while i < len(src):
        ch = src[i]
        if esc:
            esc = False
            i += 1
            continue
        if in_s:
            if ch == "\\":
                esc = True
            elif ch == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            if ch == "\\":
                esc = True
            elif ch == '"':
                in_d = False
            i += 1
            continue
        if in_b:
            if ch == "`":
                in_b = False
            i += 1
            continue

        if ch == "'":
            in_s = True
        elif ch == '"':
            in_d = True
        elif ch == "`":
            in_b = True
        elif ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _extract_proxy_url_string(src: str, start: int) -> str | None:
    """
    Given a source string and an index near a proxyUrl( call, extract the first
    string literal argument to proxyUrl(...), allowing newlines/whitespace.
    """
    j = src.find("proxyUrl", start)
    if j < 0:
        return None
    j = src.find("(", j)
    if j < 0:
        return None
    j += 1
    # Skip whitespace/newlines
    while j < len(src) and src[j].isspace():
        j += 1
    if j >= len(src):
        return None
    lit, _next = _parse_string_literal(src, j)
    return lit


def _extract_frontend_contract() -> set[tuple[str, str]]:
    """
    Parse `frontend/lib/api.ts` and return (METHOD, normalized_path_template).
    This intentionally duplicates the logic of `scripts/extract_frontend_contract.py`
    so CI fails loudly if the frontend adds an API dependency.
    """
    out: set[tuple[str, str]] = set()

    repo_root = Path(__file__).resolve().parents[2]  # backend/tests -> repo root
    frontend_root = repo_root / "frontend"
    for fp in list(frontend_root.rglob("*.ts")) + list(frontend_root.rglob("*.tsx")):
        if "node_modules" in fp.parts or ".next" in fp.parts:
            continue
        src = fp.read_text(encoding="utf-8")
        for m in re.finditer(r"\bapi\.(get|post|put|delete|patch)\b", src):
            method = str(m.group(1) or "").upper()
            j = m.end()
            # Skip whitespace
            while j < len(src) and src[j].isspace():
                j += 1
            # Skip optional TS generics: api.get<...>(...)
            if j < len(src) and src[j] == "<":
                j = _skip_ts_generics(src, j)
                while j < len(src) and src[j].isspace():
                    j += 1
            if j >= len(src) or src[j] != "(":
                continue
            open_idx = j
            span = _extract_call_span(src, open_idx) if open_idx >= 0 else None
            if not span:
                continue
            call_src = src[span[0] : span[1]]
            raw = _extract_proxy_url_string_from_call(call_src)
            if not raw:
                continue
            raw = raw.strip()
            if not raw.startswith("/"):
                continue
            path = re.sub(r"\$\{[^}]+\}", "{}", raw)
            out.add((method, _normalize_template(path)))

        # Also capture Next.js server route handlers that call backend directly:
        #   fetch(`${getBackendBaseUrl()}/api/...`, { method: 'POST', ... })
        for m in re.finditer(r"\bfetch\b", src):
            open_idx = src.find("(", m.start())
            sp = _extract_call_span(src, open_idx) if open_idx >= 0 else None
            if not sp:
                continue
            call_src = src[sp[0] : sp[1]]

            # Only consider calls that reference getBackendBaseUrl()
            if "getBackendBaseUrl()" not in call_src:
                continue

            # Method (default GET)
            method = "GET"
            mm = re.search(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]", call_src)
            if mm:
                method = str(mm.group(1) or "GET").upper()

            # Extract first template literal or string literal argument (best-effort)
            # Prefer template literal since these are usually backticks.
            first_arg = None
            j = call_src.find("(")
            if j >= 0:
                j += 1
                while j < len(call_src) and call_src[j].isspace():
                    j += 1
                lit, _next = _parse_string_literal(call_src, j)
                first_arg = lit
            if not first_arg:
                continue

            if "/api/" not in first_arg:
                continue

            # Take substring starting at /api/
            api_idx = first_arg.find("/api/")
            path = first_arg[api_idx:]
            path = re.sub(r"\$\{[^}]+\}", "{}", path)
            out.add((method, _normalize_template(path)))

    return out


def _fastapi_routes() -> set[tuple[str, str]]:
    app = create_app()
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if not path or not methods:
            continue
        norm_path = _normalize_template(path)
        for m in methods:
            out.add((str(m).upper(), norm_path))
    return out


def test_frontend_api_contract_routes_exist():
    required = _extract_frontend_contract()
    available = _fastapi_routes()

    # Frontend uses proxyUrl('/api/...') so all required paths should be on FastAPI.
    missing = sorted([f"{m} {p}" for (m, p) in required if (m, p) not in available])
    assert not missing, "Missing backend routes required by frontend:\n" + "\n".join(missing)


