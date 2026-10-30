"""The global airport directory (30 Oct 2026): a maintained public dataset with provenance, searchable by name, IATA, ICAO, city and
country, including airports without an IATA code; multiple selection and a country or region scope.

Loading: `load_ourairports()` reads OurAirports' `airports.csv` (public domain; https://ourairports.com/data/, mirrored at
https://davidmegginson.github.io/ourairports-data/airports.csv) and upserts every row with the dataset's provenance and refresh date.
It runs from `tools/load_airports.py` or from Settings → Data sources (upload of the CSV) when the server cannot reach the site.
Before the dataset is loaded, the bundled seed (`reference/airports.py`, a curated starting set) is loaded once so an airport can be
chosen on a fresh install; the maintained dataset replaces every seed row it covers.

Presence in the directory never means an airport handles cargo. Airport selection is a scope; freight relevance is assessed from
evidence, separately. A company's office location, the airports it serves, a gateway and a final destination are different facts
(`organisation_airports.role`, `opportunity_airports.role`).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Iterable

from ..reference.airports import SEED, SEED_PROVENANCE
from ..reference.geography import COUNTRIES, REGIONS
from ..repo.db import Database

OURAIRPORTS = {"key": "ourairports", "name": "OurAirports airports.csv", "source": "OurAirports (ourairports.com), community-maintained, public domain",
               "url": "https://davidmegginson.github.io/ourairports-data/airports.csv", "licence": "Public domain (OurAirports data release)"}
BATCH = 2000
# OurAirports' airports.csv holds ~80,000 rows (2026). A maintained file with fewer than this many rows is a partial load (a sample, a regional
# extract): the directory then says "partial", never "full".
FULL_MIN_ROWS = 40000
_TYPES = {"large_airport", "medium_airport", "small_airport", "heliport", "seaplane_base", "balloonport", "closed"}


class DirectoryRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def ensure_seed(db: Database) -> None:
    """Loads the bundled seed once (idempotent, cheap when already loaded). Never overwrites maintained rows."""
    if db.one("refdata_get", key=SEED_PROVENANCE["key"]):
        return
    rows = [{"ident": s["icao"], "iata": s["iata"], "icao": s["icao"], "name": s["name"], "city": s["city"], "country": s["country"], "region_code": None,
             "type": s["type"], "status": "open", "scheduled_service": None, "latitude": None, "longitude": None, "aliases": [], "source_id": s["iata"]}
            for s in SEED]
    with db.transaction() as tx:
        tx.run("refdata_upsert", key=SEED_PROVENANCE["key"], name=SEED_PROVENANCE["name"], source=SEED_PROVENANCE["source"], url=None,
               licence=SEED_PROVENANCE["licence"], version=SEED_PROVENANCE["version"], refreshed=SEED_PROVENANCE["version"] + "T00:00:00Z",
               rows=len(rows), notes=SEED_PROVENANCE["notes"])
        tx.run("airport_dir_upsert_many", rows=rows, source=SEED_PROVENANCE["key"], refreshed=SEED_PROVENANCE["version"] + "T00:00:00Z")


def _rows_from_ourairports(text: str) -> Iterable[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    required = {"ident", "type", "name", "iso_country"}
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        raise DirectoryRejected(422, "Not an OurAirports airports.csv: the header must include ident, type, name and iso_country")
    for r in reader:
        ident = (r.get("ident") or "").strip().upper()
        country = (r.get("iso_country") or "").strip().upper()
        if not ident or len(country) != 2:
            continue
        typ = (r.get("type") or "unknown").strip()
        iata = (r.get("iata_code") or "").strip().upper()
        gps = (r.get("gps_code") or "").strip().upper()
        icao = gps if len(gps) == 4 and gps.isalpha() else (ident if len(ident) == 4 and ident.isalpha() else "")
        aliases = [k.strip() for k in (r.get("keywords") or "").split(",") if k.strip()]
        local = (r.get("local_code") or "").strip()
        if local and local not in (iata, icao):
            aliases.append(local)

        def num(v: str | None) -> float | None:
            try:
                return round(float(v), 6) if v not in (None, "") else None
            except ValueError:
                return None
        yield {"ident": ident, "iata": iata if len(iata) == 3 else "", "icao": icao, "name": (r.get("name") or ident).strip(), "city": (r.get("municipality") or "").strip(),
               "country": country, "region_code": (r.get("iso_region") or "").strip(), "type": typ if typ in _TYPES else "unknown",
               "status": "closed" if typ == "closed" else "open", "scheduled_service": (r.get("scheduled_service") or "").strip().lower() == "yes",
               "latitude": num(r.get("latitude_deg")), "longitude": num(r.get("longitude_deg")), "aliases": aliases[:12], "source_id": (r.get("id") or "").strip()}


def load_ourairports(db: Database, text: str, *, version: str | None = None, refreshed_at: datetime | None = None, notes: str | None = None) -> dict[str, Any]:
    """Upserts the dataset. `version`/`refreshed_at`: as stated by the publisher (the file's date); when unknown the load time is recorded as
    the load time only, never claimed as the publisher's refresh."""
    ensure_seed(db)
    refreshed = (refreshed_at or datetime.now(timezone.utc)).isoformat()
    total = 0
    batch: list[dict[str, Any]] = []
    with db.transaction() as tx:
        tx.run("refdata_upsert", key=OURAIRPORTS["key"], name=OURAIRPORTS["name"], source=OURAIRPORTS["source"], url=OURAIRPORTS["url"],
               licence=OURAIRPORTS["licence"], version=version or "loading", refreshed=refreshed_at.isoformat() if refreshed_at else None, rows=0, notes="loading")
        for row in _rows_from_ourairports(text):
            batch.append(row)
            if len(batch) >= BATCH:
                tx.run("airport_dir_upsert_many", rows=batch, source=OURAIRPORTS["key"], refreshed=refreshed)
                total += len(batch)
                batch = []
        if batch:
            tx.run("airport_dir_upsert_many", rows=batch, source=OURAIRPORTS["key"], refreshed=refreshed)
            total += len(batch)
        if total == 0:
            raise DirectoryRejected(422, "The file holds no airport rows")
        tx.run("refdata_upsert", key=OURAIRPORTS["key"], name=OURAIRPORTS["name"], source=OURAIRPORTS["source"], url=OURAIRPORTS["url"],
               licence=OURAIRPORTS["licence"], version=version or (refreshed_at.date().isoformat() if refreshed_at else "file date not stated"),
               refreshed=refreshed_at.isoformat() if refreshed_at else None, rows=total,
               notes=(notes or "") + ("" if refreshed_at else " Publisher refresh date not supplied with the file: only the load time is known."))
    return {"rows": total, "dataset": db.one("refdata_get", key=OURAIRPORTS["key"])}


def record_attempt(db: Database, *, ok: bool, source: str, detail: str) -> None:
    """The last attempt to load the maintained dataset (deployment step, CLI or upload), so a failure stays visible."""
    import json
    db.run("flag_set", key="airport_load_attempt", value=json.dumps({"at": datetime.now(timezone.utc).isoformat(), "ok": ok, "source": source, "detail": detail[:300]}))


def status(db: Database) -> dict[str, Any]:
    """Which directory the application is using — `seed` (the bundled starting set only), `partial` (a maintained file with fewer than
    FULL_MIN_ROWS rows, e.g. a sample) or `full` — with the dataset's source, version, publisher refresh date, load time and total records."""
    ensure_seed(db)
    c = db.one("airport_dir_count") or {}
    total, maintained = int(c.get("n") or 0), int(c.get("maintained") or 0)
    sets = db.all("refdata_list")
    ds = next((d for d in sets if d["key"] == OURAIRPORTS["key"]), None)
    seed = next((d for d in sets if d["key"] == SEED_PROVENANCE["key"]), None)
    using = "full" if ds and int(ds.get("rows_loaded") or 0) >= FULL_MIN_ROWS else "partial" if maintained else "seed"
    attempt = db.scalar("flag_get", key="airport_load_attempt")
    active = ds if using != "seed" else seed
    note = {"full": f"Full directory in use: {OURAIRPORTS['name']} ({int(ds['rows_loaded']) if ds else 0} rows loaded); the bundled seed rows it covers were replaced.",
            "partial": f"Partial directory: a maintained file with {int(ds['rows_loaded']) if ds else maintained} rows is loaded (fewer than {FULL_MIN_ROWS}, so not the complete "
                       "dataset); airports it does not cover still come from the bundled seed. Load the complete airports.csv.",
            "seed": "Only the bundled seed is loaded (a curated starting set of airports with IATA codes). Load OurAirports' airports.csv — at deployment "
                    "(python -m app.airports_cli load --auto), as a verified import package, or by upload here — for the full directory."}[using]
    return {"using": using, "using_label": {"full": "Full directory", "partial": "Partial directory (maintained file + seed)", "seed": "Bundled seed only"}[using],
            "total_records": total, "airports": total, "maintained_rows": maintained, "seed_rows": total - maintained, "maintained": maintained > 0,
            "full_min_rows": FULL_MIN_ROWS,
            "dataset": ({"key": active["key"], "name": active["name"], "source": active["source"], "url": active.get("url"), "licence": active.get("licence"),
                         "version": active.get("version"), "refreshed_at": active.get("refreshed_at"), "loaded_at": active.get("loaded_at"),
                         "rows_loaded": int(active.get("rows_loaded") or 0)} if active else None),
            "datasets": sets, "note": note + (f" The last load attempt ({attempt['source']}, {attempt['at'][:16].replace('T', ' ')} UTC) FAILED: {attempt['detail']}"
                                              if attempt and not attempt.get("ok") else ""),
            "last_attempt": attempt,
            "cargo_rule": "Presence in the directory never means an airport handles cargo: freight relevance is researched separately, from evidence."}


def search(db: Database, q: str | None, *, country: str | None = None, include_closed: bool = False, limit: int = 20) -> list[dict[str, Any]]:
    ensure_seed(db)
    q = (q or "").strip() or None
    if q and not country and len(q) >= 4:
        # a country typed by name ('Lithuania', 'united arab'): that country's airports
        named = [code for code, v in COUNTRIES.items() if v[0].lower() == q.lower()] or \
                [code for code, v in COUNTRIES.items() if v[0].lower().startswith(q.lower())]
        if len(named) == 1 and not db.all("airport_dir_search", q=q, country=None, include_closed=include_closed, limit=1):
            country, q = named[0], None
    if q is None and not country:
        return []
    rows = db.all("airport_dir_search", q=q, country=(country or "").upper() or None, include_closed=include_closed, limit=limit)
    for r in rows:
        r["label"] = label(r)
        r["country_name"] = COUNTRIES.get(r["country"], (r["country"],))[0]
    return rows


def label(a: dict[str, Any]) -> str:
    code = a.get("iata") or a.get("icao") or a.get("ident")
    extra = f" · {a['icao']}" if a.get("iata") and a.get("icao") else ("" if a.get("iata") else " · no IATA code")
    return f"{a['name']} ({code}{extra})" + (f", {a['city']}" if a.get("city") and a["city"] != a["name"] else "")


def resolve(db: Database, code: str | None) -> dict[str, Any] | None:
    if not code or not code.strip():
        return None
    ensure_seed(db)
    return db.one("airport_dir_get", code=code.strip())


def resolve_many(db: Database, codes: Iterable[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """(directory rows, codes not in the directory — kept as written and labelled unresolved)."""
    found, missing = [], []
    for c in codes:
        a = resolve(db, c)
        (found.append(a) if a else missing.append(c.strip().upper()))
    return found, missing


def idents_for(db: Database, idents: Iterable[str]) -> list[dict[str, Any]]:
    ids = [i for i in idents if i]
    return db.all("airport_dir_many", idents=ids) if ids else []


def scope_countries(db: Database, *, countries: list[str], region: str | None) -> list[str]:
    """'All airports in this country / region' is a country scope: the airports are not enumerated."""
    if region and region in REGIONS:
        return list(REGIONS[region][2])
    return countries
