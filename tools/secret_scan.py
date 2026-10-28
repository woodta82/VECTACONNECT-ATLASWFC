#!/usr/bin/env python3
"""Repository secret scan. Exit 1 on any finding.

Unlike the VECTA 2.9.0 grep (which matched its own pattern text and the
placeholders in .env.example), patterns here require realistic secret
SHAPES, and this file is excluded by path rather than by weakening patterns.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", ".next", "__pycache__", ".pytest_cache", "legacy"}
SKIP_FILES = {Path(__file__).resolve()}
PATTERNS = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{24,}"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "assigned_password": re.compile(r"^(LOGIN_BOOTSTRAP_PASSWORD|POSTGRES_PASSWORD|ANTHROPIC_API_KEY)=(?!$|<|\$\{|change-me|dev-only)\S+", re.M),
    "db_url_with_password": re.compile(r"postgres(ql)?(\+psycopg)?://[^:\s/]+:(?!atlas@|dev-only@|test_only_pw@|\$\{|<)[^@\s]{6,}@"),
}


def scan() -> list[str]:
    findings = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(p in SKIP_DIRS for p in path.relative_to(ROOT).parts) or path.resolve() in SKIP_FILES:
            continue
        if path.suffix in {".png", ".jpg", ".ico", ".woff2", ".woff", ".ttf", ".bundle", ".pdf", ".xlsx"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pat in PATTERNS.items():
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {name}")
    return findings


if __name__ == "__main__":
    found = scan()
    for f in found:
        print(f"::error::possible secret {f}")
    print(f"secret scan: {len(found)} finding(s)")
    sys.exit(1 if found else 0)
