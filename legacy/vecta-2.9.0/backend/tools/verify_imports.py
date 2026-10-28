#!/usr/bin/env python3
"""Resolve every relative import in the backend the way Python does.

WHY THIS EXISTS
===============
A previous change shipped `from . import evidence` inside
`app/services/opportunity_service.py`. That resolves to
`app.services.evidence`, which does not exist — the module was one level
deeper than the import assumed, so it failed at import time with
`ImportError: cannot import name 'evidence' from 'app.services'`.

It was not caught because verification grepped for the import *string* and
confirmed the target names existed somewhere in the package. A grep cannot
see package depth, so it confirmed the wrong thing.

This script computes the actual target module path for every relative
import (`.` = current package, `..` = parent, and so on) and checks that
the module file exists and exports the requested name. It needs no
third-party packages installed, so it runs anywhere — including build
environments where fastapi/pydantic are unavailable and a real import
cannot be attempted.

Usage:  python3 tools/verify_imports.py
Exit code 0 = clean, 1 = problems found.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"


def module_path_for(package_parts: list[str]) -> Path | None:
    """Maps a dotted module path to a file, accepting either module.py or
    package/__init__.py."""
    base = BACKEND.joinpath(*package_parts)
    if base.with_suffix(".py").exists():
        return base.with_suffix(".py")
    if (base / "__init__.py").exists():
        return base / "__init__.py"
    return None


def exported_names(path: Path) -> set[str]:
    """Top-level names a module defines or re-exports."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
    return names


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    rel = path.relative_to(BACKEND)
    # Package containing this module, e.g. app/services/x.py -> ['app','services']
    own_package = list(rel.parts[:-1])

    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        return [f"{rel}: SYNTAX ERROR {e}"]

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level == 0:
            continue

        # This is the rule the grep could not see: one dot means the
        # module's own package, each extra dot climbs one level.
        climb = node.level - 1
        if climb > len(own_package):
            problems.append(f"{rel}:{node.lineno}: too many dots ({'.' * node.level}) — climbs above the root")
            continue
        target_package = own_package[: len(own_package) - climb] if climb else own_package

        if node.module:
            target_parts = target_package + node.module.split(".")
            target_file = module_path_for(target_parts)
            if target_file is None:
                problems.append(
                    f"{rel}:{node.lineno}: '{'.' * node.level}{node.module}' -> "
                    f"{'.'.join(target_parts)} does not exist"
                )
                continue
            available = exported_names(target_file)
            for alias in node.names:
                if alias.name == "*":
                    continue
                # A name may be either something the target module defines,
                # OR a submodule of it (`from .routers import admin` is
                # valid even though routers/__init__.py never names admin).
                is_submodule = module_path_for(target_parts + [alias.name]) is not None
                if alias.name not in available and not is_submodule:
                    problems.append(
                        f"{rel}:{node.lineno}: '{alias.name}' not found in {'.'.join(target_parts)}"
                    )
        else:
            # `from . import x` / `from .. import x` — x must be a sibling
            # module of the target package.
            for alias in node.names:
                target_parts = target_package + [alias.name]
                if module_path_for(target_parts) is None:
                    problems.append(
                        f"{rel}:{node.lineno}: '{'.' * node.level}{alias.name}' -> "
                        f"{'.'.join(target_parts)} does not exist"
                    )
    return problems


def check_unbound_names(path: Path) -> list[str]:
    """Catches a class of bug the import resolver cannot see.

    `verify_imports` checks that imports RESOLVE. It cannot see a name
    that was never imported at all — as happened when `CommercialValue`
    was used in change_detector.py without being added to the import list.
    That resolves fine (there is no bad import) but fails at runtime.

    This walks every module-level Name load and flags capitalised names
    that are never bound, which catches missing model/class imports
    without needing the packages installed.
    """
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []

    bound: set[str] = set(dir(__builtins__)) | {"self", "cls"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)

    used = {
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    # Capitalised only: lower-case false positives are too noisy to be useful.
    missing = sorted(u for u in (used - bound) if u[:1].isupper())
    rel = path.relative_to(BACKEND)
    return [f"{rel}: '{n}' used but never imported or defined" for n in missing]


def main() -> int:
    all_problems: list[str] = []
    files = sorted(APP.rglob("*.py"))
    for f in files:
        all_problems.extend(check_file(f))
        all_problems.extend(check_unbound_names(f))

    print(f"Checked {len(files)} modules under app/")
    if all_problems:
        print(f"\n{len(all_problems)} IMPORT PROBLEM(S):\n")
        for p in all_problems:
            print("  ✗", p)
        return 1
    print("All relative imports resolve correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
