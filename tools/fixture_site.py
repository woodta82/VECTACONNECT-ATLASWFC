"""Serve the SYNTHETIC fixture source site (backend/tests/fixtures/site) on 127.0.0.1 for
local verification and demonstration. Not a real source; see the site's README."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.fixtures.servers import FixtureSite  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8089)
    with FixtureSite(ap.parse_args().port) as s:
        print(f"fixture site on {s.base}", flush=True)
        while True:
            time.sleep(3600)
