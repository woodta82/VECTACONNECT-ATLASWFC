"""The global airport directory at deployment (30 Oct 2026, amendment item 3).

    python -m app.airports_cli load --download                     # OurAirports airports.csv from the publisher's mirror
    python -m app.airports_cli load --file airports.csv [--version V] [--refreshed-at ISO]
    python -m app.airports_cli load --package DIR                  # a verified import package (below)
    python -m app.airports_cli load --auto --if-stale 30 --optional  # the deployment step: package if AIRPORTS_PACKAGE is set, else download;
                                                                    # skipped when the full directory is younger than 30 days; a failure is
                                                                    # reported and exits 0 so the application still starts on the seed
    python -m app.airports_cli package --file airports.csv --version 2026-10-28 --refreshed-at 2026-10-28 --out DIR
    python -m app.airports_cli verify DIR
    python -m app.airports_cli status

An import package is the publisher's file, unchanged, plus a manifest: DIR/airports.csv.gz and DIR/manifest.json with the dataset name,
source, licence, version, publisher refresh date, row count, IATA and ICAO counts, the column header and the SHA-256 of the uncompressed CSV.
`verify` and `load --package` recompute every figure and refuse a package that does not match. OurAirports releases its data into the public
domain, so a package may be redistributed; any other source must be checked for its licence first.

DATABASE_URL must point at the ATLAS database.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGE_FORMAT = "atlas-airports-package/1"


def _db():
    from .repo.db import SQLAlchemyDatabase
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return SQLAlchemyDatabase(url.replace("postgresql://", "postgresql+psycopg://", 1) if url.startswith("postgresql://") else url)


def describe(text: str) -> dict[str, Any]:
    """Figures recomputed from the CSV itself: rows, IATA and ICAO counts, header, SHA-256."""
    reader = csv.DictReader(io.StringIO(text))
    rows = iata = icao = no_iata = 0
    for r in reader:
        rows += 1
        if (r.get("iata_code") or "").strip():
            iata += 1
        else:
            no_iata += 1
        gps = (r.get("gps_code") or "").strip()
        if len(gps) == 4 and gps.isalpha():
            icao += 1
    return {"rows": rows, "with_iata": iata, "without_iata": no_iata, "with_icao": icao, "columns": reader.fieldnames or [],
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def build_package(text: str, out: Path, *, version: str, refreshed_at: str | None, source_url: str | None = None) -> dict[str, Any]:
    from .services.airport_directory import FULL_MIN_ROWS, OURAIRPORTS
    out.mkdir(parents=True, exist_ok=True)
    d = describe(text)
    if not {"ident", "type", "name", "iso_country"} <= set(d["columns"]):
        raise SystemExit("not an OurAirports airports.csv: the header must include ident, type, name and iso_country")
    manifest = {"format": PACKAGE_FORMAT, "dataset": OURAIRPORTS["name"], "source": OURAIRPORTS["source"], "source_url": source_url or OURAIRPORTS["url"],
                "licence": OURAIRPORTS["licence"], "version": version, "refreshed_at": refreshed_at, "packaged_at": datetime.now(timezone.utc).isoformat(),
                "complete": d["rows"] >= FULL_MIN_ROWS, **d}
    with gzip.open(out / "airports.csv.gz", "wt", encoding="utf-8", newline="") as f:
        f.write(text)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def read_package(path: Path) -> tuple[str, dict[str, Any]]:
    """(the CSV text, the manifest), after recomputing every figure; refuses a package that does not match its manifest."""
    mf = path / "manifest.json"
    data = path / "airports.csv.gz"
    if not mf.exists() or not data.exists():
        raise SystemExit(f"{path}: manifest.json and airports.csv.gz are required")
    manifest = json.loads(mf.read_text())
    if manifest.get("format") != PACKAGE_FORMAT:
        raise SystemExit(f"{path}: unknown package format {manifest.get('format')!r}")
    with gzip.open(data, "rt", encoding="utf-8", newline="") as f:
        text = f.read()
    d = describe(text)
    bad = [k for k in ("sha256", "rows", "with_iata", "with_icao", "columns") if manifest.get(k) != d[k]]
    if bad:
        raise SystemExit(f"{path}: the package does not match its manifest ({', '.join(bad)}): refused")
    return text, manifest


def _download() -> tuple[str, datetime | None, str]:
    from .services.airport_directory import OURAIRPORTS
    with urllib.request.urlopen(OURAIRPORTS["url"], timeout=180) as r:  # noqa: S310 - fixed public URL
        text = r.read().decode("utf-8", "replace")
        last = r.headers.get("Last-Modified")
    refreshed = datetime.strptime(last, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc) if last else None
    return text, refreshed, OURAIRPORTS["url"]


def _source_label(a: argparse.Namespace) -> str:
    if a.package or (a.auto and os.environ.get("AIRPORTS_PACKAGE")):
        return "import package"
    return "file" if a.file else "download"


def load(a: argparse.Namespace) -> int:
    from .services import airport_directory as ad
    db = _db()
    st = ad.status(db)
    if a.if_stale is not None and st["using"] == "full" and st["dataset"] and st["dataset"].get("loaded_at"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(st["dataset"]["loaded_at"]))).days
        if age < a.if_stale:
            print(f"[airports] full directory loaded {age} day(s) ago ({st['total_records']} records, version {st['dataset'].get('version')}): nothing to do")
            return 0
    try:
        notes = a.notes
        if a.package or (a.auto and os.environ.get("AIRPORTS_PACKAGE")):
            text, manifest = read_package(Path(a.package or os.environ["AIRPORTS_PACKAGE"]))
            version, refreshed = manifest["version"], (datetime.fromisoformat(manifest["refreshed_at"]) if manifest.get("refreshed_at") else None)
            notes = (notes or "") + f" Loaded from a verified import package (SHA-256 {manifest['sha256'][:16]}…, {manifest['rows']} rows)."
        elif a.file:
            text = Path(a.file).read_text(encoding="utf-8", errors="replace")
            version, refreshed = a.version, None
        elif a.download or a.auto:
            text, refreshed, _ = _download()
            version = a.version
        else:
            raise SystemExit("load: --file, --download, --package or --auto")
        if a.refreshed_at:
            refreshed = datetime.fromisoformat(a.refreshed_at)
        if refreshed and refreshed.tzinfo is None:
            refreshed = refreshed.replace(tzinfo=timezone.utc)
        out = ad.load_ourairports(db, text, version=version or (refreshed.date().isoformat() if refreshed else None), refreshed_at=refreshed, notes=notes)
    except (OSError, ValueError, ad.DirectoryRejected) as exc:
        msg = getattr(exc, "detail", None) or str(exc)
        ad.record_attempt(db, ok=False, source=_source_label(a), detail=msg)
        print(f"[airports] the maintained dataset was NOT loaded: {msg}. The application uses {st['using']} ({st['total_records']} records).", file=sys.stderr)
        return 0 if a.optional else 1
    ad.record_attempt(db, ok=True, source=_source_label(a), detail=f"{out['rows']} rows loaded")
    after = ad.status(db)
    print(f"[airports] loaded {out['rows']} rows; using {after['using']} directory: {after['total_records']} records; "
          f"dataset {out['dataset']['name']} version {out['dataset']['version']}, publisher refresh {out['dataset']['refreshed_at'] or 'not stated'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.airports_cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ld = sub.add_parser("load")
    ld.add_argument("--file")
    ld.add_argument("--download", action="store_true")
    ld.add_argument("--package")
    ld.add_argument("--auto", action="store_true", help="package when AIRPORTS_PACKAGE is set, else download")
    ld.add_argument("--version")
    ld.add_argument("--refreshed-at")
    ld.add_argument("--notes")
    ld.add_argument("--if-stale", type=int, help="skip when the full directory was loaded fewer than N days ago")
    ld.add_argument("--optional", action="store_true", help="report a failure and exit 0 (the deployment continues on the seed)")
    pk = sub.add_parser("package")
    pk.add_argument("--file", required=True)
    pk.add_argument("--version", required=True)
    pk.add_argument("--refreshed-at")
    pk.add_argument("--source-url")
    pk.add_argument("--out", required=True)
    vf = sub.add_parser("verify")
    vf.add_argument("path")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "load":
        return load(a)
    if a.cmd == "package":
        m = build_package(Path(a.file).read_text(encoding="utf-8", errors="replace"), Path(a.out), version=a.version, refreshed_at=a.refreshed_at, source_url=a.source_url)
        print(json.dumps({k: m[k] for k in ("version", "refreshed_at", "rows", "with_iata", "without_iata", "with_icao", "complete", "sha256")}, indent=2))
        return 0
    if a.cmd == "verify":
        _text, m = read_package(Path(a.path))
        print(f"verified: {m['rows']} rows, version {m['version']}, SHA-256 {m['sha256']}, complete: {m['complete']}")
        return 0
    from .services import airport_directory as ad
    print(json.dumps(ad.status(_db()), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
