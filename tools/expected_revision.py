#!/usr/bin/env python3
"""Print the schema revision the application expects (backend/app/main.py), so checks never hard-code it."""
import re
from pathlib import Path

src = (Path(__file__).resolve().parents[1] / "backend" / "app" / "main.py").read_text()
print(re.search(r'EXPECTED_SCHEMA_REVISION = "(\w+)"', src).group(1))
