"""Entity resolution to canonical records (directive §3).

Airlines, organisations, countries/territories and airports named in
evidence are resolved to canonical rows. Exact matches (IATA code, canonical
name, recorded alias) resolve; anything else creates a new canonical record
flagged `auto_created`, with its provenance, and a SIMILAR existing record
(by name) becomes a merge-review candidate. Fuzzy matches are never merged
automatically.
"""
from __future__ import annotations

import re

from ..domain.identity import name_similarity
from ..reference.geography import COUNTRIES, resolve_country
from ..repo.db import Database

SIMILAR = 0.6


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def airport_country(db: Database, code: str) -> str | None:
    if not re.fullmatch(r"[A-Z]{3}", code or ""):
        return None
    row = db.one("airport_country", code=code)
    return row["country"] if row else None


def _merge_candidates_for(db: Database, new_id: str, name: str, kind: str) -> None:
    for r in db.all("organisations_by_kind", kind=kind):
        if r["id"] == new_id:
            continue
        score = name_similarity(name, r["canonical_name"])
        if score >= SIMILAR:
            left, right = sorted([r["id"], new_id])
            db.run("merge_candidate_add", entity_type="organisation", left=left, right=right,
                   reason=f"similar names: {r['canonical_name']!r} / {name!r}", score=round(score, 4))


def organisation(db: Database, name: str, kind: str, *, provenance_id: str | None, country: str | None = None) -> str:
    oid = db.scalar("org_by_name", name=name, norm=_norm(name))
    if oid is not None:
        return str(oid)
    oid = str(db.scalar("org_insert_auto", name=name, kind=kind, prov=provenance_id, country=country))
    db.run("alias_insert", org=oid, alias=name, norm=_norm(name), prov=provenance_id)
    _merge_candidates_for(db, oid, name, kind)
    return oid


def airline(db: Database, *, name: str | None, iata: str | None, provenance_id: str | None) -> str | None:
    """Resolve an airline by IATA designator (when the code itself is
    supported by evidence) or by name/alias."""
    if iata and re.fullmatch(r"[A-Z0-9]{2}", iata):
        hit = db.scalar("airline_by_iata", code=iata)
        if hit is not None:
            return str(hit)
    if name:
        hit = db.scalar("org_by_name", name=name, norm=_norm(name))
        if hit is not None:
            db.run("airline_ensure", org=str(hit), iata=None)
            return str(hit)
        oid = organisation(db, name, "airline", provenance_id=provenance_id)
        taken = iata and db.scalar("airline_by_iata", code=iata) is not None
        db.run("airline_ensure", org=oid, iata=None if (taken or not iata) else iata)
        return oid
    return None


def territory_for_country(db: Database, code: str) -> str | None:
    if code not in COUNTRIES:
        return None
    return str(db.scalar("territory_ensure_country", code=code, name=COUNTRIES[code][0]))


def country(text: str | None) -> str | None:
    return resolve_country(text)
