"""Shared test configuration.

Environment variables must be set BEFORE any `app.*` import, because the
SQLAlchemy engine and the Settings object are both created at module
import time. pytest imports conftest.py first, which is why this lives
here rather than in individual test modules.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_atlas.db")
os.environ["LOGIN_USERNAME"] = "tom@vectasports"
os.environ["LOGIN_PASSWORD"] = "TestBootstrap-Pw-1!"  # safe test credential, never production
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("ANTHROPIC_API_KEY", "")  # no live AI calls in any test
