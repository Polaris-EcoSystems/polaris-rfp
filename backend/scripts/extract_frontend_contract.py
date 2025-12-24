from __future__ import annotations

"""
Extract the frontend→backend API contract from `frontend/lib/api.ts`.

This looks for patterns like:
  api.get(proxyUrl('/api/rfp/'))
  api.post(proxyUrl(`/api/rfp/${cleanPathToken(id)}/review`), ...)

We normalize:
- method: GET/POST/PUT/DELETE
- path templates: `/api/rfp/{id}/review` (best-effort)

Output is JSON lines to stdout:
  {"method":"GET","path":"/api/rfp/"}
"""

import json
import os
import re
from pathlib import Path


METHODS = ["get", "post", "put", "delete", "patch"]


def normalize_path_template(raw: str) -> str:
    s = str(raw or "")
    # Replace ${...} template segments with {var}
    # Keep it simple; most templates are `${cleanPathToken(x)}` or `${encodeURIComponent(x)}`
    s = re.sub(r"\$\{[^}]+\}", "{var}", s)
    # Collapse duplicate slashes
    s = re.sub(r"//+", "/", s)
    return s


def _parse_string_literal(src: str, i: int) -> tuple[str | None, int]:
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
        if q in ("'", '"') and ch == "\\" and i + 1 < len(src):
            out.append(src[i + 1])
            i += 2
            continue
        out.append(ch)
        i += 1
    return None, i


def _extract_call_span(src: str, open_paren_idx: int) -> tuple[int, int] | None:
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


def extract_contract_from_source(ts_src: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()

    for m in re.finditer(r"\bapi\.(get|post|put|delete|patch)\b", ts_src):
        method = str(m.group(1) or "").upper()
        j = m.end()
        while j < len(ts_src) and ts_src[j].isspace():
            j += 1
        if j < len(ts_src) and ts_src[j] == "<":
            j = _skip_ts_generics(ts_src, j)
            while j < len(ts_src) and ts_src[j].isspace():
                j += 1
        if j >= len(ts_src) or ts_src[j] != "(":
            continue
        open_idx = j
        span = _extract_call_span(ts_src, open_idx) if open_idx >= 0 else None
        if not span:
            continue
        call_src = ts_src[span[0] : span[1]]
        raw = _extract_proxy_url_string_from_call(call_src)
        if not raw:
            continue
        raw = raw.strip()
        if not raw.startswith("/"):
            continue
        out.add((method, normalize_path_template(raw)))

    # Some calls bypass proxyUrl (Next session endpoints). Ignore those (not backend FastAPI).
    # But keep direct backend paths if they start with /api/ and are not /api/session/* etc.
    direct_pat = re.compile(
        r"api\.(get|post|put|delete|patch)\s*\(\s*(?P<q>`|'|\")(?P<path>/api/[^\"'`\n]+)(?P=q)",
        re.MULTILINE,
    )
    for m in direct_pat.finditer(ts_src):
        path = str(m.group("path") or "")
        if path.startswith("/api/session/") or path.startswith("/api/auth/"):
            continue
        out.add((m.group(1).upper(), normalize_path_template(path)))

    return out


def extract_contract_from_frontend(frontend_root: Path) -> list[dict[str, str]]:
    out: set[tuple[str, str]] = set()
    for fp in frontend_root.rglob("*.ts"):
        if "node_modules" in fp.parts or ".next" in fp.parts:
            continue
        out |= extract_contract_from_source(fp.read_text(encoding="utf-8"))
    for fp in frontend_root.rglob("*.tsx"):
        if "node_modules" in fp.parts or ".next" in fp.parts:
            continue
        out |= extract_contract_from_source(fp.read_text(encoding="utf-8"))
    return [{"method": method, "path": path} for (method, path) in sorted(out)]


def main() -> None:
    repo_root = Path(os.getcwd()).resolve().parent  # backend/ -> repo root
    frontend_root = repo_root / "frontend"
    items = extract_contract_from_frontend(frontend_root)
    for it in items:
        print(json.dumps(it, ensure_ascii=False))


if __name__ == "__main__":
    main()


