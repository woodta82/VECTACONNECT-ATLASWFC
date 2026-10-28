"""Regenerate docs/import-templates/*.csv, docs/import-templates/FIELDS.md and the dataset section of
docs/CONNECTORS_AND_DATASETS.md from the import contracts (backend/app/domain/import_docs.py), so they never drift.
backend/tests/unit/test_import_docs.py fails if the committed files differ from this output."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.domain import import_docs  # noqa: E402

files = import_docs.render((ROOT / "docs" / "CONNECTORS_AND_DATASETS.md").read_text())
for rel, content in files.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
print(f"{len(files)} files written")
