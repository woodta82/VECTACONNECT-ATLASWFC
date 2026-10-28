"""Import service (directive §10): upload -> mapping -> validation -> preview ->
review -> commit -> reconciliation, for every dataset including master data.

- PREVIEW (dry run) stores the uploaded file, the mapping, the file's time
  zone and a fingerprint of the planned effects and row errors.
- COMMIT takes only the preview id. It re-plans from the STORED file and
  mapping against the database as it is now; if the plan differs from the
  one the reviewer saw (records changed in between), the commit is refused
  and a new preview is required. A preview can be committed once.
- Bad rows are quarantined with their raw values, never dropped; a commit
  with quarantined rows is marked PARTIAL and says so.
- Every written row records its previous values (import_row_effects), so
  supported datasets can be REVERSED: inserted rows removed, updated rows
  restored. Reversal is refused when a later import changed the same rows or
  when other records now depend on rows the import created.
- Capability, credential, agreement and service-requirement imports
  re-evaluate every live opportunity's qualification.

Reference rules: a row naming an airport, airline, station, operating
company, service or owner that is not registered is QUARANTINED
(`unresolved_reference`). The internal registers (agreements, capabilities,
operating companies) may create operating companies; agreements may create
the airline named by IATA code and name.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from ..domain import imports as im
from ..repo.db import Database, to_json
from . import ops_service
from .audit import RequestMeta, audit

COMMIT_SUPPORTED = set(im.CONTRACTS)
REVERSIBLE = im.REVERSIBLE
RECOMPUTE_AFTER = {"capabilities", "training_credentials", "agreements", "service_requirements"}
CORRECT_BY_REIMPORT = sorted(COMMIT_SUPPORTED - REVERSIBLE)


class ImportRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _source_for(db: Database, dataset: str) -> str:
    name = f"Import: {dataset}"
    sid = db.scalar("source_for_dataset", name=name)
    if sid is None:
        contract = im.CONTRACTS[dataset]
        sid = db.scalar("source_insert", connector_id=None, name=name, family=f"import:{dataset}", base_url=None,
                        authority="internal_record", note=contract.source_of_truth, retention=True, enabled=True,
                        sla=contract.freshness_sla_hours)
        db.run("source_mark_import", id=str(sid))
    return str(sid)


# ===================================================================== existing state (for upsert planning)


def _rows(db: Database, query: str, key: Callable[[dict[str, Any]], str], **params: Any) -> dict[str, dict[str, Any]]:
    return {key(r): r for r in db.all(query, **params)}


def _existing(db: Database, dataset: str, source_id: str) -> dict[str, dict[str, Any]]:
    ext = lambda r: r["external_id"]  # noqa: E731
    if dataset == "bookings":
        return _rows(db, "existing_bookings", ext, source=source_id)
    if dataset == "quotes":
        return _rows(db, "existing_quotes", ext, source=source_id)
    if dataset == "capacity":
        return _rows(db, "existing_capacity", ext, source=source_id)
    if dataset == "exceptions":
        out = {}
        for r in db.all("existing_exception_reports", source=source_id):
            out[r["external_id"]] = r["report"] if isinstance(r["report"], dict) else json.loads(r["report"])
        return out
    if dataset == "agreements":
        return _rows(db, "existing_agreements", ext)
    if dataset == "capabilities":
        return _rows(db, "existing_capabilities", lambda r: f"{r['operating_company']}|{r['service_code']}|{r['station'] or '*'}")
    if dataset == "trucking":
        return _rows(db, "existing_trucking", ext, source=source_id)
    if dataset == "finance":
        return _rows(db, "existing_finance", lambda r: f"{r['operating_company']}|{r['period_start']}|{r['period_end']}|{r['metric']}|{r['currency']}",
                     source=source_id)
    if dataset == "channel_events":
        return _rows(db, "existing_channel_events", ext, source=source_id)
    if dataset == "training_credentials":
        return _rows(db, "existing_credentials", ext, source=source_id)
    if dataset == "gateway_connections":
        return _rows(db, "existing_gateway_connections", ext, source=source_id)
    if dataset == "contacts":
        return _rows(db, "existing_contacts", ext)
    if dataset in ("airports", "airlines", "territories", "services", "stations"):
        return _rows(db, f"existing_{dataset}", lambda r: im.row_key(dataset, r))
    if dataset == "operating_companies":
        return _rows(db, "existing_operating_companies", lambda r: str(r["name"]).lower())
    if dataset == "service_requirements":
        return _rows(db, "existing_service_requirements", lambda r: f"{r['service_code']}|{r['credential_type']}")
    return {}


def _reference_check(db: Database, dataset: str) -> Callable[[dict[str, Any]], list[tuple[str, str]]]:
    cache: dict[tuple[str, str], bool] = {}

    def has(kind: str, query: str, value: str, **extra: Any) -> bool:
        k = (kind, value)
        if k not in cache:
            cache[k] = db.scalar(query, **extra) is not None
        return cache[k]

    airport = lambda c: has("airport", "airport_id", c, code=c)  # noqa: E731
    airline = lambda c: has("airline", "airline_by_iata", c, code=c.upper())  # noqa: E731
    company = lambda n: has("company", "company_by_name", n, name=n)  # noqa: E731
    service = lambda c: has("service", "service_by_code", c, code=c)  # noqa: E731
    person = lambda n: has("person", "person_by_name", n, name=n)  # noqa: E731
    station = lambda c: has("station", "station_id", c, code=c.upper())  # noqa: E731

    def check(v: dict[str, Any]) -> list[tuple[str, str]]:
        errs: list[tuple[str, str]] = []
        airport_fields = ("origin", "destination", "gateway") + (("station",) if dataset not in ("stations",) else ())
        for f in airport_fields:
            if dataset in ("airports", "territories"):
                break
            if v.get(f) and not airport(v[f]):
                errs.append((f, f"airport {v[f]} is not registered (load it under Setup: airports)"))
        if dataset in ("bookings", "capacity", "gateway_connections") and v.get("airline_iata") and not airline(v["airline_iata"]):
            errs.append(("airline_iata", f"airline {v['airline_iata']} is not registered (Setup: airlines)"))
        if dataset in ("bookings", "exceptions", "finance", "training_credentials", "contacts") and v.get("operating_company") \
                and not company(v["operating_company"]):
            errs.append(("operating_company", f"operating company {v['operating_company']!r} is not registered (Setup: operating companies)"))
        if dataset == "quotes" and v.get("owner") and not person(v["owner"]):
            errs.append(("owner", f"owner {v['owner']!r} is not a recorded person"))
        if dataset in ("capabilities", "training_credentials", "service_requirements") and v.get("service_code") \
                and not service(v["service_code"]):
            errs.append(("service_code", f"service {v['service_code']} is not in the catalogue"))
        if dataset == "agreements":
            for code in _split(v.get("services")):
                if not service(code):
                    errs.append(("services", f"service {code} is not in the catalogue"))
        if dataset == "trucking" and v.get("origin_station") and not station(v["origin_station"]):
            errs.append(("origin_station", f"station {v['origin_station']} is not registered (Setup: stations)"))
        return errs

    return check


def _split(v: Any) -> list[str]:
    return [p.strip().upper() for p in str(v or "").split(";") if p.strip()]


# ===================================================================== planning and fingerprint


def _plan(db: Database, dataset: str, filename: str, data: bytes, mapping: dict[str, str] | None, naive_tz: str | None):
    if dataset not in im.CONTRACTS:
        raise ImportRejected(404, f"unknown dataset {dataset}")
    source_id = _source_for(db, dataset)
    try:
        preview, effects, errors, rec = im.run_import(dataset, filename, data, _existing(db, dataset, source_id), mapping,
                                                      naive_tz=naive_tz or None, reference_check=_reference_check(db, dataset))
    except im.FileRejected as exc:
        raise ImportRejected(422, str(exc)) from exc
    except Exception as exc:  # unknown time zone name, unreadable workbook
        if exc.__class__.__name__ in ("ZoneInfoNotFoundError", "BadZipFile", "InvalidFileException", "KeyError", "ValueError"):
            raise ImportRejected(422, f"file or time zone rejected: {exc}") from exc
        raise
    return source_id, preview, effects, errors, rec


def _fingerprint(effects: list[im.PlannedEffect], errors: list[im.RowError]) -> str:
    material = {
        "effects": [[e.row_number, e.key, e.action, {k: im._comparable(v) for k, v in sorted(e.values.items())}] for e in effects],
        "errors": [[e.row_number, e.field, e.code] for e in errors],
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()


def dry_run(db: Database, dataset: str, filename: str, data: bytes, mapping: dict[str, str] | None, meta: RequestMeta,
            naive_tz: str | None = None) -> dict:
    source_id, preview, effects, errors, rec = _plan(db, dataset, filename, data, mapping, naive_tz)
    ok = not preview.unmapped_required
    with db.transaction() as tx:
        job_id = str(tx.scalar("import_job_insert", dataset=dataset, source_id=source_id, file_name=filename[:200], sha=rec.file_sha256,
                               schema_version=rec.schema_version, mapping=preview.mapping, mode="dry_run",
                               status="validated" if ok else "failed", totals=asdict(rec), session_ref=meta.session_ref))
        for e in errors:
            tx.run("import_error_add", job=job_id, row=e.row_number, field=e.field, code=e.code, message=e.message, raw=e.raw)
        tx.run("import_file_store", job=job_id, content=data, tz=naive_tz or None, fingerprint=_fingerprint(effects, errors))
        audit(tx, "import_dry_run", meta, entity_type="import_job", entity_id=job_id, detail={"dataset": dataset, "rows": rec.rows_read})
    preview_rows = [{"row": e.row_number, "key": e.key, "action": e.action,
                     "values": json.loads(to_json(e.values)), "previous": json.loads(to_json(e.previous)) if e.previous else None}
                    for e in effects if e.action != "unchanged"][:200]
    return {"job_id": job_id, "dataset": dataset, "mapping": asdict(preview), "reconciliation": asdict(rec),
            "errors": [asdict(e) for e in errors[:200]], "commit_supported": ok and dataset in COMMIT_SUPPORTED,
            "planned": {"insert": rec.inserted, "update": rec.updated, "unchanged": rec.unchanged},
            "preview": preview_rows, "reversible": dataset in REVERSIBLE}


def commit(db: Database, preview_job_id: str, meta: RequestMeta) -> dict:
    job = db.one("import_job_get", id=preview_job_id)
    if job is None or job["mode"] != "dry_run":
        raise ImportRejected(404, "preview not found; run a preview (dry run) first")
    if job["status"] != "validated":
        raise ImportRejected(409, "this preview cannot be committed (required fields not mapped)")
    if db.scalar("import_commit_for_preview", id=preview_job_id) is not None:
        raise ImportRejected(409, "this preview has already been committed; run a new preview to import again")
    stored = db.one("import_file_get", id=preview_job_id)
    if stored is None:
        raise ImportRejected(409, "the previewed file is no longer stored; run a new preview")
    dataset = job["dataset"]
    data = bytes(stored["content"])
    mapping = job["mapping"] if isinstance(job["mapping"], dict) else json.loads(job["mapping"])
    source_id, preview, effects, errors, rec = _plan(db, dataset, job["file_name"], data, mapping, stored["naive_timezone"])
    if _fingerprint(effects, errors) != stored["plan_fingerprint"]:
        raise ImportRejected(409, "the data changed since this preview (the planned inserts, updates or errors differ); "
                                  "run the preview again and review it before committing")
    writer = WRITERS[dataset]
    partial = rec.rows_quarantined > 0
    with db.transaction() as tx:
        job_id = str(tx.scalar("import_job_insert2", dataset=dataset, source_id=source_id, file_name=job["file_name"],
                               sha=rec.file_sha256, schema_version=rec.schema_version, mapping=preview.mapping, mode="commit",
                               status="pending", totals=asdict(rec), session_ref=meta.session_ref, preview=preview_job_id,
                               partial=partial))
        for e in errors:
            tx.run("import_error_add", job=job_id, row=e.row_number, field=e.field, code=e.code, message=e.message, raw=e.raw)
        for eff in effects:
            if eff.action == "unchanged":
                continue
            prov = str(tx.scalar("provenance_insert", kind="import_row", job=job_id, row=eff.row_number, doc=None, note=None))
            target = writer(tx, source_id, eff.values, prov)
            tx.run("import_effect_add", job=job_id, row=eff.row_number, table=im.CONTRACTS[dataset].target_table, target=target,
                   action=eff.action, previous=_jsonable(eff.previous))
        tx.run("import_job_committed", id=job_id, totals=asdict(rec))
        run_id = tx.scalar("ingestion_run_start", source=source_id, job=None)
        tx.run("ingestion_run_finish", id=str(run_id), status="succeeded",
               stats={"import_job_id": job_id, "inserted": rec.inserted, "updated": rec.updated, "quarantined": rec.rows_quarantined})
        recomputed = 0
        if dataset in RECOMPUTE_AFTER and (rec.inserted or rec.updated):
            from .ingestion import recompute_open_opportunities

            recomputed = recompute_open_opportunities(tx)
        audit(tx, "import_committed", meta, entity_type="import_job", entity_id=job_id,
              detail={"dataset": dataset, "inserted": rec.inserted, "updated": rec.updated, "quarantined": rec.rows_quarantined,
                      "preview_job_id": preview_job_id})
    return {"job_id": job_id, "dataset": dataset, "reconciliation": asdict(rec), "errors": [asdict(e) for e in errors[:200]],
            "partial": partial, "partial_note": (f"Partial import: {rec.rows_quarantined} row(s) quarantined and NOT imported. "
                                                 "Fix them in the source file and import again.") if partial else None,
            "opportunities_recomputed": recomputed, "reversible": dataset in REVERSIBLE}


def import_file(db: Database, dataset: str, filename: str, data: bytes, mapping: dict[str, str] | None, meta: RequestMeta,
                naive_tz: str | None = None) -> dict:
    """Preview then commit the same file in one step (setup scripts and tests).
    The browser workflow always shows the preview before commit."""
    pre = dry_run(db, dataset, filename, data, mapping, meta, naive_tz=naive_tz)
    if not pre["commit_supported"]:
        raise ImportRejected(422, f"required fields not mapped: {', '.join(pre['mapping']['unmapped_required'])}")
    return commit(db, pre["job_id"], meta)


def _jsonable(prev: dict | None) -> dict | None:
    if prev is None:
        return None
    return json.loads(to_json(prev))


# ===================================================================== writers


def _org(tx: Database, name: str | None, kind: str, prov: str | None) -> str | None:
    if not name:
        return None
    oid = tx.scalar("org_by_name", name=name, norm=_norm(name))
    if oid is None:
        oid = tx.scalar("org_insert", name=name, kind=kind, prov=prov)
        tx.run("alias_insert", org=str(oid), alias=name, norm=_norm(name), prov=prov)
    if kind == "forwarder":
        tx.run("forwarder_ensure", org=str(oid))
    return str(oid)


def _lane(tx: Database, origin: str, destination: str) -> str:
    o = tx.scalar("airport_id", code=origin)
    d = tx.scalar("airport_id", code=destination)
    if o is None or d is None:  # quarantined earlier by the reference check; defensive
        raise ImportRejected(422, f"unregistered airport in lane {origin}->{destination}")
    return str(tx.scalar("lane_ensure", o=str(o), d=str(d)))


def _id(tx: Database, query: str, **params: Any) -> str | None:
    v = tx.scalar(query, **params)
    return str(v) if v is not None else None


def _days(v: Any) -> list[int] | None:
    return [int(x) for x in str(v).split(";")] if v else None


def _write_booking(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar(
        "booking_upsert", source=source_id, external_id=v["external_id"], forwarder=_org(tx, v.get("forwarder"), "forwarder", prov),
        airline=_id(tx, "airline_by_iata", code=str(v["airline_iata"]).upper()) if v.get("airline_iata") else None,
        lane=_lane(tx, v["origin"], v["destination"]),
        company=_id(tx, "company_by_name", name=v["operating_company"]) if v.get("operating_company") else None,
        flight_date=v.get("flight_date"), booked_at=v["booked_at"], status=v["status"], actual=v.get("actual_weight"),
        chargeable=v.get("chargeable_weight"), volume=v.get("volume"), revenue=v.get("revenue"), currency=v.get("currency"), prov=prov))


def _write_quote(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar(
        "quote_upsert", source=source_id, external_id=v["external_id"], forwarder=_org(tx, v.get("forwarder"), "forwarder", prov),
        lane=_lane(tx, v["origin"], v["destination"]), quoted_at=v["quoted_at"], status=v["status"], lost_reason=v.get("lost_reason"),
        chargeable=v.get("chargeable_weight"), amount=v.get("amount"), currency=v.get("currency"),
        owner=_id(tx, "person_by_name", name=v["owner"]) if v.get("owner") else None, prov=prov))


def _write_capacity(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar(
        "capacity_upsert", source=source_id, external_id=v["external_id"],
        airline=_id(tx, "airline_by_iata", code=str(v["airline_iata"]).upper()) if v.get("airline_iata") else None,
        lane=_lane(tx, v["origin"], v["destination"]), flight_number=v.get("flight_number"), period_start=v["period_start"],
        period_end=v["period_end"], basis=v["basis"], capacity_type=v["capacity_type"], amount=v["amount"], snapshot_at=v["snapshot_at"],
        prov=prov))


def _write_agreement(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    iata = str(v["airline_iata"]).upper()
    airline = _id(tx, "airline_by_iata", code=iata)
    if airline is None:
        airline = _org(tx, v["airline_name"], "airline", prov)
        tx.run("airline_insert", org=airline, iata=iata)
    company = str(tx.scalar("company_ensure", name=v["operating_company"], prov=prov))
    aid = str(tx.scalar("agreement_upsert", external_id=v["external_id"], airline=airline, company=company,
                        effective_from=v.get("effective_from"), effective_to=v.get("effective_to"), renewal_date=v.get("renewal_date"),
                        notice_date=v.get("notice_date"), exclusivity=v.get("exclusivity"), appointment_rights=v.get("appointment_rights"),
                        remuneration_model=v.get("remuneration_model"), prov=prov))
    tx.run("agreement_clear_scope", id=aid)
    for code in _split(v.get("territories")):
        kind = "country" if len(code) == 2 else "station" if len(code) == 3 else "region"
        tid = str(tx.scalar("territory_ensure", code=code, kind=kind))
        if kind == "country":
            tx.run("territory_set_country", id=tid, country=code)
        tx.run("agreement_add_territory", id=aid, territory=tid)
    for code in _split(v.get("services")):
        tx.run("agreement_add_service", id=aid, service=str(tx.scalar("service_by_code", code=code)))
    return aid


def _write_capability(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    company = str(tx.scalar("company_ensure", name=v["operating_company"], prov=prov))
    langs = _split(v.get("languages"))
    return str(tx.scalar(
        "capability_upsert", company=company, service=str(tx.scalar("service_by_code", code=v["service_code"])),
        station=_id(tx, "airport_id", code=v["station"]) if v.get("station") else None, status=v["status"],
        owner=v.get("verification_owner"), valid_from=v.get("valid_from"), valid_to=v.get("valid_to"),
        languages="{" + ",".join(langs) + "}" if langs else None, restrictions=v.get("commodity_restrictions"), prov=prov))


def _write_exception(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    company = _id(tx, "company_by_name", name=v["operating_company"]) if v.get("operating_company") else None
    customer = _org(tx, v.get("customer"), "forwarder", prov)
    known = tx.scalar("exception_for_report", source=source_id, external_id=v["external_id"])
    if v["status"] == "resolved" and known is not None:
        ops_service.resolve(tx, str(known), "resolved in source system", RequestMeta(ip="import"))
        exc_id = str(known)
    else:
        res = ops_service.open_exception(
            tx, exception_type=v["exception_type"], severity=v["severity"], description=v["description"],
            booking_ref=v.get("booking_ref"), customer_id=customer, customer_label=v.get("customer"),
            company_id=company, company_label=v.get("operating_company"),
            deadline_utc=v.get("deadline"), owner_person_id=None, source_id=source_id, external_id=v["external_id"])
        exc_id = res["id"]
        if v["status"] == "resolved":
            ops_service.resolve(tx, exc_id, "resolved in source system", RequestMeta(ip="import"))
    tx.run("exception_report_upsert", source=source_id, external_id=v["external_id"], exception=exc_id, report=json.loads(to_json(v)))
    return exc_id


def _write_trucking(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar(
        "trucking_upsert", source=source_id, external_id=v["external_id"], provider=_org(tx, v["provider"], "trucking_provider", prov),
        station=_id(tx, "station_id", code=str(v["origin_station"]).upper()), gateway=_id(tx, "airport_id", code=v["gateway"]),
        days=_days(v["departure_days"]), time=v["departure_time"], transit=v.get("transit_minutes"),
        restrictions=v.get("restrictions"), prov=prov))


def _write_finance(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar(
        "finance_upsert", source=source_id, company=_id(tx, "company_by_name", name=v["operating_company"]),
        period_start=v["period_start"], period_end=v["period_end"], metric=v["metric"], amount=v["amount"], currency=v["currency"],
        basis=v["basis"], prov=prov))


def _write_channel_event(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar(
        "channel_event_upsert", source=source_id, external_id=v["external_id"], event_type=v["event_type"],
        session_key=v.get("session_key"), booking_ref=v.get("booking_ref"), channel=v["channel"], occurred_at=v["occurred_at"],
        forwarder=_org(tx, v.get("forwarder"), "forwarder", prov), prov=prov))


def _write_credential(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar(
        "credential_upsert", source=source_id, external_id=v["external_id"], company=_id(tx, "company_by_name", name=v["operating_company"]),
        service=_id(tx, "service_by_code", code=v["service_code"]) if v.get("service_code") else None,
        credential_type=v["credential_type"], holder=v.get("holder_description"),
        station=_id(tx, "airport_id", code=v["station"]) if v.get("station") else None, issued_on=v.get("issued_on"),
        expires_on=v.get("expires_on"), prov=prov))


def _write_airport(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar("airport_upsert", iata=v["iata_code"], icao=v.get("icao_code"), name=v["name"], country=v["country"],
                         tz=v["timezone"]))


def _write_airline(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    by_code = _id(tx, "airline_by_iata", code=v["iata_code"])
    oid = by_code or _id(tx, "org_by_name", name=v["name"], norm=_norm(v["name"]))
    if oid is None:
        oid = str(tx.scalar("org_insert", name=v["name"], kind="airline", prov=prov))
    elif by_code:
        # The airline register is the source of truth for the airline's name: a corrected name replaces the canonical
        # name (the previous name stays an alias, so earlier evidence still resolves to the same airline).
        tx.run("org_set_name", id=oid, name=v["name"])
    tx.run("alias_insert", org=oid, alias=v["name"], norm=_norm(v["name"]), prov=prov)
    tx.run("org_set_country", id=oid, country=v.get("country"))
    tx.run("airline_upsert", org=oid, iata=v["iata_code"], icao=v.get("icao_code"), awb=v.get("awb_prefix"))
    return oid


def _write_company(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar("company_upsert", name=v["name"], legal=v.get("legal_entity_name"), country=v.get("country"),
                         member=v.get("is_group_member", True), prov=prov))


def _write_territory(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar("territory_upsert", code=v["code"], name=v["name"], kind=v["kind"],
                         country=v.get("country") or (v["code"] if v["kind"] == "country" else None)))


def _write_service(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar("service_upsert", code=v["code"], name=v["name"], category=v["category"]))


def _write_service_requirement(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    sid = str(tx.scalar("service_by_code", code=v["service_code"]))
    tx.run("service_requirement_add", service=sid, credential=v["credential_type"])
    return sid


def _write_contact(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar("contact_upsert", external_id=v["external_id"], full_name=v["full_name"], role_title=v.get("role_title"),
                         org=_org(tx, v.get("organisation"), "other", prov) if v.get("organisation") else None,
                         company=_id(tx, "company_by_name", name=v["operating_company"]) if v.get("operating_company") else None,
                         email=v.get("email"), internal=bool(v.get("is_internal")), prov=prov))


def _write_station(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar("station_upsert", code=v["code"], name=v["name"], offline=v["is_offline"], country=v.get("country"),
                         tz=v.get("timezone")))


def _write_gateway(tx: Database, source_id: str, v: dict[str, Any], prov: str | None) -> str:
    return str(tx.scalar(
        "gateway_upsert", source=source_id, external_id=v["external_id"], gateway=_id(tx, "airport_id", code=v["gateway"]),
        airline=_id(tx, "airline_by_iata", code=v["airline_iata"]) if v.get("airline_iata") else None,
        lane=_lane(tx, v["gateway"], v["destination"]), flight=v.get("flight_number"), days=_days(v["departure_days"]),
        time=v["departure_time"], cutoff=v.get("connection_cutoff_minutes"), prov=prov))


WRITERS: dict[str, Callable[[Database, str, dict[str, Any], str | None], str]] = {
    "bookings": _write_booking, "quotes": _write_quote, "capacity": _write_capacity, "exceptions": _write_exception,
    "agreements": _write_agreement, "capabilities": _write_capability, "trucking": _write_trucking, "finance": _write_finance,
    "channel_events": _write_channel_event, "training_credentials": _write_credential, "airports": _write_airport,
    "airlines": _write_airline, "operating_companies": _write_company, "territories": _write_territory, "services": _write_service,
    "service_requirements": _write_service_requirement, "contacts": _write_contact, "stations": _write_station,
    "gateway_connections": _write_gateway,
}
DELETE_QUERY = {
    "bookings": "booking_delete", "quotes": "quote_delete", "capacity": "capacity_delete", "trucking": "trucking_delete",
    "finance": "finance_delete", "channel_events": "channel_event_delete", "training_credentials": "credential_delete",
    "gateway_connections": "gateway_delete", "airports": "airport_delete", "stations": "station_delete", "contacts": "contact_delete",
    "service_requirements": None,
}


def reverse(db: Database, job_id: str, reason: str, meta: RequestMeta) -> dict:
    job = db.one("import_job_get", id=job_id)
    if job is None:
        raise ImportRejected(404, "import job not found")
    if job["status"] != "committed" or job["dataset"] not in REVERSIBLE:
        raise ImportRejected(409, f"only committed imports of {', '.join(sorted(REVERSIBLE))} can be reversed; "
                                  f"{', '.join(CORRECT_BY_REIMPORT)} are corrected by importing a corrected file")
    if int(db.scalar("import_later_conflicts", job=job_id) or 0) > 0:
        raise ImportRejected(409, "a later committed import changed the same records; reverse the later import first")
    dataset = job["dataset"]
    effects = db.all("import_effects", job=job_id)
    try:
        with db.transaction() as tx:
            for e in effects:
                if e["action"] == "insert":
                    if dataset == "service_requirements":
                        prev_vals = _effect_values(tx, job_id, e["row_number"])
                        tx.run("service_requirement_delete", service=str(e["target_id"]), credential=prev_vals.get("credential_type"))
                    else:
                        tx.run(DELETE_QUERY[dataset], id=str(e["target_id"]))  # type: ignore[arg-type]
                elif e["action"] == "update" and e["previous"]:
                    WRITERS[dataset](tx, str(job["source_id"]), e["previous"], None)
            tx.run("import_job_reversed", id=job_id, reason=reason)
            if dataset in RECOMPUTE_AFTER:
                from .ingestion import recompute_open_opportunities

                recompute_open_opportunities(tx)
            audit(tx, "import_reversed", meta, entity_type="import_job", entity_id=job_id, detail={"dataset": dataset})
    except Exception as exc:  # noqa: BLE001
        if exc.__class__.__name__ == "IntegrityError" or "foreign key" in str(exc).lower():
            raise ImportRejected(409, "records created by this import are now used by other records (for example bookings that "
                                      "reference an imported airport); reverse or correct those first") from exc
        raise
    return {"job_id": job_id, "reversed_rows": len(effects)}


def _effect_values(tx: Database, job_id: str, row_number: int) -> dict[str, Any]:
    """Values written for one row (from the stored file via the committed plan)."""
    job = tx.one("import_job_get", id=job_id)
    stored = tx.one("import_file_get", id=str(job["preview_job_id"])) if job and job.get("preview_job_id") else None
    if stored is None or job is None:
        return {}
    mapping = job["mapping"] if isinstance(job["mapping"], dict) else json.loads(job["mapping"])
    kind = im.validate_upload(job["file_name"], bytes(stored["content"]))
    headers, rows = im.read_rows(kind, bytes(stored["content"]))
    valid, _ = im.validate_rows(im.CONTRACTS[job["dataset"]], mapping, rows, naive_tz=stored["naive_timezone"])
    for r in valid:
        if r.row_number == row_number:
            return r.values
    return {}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
