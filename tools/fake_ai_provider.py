"""SIMULATED Anthropic Messages API for local verification only. Returns canned claim JSON
for the synthetic fixture documents (backend/tests/fixtures/servers.py). It does not
interpret documents and must never be configured in production (AI_API_BASE_URL must be
https outside development/test)."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.fixtures.servers import FakeAIProvider  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    with FakeAIProvider(ap.parse_args().port) as s:
        print(f"SIMULATED AI provider on {s.base}", flush=True)
        while True:
            time.sleep(3600)
