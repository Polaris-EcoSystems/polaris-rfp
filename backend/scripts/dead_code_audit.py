from __future__ import annotations

"""
Dead-code / reachability audit (best-effort).

Goal: identify Python modules in `app/` that are not reachable from real entrypoints.

Notes:
- This is a static AST import graph; dynamic imports won't be captured.
- Marked "unreachable" does NOT automatically mean safe to delete.
  Use this as a shortlist for manual review + test verification.
"""

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class AuditResult:
    reachable: set[str]
    unreachable: set[str]
    parse_errors: dict[str, str]


def _iter_py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        out.append(p)
    return out


def _module_name_from_path(app_root: Path, file_path: Path) -> str | None:
    try:
        rel = file_path.relative_to(app_root)
    except Exception:
        return None
    if rel.name == "__init__.py":
        parts = rel.parent.parts
    else:
        parts = (*rel.parent.parts, rel.stem)
    if not parts:
        return "app"
    return "app." + ".".join(parts)


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imports_from_ast(tree: ast.AST, *, within_module: str, known_modules: set[str]) -> set[str]:
    """
    Return imported module names as best-effort dotted paths.
    Only returns imports under the `app.*` namespace.
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = str(alias.name or "").strip()
                if name == "app" or name.startswith("app."):
                    out.add(name)
        elif isinstance(node, ast.ImportFrom):
            mod = str(node.module or "").strip()
            level = int(node.level or 0)

            # Resolve relative imports into app.* (best-effort)
            resolved_mod: str | None = None
            if level and within_module.startswith("app."):
                # PEP 328: level=1 is "current package", level=2 is parent, etc.
                # So we go up (level-1) from the current package.
                pkg_parts = within_module.split(".")[:-1]
                ascend = max(0, level - 1)
                prefix = pkg_parts[:-ascend] if ascend else pkg_parts
                if mod:
                    abs_mod = ".".join([*prefix, mod])
                else:
                    abs_mod = ".".join(prefix)
                if abs_mod:
                    abs_mod = "app." + abs_mod if not abs_mod.startswith("app.") else abs_mod
                    if abs_mod == "app" or abs_mod.startswith("app."):
                        resolved_mod = abs_mod
                        out.add(abs_mod)
            else:
                if mod == "app" or mod.startswith("app."):
                    resolved_mod = mod
                    out.add(mod)

            # Handle `from X import Y` where Y is a submodule file/package.
            # In Python this triggers import of X.Y; represent that edge when possible.
            if resolved_mod:
                for alias in node.names:
                    nm = str(alias.name or "").strip()
                    if not nm or nm == "*":
                        continue
                    cand = f"{resolved_mod}.{nm}"
                    if cand in known_modules:
                        out.add(cand)
    return out


def build_import_graph(app_root: Path) -> tuple[dict[str, set[str]], dict[str, str]]:
    graph: dict[str, set[str]] = {}
    parse_errors: dict[str, str] = {}

    files = _iter_py_files(app_root)
    known: set[str] = set()
    for fp in files:
        mod = _module_name_from_path(app_root, fp)
        if mod:
            known.add(mod)

    for fp in files:
        mod = _module_name_from_path(app_root, fp)
        if not mod:
            continue
        try:
            src = _safe_read_text(fp)
            tree = ast.parse(src, filename=str(fp))
            graph[mod] = _imports_from_ast(tree, within_module=mod, known_modules=known)
        except Exception as e:
            parse_errors[str(fp)] = str(e)
            graph[mod] = set()
    return graph, parse_errors


def reachable_from(graph: dict[str, set[str]], roots: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    stack: list[str] = [r for r in roots if r in graph]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in graph.get(cur, set()):
            if nxt in graph and nxt not in seen:
                stack.append(nxt)
    return seen


def audit(app_root: Path, *, roots: list[str]) -> AuditResult:
    graph, errors = build_import_graph(app_root)
    reach = reachable_from(graph, roots)
    # Mark parent packages as reachable when any submodule is reachable.
    expanded: set[str] = set(reach)
    for m in list(reach):
        parts = m.split(".")
        # progressively add prefixes: app, app.foo, app.foo.bar, ...
        for i in range(1, len(parts)):
            pref = ".".join(parts[:i])
            if pref in graph:
                expanded.add(pref)
    reach = expanded
    all_mods = set(graph.keys())
    unreachable = all_mods - reach
    return AuditResult(reachable=reach, unreachable=unreachable, parse_errors=errors)


def _default_roots() -> list[str]:
    # Real entrypoints that typically get loaded in prod and tests.
    return [
        "app.main",
        "app.browser_worker",
        "app.workers.contracting_worker",
        "app.workers.outbox_worker",
    ]


def main() -> None:
    repo_root = Path(os.getcwd()).resolve()
    app_root = repo_root / "app"
    res = audit(app_root, roots=_default_roots())

    print("=== Dead code audit (best-effort) ===")
    print(f"app_root: {app_root}")
    print(f"roots: {', '.join(_default_roots())}")
    print("")
    if res.parse_errors:
        print(f"parse_errors: {len(res.parse_errors)}")
        for k, v in list(res.parse_errors.items())[:20]:
            print(f"- {k}: {v}")
        print("")

    print(f"reachable: {len(res.reachable)}")
    print(f"unreachable: {len(res.unreachable)}")
    print("")
    print("Unreachable modules (first 200):")
    for m in sorted(res.unreachable)[:200]:
        print(f"- {m}")


if __name__ == "__main__":
    main()


