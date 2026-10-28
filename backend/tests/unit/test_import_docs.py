"""The import documentation and templates are generated from the contracts; this fails if they drift."""
from pathlib import Path

from app.domain import import_docs
from app.domain import imports as im

ROOT = Path(__file__).resolve().parents[3]


def test_committed_import_docs_match_the_contracts():
    files = import_docs.render((ROOT / "docs" / "CONNECTORS_AND_DATASETS.md").read_text())
    stale = [rel for rel, content in files.items() if (ROOT / rel).read_text() != content]
    assert not stale, f"regenerate with: python tools/gen_import_templates.py ({stale})"


def test_every_dataset_is_documented_with_refresh_key_and_correction_mode():
    md = import_docs.fields_md()
    for name in im.CONTRACTS:
        assert f"## {name}" in md and name in import_docs.USED_BY
        assert import_docs.refresh_requirement(name) and import_docs.duplicate_key(name)
    for name, c in im.CONTRACTS.items():
        for f in c.fields:
            if f.required:
                assert f.description or f.name in import_docs.WHY_REQUIRED, (name, f.name)


def test_no_stale_claims_remain_in_the_docs():
    doc = (ROOT / "docs" / "CONNECTORS_AND_DATASETS.md").read_text()
    assert "dry run only" not in doc.lower() and "all 9 datasets" not in doc.lower()
