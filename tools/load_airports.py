#!/usr/bin/env python3
"""Load or refresh the global airport directory (wrapper around `python -m app.airports_cli`, which also runs inside the API image).

  python tools/load_airports.py --file airports.csv [--version 2026-10-01] [--refreshed-at 2026-10-01]
  python tools/load_airports.py --download              # https://davidmegginson.github.io/ourairports-data/airports.csv
  python tools/load_airports.py --package DIR           # a verified import package (see app/airports_cli.py)

DATABASE_URL must point at the ATLAS database.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.airports_cli import main  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:]
    raise SystemExit(main(argv if argv and argv[0] in ("load", "package", "verify", "status") else ["load", *argv]))
