"""Controlled CSV/XLSX imports (build spec §8).

Flow: upload -> validate file (size/type) -> mapping preview -> dry run ->
row validation + duplicate review -> commit -> reconciliation summary +
error report.

- Rows are keyed on (source, external_id). Reruns produce `unchanged`, so a
  batch can be re-imported without duplicating bookings.
- Amendments and cancellations are updates of the same external id, with
  the previous values kept for reversal.
- Bad rows are quarantined with their raw values; they are never dropped.
- Duplicate external ids inside one file are quarantined (all but the first).
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Callable, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

MAX_FILE_BYTES = 20 * 1024 * 1024
SCHEMA_VERSION = "wfc-import-1"

FieldType = Literal["str", "decimal", "date", "datetime", "currency", "iata_airport", "enum", "int", "country", "timezone", "bool",
                    "airline_code", "weekdays", "hhmm"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: FieldType
    required: bool = False
    unit: str | None = None
    choices: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class DatasetContract:
    dataset: str
    target_table: str
    fields: tuple[FieldSpec, ...]
    source_of_truth: str
    freshness_sla_hours: int | None
    retention: str
    reconcile_sums: tuple[str, ...] = ()

    @property
    def required(self) -> list[str]:
        return [f.name for f in self.fields if f.required]


def _fs(*a, **k) -> FieldSpec:
    return FieldSpec(*a, **k)


CONTRACTS: dict[str, DatasetContract] = {
    "bookings": DatasetContract(
        "bookings", "bookings",
        (
            _fs("external_id", "str", True, description="Stable booking id in the source system"),
            _fs("forwarder", "str", False, description="Forwarder name as in source"),
            _fs("airline_iata", "str", False),
            _fs("origin", "iata_airport", True), _fs("destination", "iata_airport", True),
            _fs("flight_date", "date", False), _fs("booked_at", "datetime", True),
            _fs("status", "enum", True, choices=("confirmed", "amended", "cancelled")),
            _fs("actual_weight", "decimal", False, unit="kg"), _fs("chargeable_weight", "decimal", False, unit="kg"),
            _fs("volume", "decimal", False, unit="m3"),
            _fs("revenue", "decimal", False), _fs("currency", "currency", False),
            _fs("operating_company", "str", False),
        ),
        source_of_truth="WFC booking system export (Not connected)", freshness_sla_hours=24,
        retention="7 years (financial records)", reconcile_sums=("chargeable_weight", "revenue"),
    ),
    "quotes": DatasetContract(
        "quotes", "quotes",
        (
            _fs("external_id", "str", True), _fs("forwarder", "str", True),
            _fs("origin", "iata_airport", True), _fs("destination", "iata_airport", True),
            _fs("quoted_at", "datetime", True),
            _fs("status", "enum", True, choices=("open", "won", "lost", "expired", "cancelled")),
            _fs("lost_reason", "str", False), _fs("chargeable_weight", "decimal", False, unit="kg"),
            _fs("amount", "decimal", False), _fs("currency", "currency", False), _fs("owner", "str", False),
        ),
        source_of_truth="WFC quoting tool export (Not connected)", freshness_sla_hours=24,
        retention="3 years", reconcile_sums=("amount",),
    ),
    "agreements": DatasetContract(
        "agreements", "representation_agreements",
        (
            _fs("external_id", "str", True), _fs("airline_iata", "str", True), _fs("airline_name", "str", True),
            _fs("operating_company", "str", True), _fs("territories", "str", True, description="Semicolon-separated territory codes"),
            _fs("services", "str", True, description="Semicolon-separated service codes"),
            _fs("effective_from", "date", False), _fs("effective_to", "date", False),
            _fs("renewal_date", "date", False), _fs("notice_date", "date", False),
            _fs("exclusivity", "enum", False, choices=("exclusive", "non_exclusive", "unknown")),
            _fs("appointment_rights", "enum", False, choices=("may_extend", "requires_consent", "prohibited", "unknown")),
            _fs("remuneration_model", "enum", False, choices=("commission", "fixed_fee", "tcm_margin", "hybrid", "unknown")),
        ),
        source_of_truth="WFC contract register", freshness_sla_hours=None, retention="Contract life + 7 years",
    ),
    "capabilities": DatasetContract(
        "capabilities", "capability_records",
        (
            _fs("operating_company", "str", True), _fs("service_code", "str", True), _fs("station", "iata_airport", False),
            _fs("status", "enum", True, choices=("verified", "unverified", "withdrawn")),
            _fs("verification_owner", "str", False), _fs("valid_from", "date", False), _fs("valid_to", "date", False),
            _fs("languages", "str", False), _fs("commodity_restrictions", "str", False),
        ),
        source_of_truth="WFC group capability register", freshness_sla_hours=None, retention="Current + 3 years",
    ),
    "capacity": DatasetContract(
        "capacity", "capacity_snapshots",
        (
            _fs("external_id", "str", True), _fs("airline_iata", "str", False),
            _fs("origin", "iata_airport", True), _fs("destination", "iata_airport", True),
            _fs("flight_number", "str", False), _fs("period_start", "date", True), _fs("period_end", "date", True),
            _fs("basis", "enum", True, choices=("weight_kg", "volume_m3")),
            _fs("capacity_type", "enum", True, choices=("offered", "bookable", "allotted")),
            _fs("amount", "decimal", True), _fs("snapshot_at", "datetime", True),
        ),
        source_of_truth="Airline schedule/capacity file (Not connected)", freshness_sla_hours=168,
        retention="3 years", reconcile_sums=("amount",),
    ),
    "exceptions": DatasetContract(
        "exceptions", "operational_exceptions",
        (
            _fs("external_id", "str", True), _fs("exception_type", "enum", True, choices=("reservation", "supervision", "post_flight")),
            _fs("severity", "enum", True, choices=("low", "medium", "high", "critical")),
            _fs("booking_ref", "str", False), _fs("customer", "str", False), _fs("operating_company", "str", False),
            _fs("description", "str", True), _fs("deadline", "datetime", False),
            _fs("status", "enum", True, choices=("open", "acknowledged", "resolved")),
        ),
        source_of_truth="Reservation/supervision exception log (Not connected)", freshness_sla_hours=1, retention="2 years",
    ),
    "trucking": DatasetContract(
        "trucking", "road_feeder_services",
        (
            _fs("external_id", "str", True), _fs("provider", "str", True), _fs("origin_station", "str", True),
            _fs("gateway", "iata_airport", True), _fs("departure_days", "weekdays", True, description="ISO weekdays, e.g. 1;3;5"),
            _fs("departure_time", "hhmm", True, description="HH:MM local"), _fs("transit_minutes", "int", False),
            _fs("restrictions", "str", False),
        ),
        source_of_truth="Trucking provider schedules", freshness_sla_hours=720, retention="Current + 1 year",
    ),
    "finance": DatasetContract(
        "finance", "financial_aggregates",
        (
            _fs("operating_company", "str", True), _fs("period_start", "date", True), _fs("period_end", "date", True),
            _fs("metric", "str", True), _fs("amount", "decimal", True), _fs("currency", "currency", True), _fs("basis", "str", True),
        ),
        source_of_truth="WFC finance month-end pack", freshness_sla_hours=744, retention="7 years", reconcile_sums=("amount",),
    ),
    "channel_events": DatasetContract(
        "channel_events", "channel_events",
        (
            _fs("external_id", "str", True),
            _fs("event_type", "enum", True, choices=("search", "quote_request", "quote", "booking", "integration_failure")),
            _fs("session_key", "str", False), _fs("booking_ref", "str", False), _fs("channel", "str", True),
            _fs("occurred_at", "datetime", True), _fs("forwarder", "str", False, description="Forwarder account, if known"),
        ),
        source_of_truth="Digital channel analytics export (Not connected)", freshness_sla_hours=24, retention="13 months",
    ),
    "training_credentials": DatasetContract(
        "training_credentials", "training_credentials",
        (
            _fs("external_id", "str", True, description="Stable credential id in the HR/training register"),
            _fs("operating_company", "str", True), _fs("credential_type", "str", True,
                                                       description="e.g. IATA_DGR, IATA_CARGO_AGENT, TSA_SECURITY"),
            _fs("service_code", "str", False, description="Service the credential supports (blank = company-wide)"),
            _fs("station", "iata_airport", False, description="Station where held (blank = company-wide)"),
            _fs("holder_description", "str", False, description="Role or team, not a personal record"),
            _fs("issued_on", "date", False), _fs("expires_on", "date", False),
        ),
        source_of_truth="WFC training and certification register", freshness_sla_hours=None, retention="Current + 3 years",
    ),
    # ------------------------------------------------------------------ master data (setup)
    "airports": DatasetContract(
        "airports", "airports",
        (
            _fs("iata_code", "iata_airport", True), _fs("icao_code", "str", False), _fs("name", "str", True),
            _fs("country", "country", True, description="ISO 3166-1 alpha-2"), _fs("timezone", "timezone", True, description="IANA zone"),
        ),
        source_of_truth="Airport reference list maintained by WFC", freshness_sla_hours=None, retention="Current",
    ),
    "airlines": DatasetContract(
        "airlines", "airlines",
        (
            _fs("iata_code", "airline_code", True, description="Two-character IATA designator"), _fs("name", "str", True),
            _fs("icao_code", "str", False), _fs("awb_prefix", "str", False, description="Three-digit AWB prefix"),
            _fs("country", "country", False),
        ),
        source_of_truth="Airline reference list maintained by WFC", freshness_sla_hours=None, retention="Current",
    ),
    "operating_companies": DatasetContract(
        "operating_companies", "operating_companies",
        (
            _fs("name", "str", True, description="Name used across WFC records, e.g. WFC-UAE"),
            _fs("legal_entity_name", "str", False), _fs("country", "country", False),
            _fs("is_group_member", "bool", False, description="yes/no; blank = yes"),
        ),
        source_of_truth="WFC group structure", freshness_sla_hours=None, retention="Current",
    ),
    "territories": DatasetContract(
        "territories", "territories",
        (
            _fs("code", "str", True, description="ISO country code, region code or station IATA"), _fs("name", "str", True),
            _fs("kind", "enum", True, choices=("country", "region", "station")), _fs("country", "country", False),
        ),
        source_of_truth="WFC territory definitions", freshness_sla_hours=None, retention="Current",
    ),
    "services": DatasetContract(
        "services", "services",
        (
            _fs("code", "str", True, description="Upper-case code, e.g. HANDLING_PHARMA"), _fs("name", "str", True),
            _fs("category", "enum", True, choices=("gssa", "tcm", "handling", "trucking", "data_processing", "accounting", "invoicing",
                                                    "collections", "training", "technology")),
        ),
        source_of_truth="WFC service catalogue", freshness_sla_hours=None, retention="Current",
    ),
    "service_requirements": DatasetContract(
        "service_requirements", "service_credential_requirements",
        (_fs("service_code", "str", True), _fs("credential_type", "str", True)),
        source_of_truth="WFC service catalogue: credentials each service always requires", freshness_sla_hours=None, retention="Current",
    ),
    "contacts": DatasetContract(
        "contacts", "people",
        (
            _fs("external_id", "str", True), _fs("full_name", "str", True), _fs("role_title", "str", False),
            _fs("organisation", "str", False, description="Airline/forwarder/partner name (created if new)"),
            _fs("operating_company", "str", False), _fs("email", "str", False),
            _fs("is_internal", "bool", False, description="yes for WFC owners; these are descriptive records, not logins"),
        ),
        source_of_truth="WFC relationship records", freshness_sla_hours=None, retention="While relevant",
    ),
    "stations": DatasetContract(
        "stations", "stations",
        (
            _fs("code", "str", True, description="Station code (IATA for airports, own code for offline points)"),
            _fs("name", "str", True), _fs("is_offline", "bool", True, description="yes = no own flights, served by road feeder"),
            _fs("country", "country", False), _fs("timezone", "timezone", False),
        ),
        source_of_truth="WFC station network", freshness_sla_hours=None, retention="Current",
    ),
    "gateway_connections": DatasetContract(
        "gateway_connections", "gateway_connections",
        (
            _fs("external_id", "str", True), _fs("gateway", "iata_airport", True), _fs("destination", "iata_airport", True),
            _fs("airline_iata", "airline_code", False), _fs("flight_number", "str", False),
            _fs("departure_days", "weekdays", True, description="ISO weekdays, e.g. 1;3;5"),
            _fs("departure_time", "hhmm", True, description="HH:MM local at the gateway"),
            _fs("connection_cutoff_minutes", "int", False, description="Minutes before departure; blank = unknown"),
        ),
        source_of_truth="Airline schedules at WFC gateways", freshness_sla_hours=720, retention="Current + 1 year",
    ),
}
# Datasets whose committed imports can be reversed. The others are referenced by qualification, agreements or history
# and are corrected by re-importing the corrected rows under the same duplicate key.
REVERSIBLE = frozenset({"bookings", "quotes", "capacity", "trucking", "finance", "channel_events", "training_credentials",
                        "gateway_connections", "airports", "stations", "contacts", "service_requirements"})
MASTER_DATA = ("airports", "airlines", "operating_companies", "territories", "services", "service_requirements", "contacts", "stations")


# --------------------------------------------------------------------- file validation


class FileRejected(ValueError):
    pass


def validate_upload(filename: str, data: bytes) -> Literal["csv", "xlsx"]:
    if len(data) == 0:
        raise FileRejected("file is empty")
    if len(data) > MAX_FILE_BYTES:
        raise FileRejected(f"file exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB")
    lower = filename.lower()
    if lower.endswith((".xlsm", ".xlsb", ".xls")):
        raise FileRejected("macro-enabled or legacy Excel formats are not accepted; save as .xlsx or .csv")
    if lower.endswith(".xlsx"):
        if not data.startswith(b"PK\x03\x04"):
            raise FileRejected("file is not a valid .xlsx (zip) document")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                raise FileRejected("workbook contains macros")
            total = sum(i.file_size for i in zf.infolist())
            if total > MAX_FILE_BYTES * 10:
                raise FileRejected("workbook expands beyond the allowed size")
        return "xlsx"
    if lower.endswith(".csv"):
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FileRejected("CSV must be UTF-8 encoded") from exc
        return "csv"
    raise FileRejected("only .csv and .xlsx files are accepted")


def read_rows(kind: Literal["csv", "xlsx"], data: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    if kind == "csv":
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        rows = [{(k or "").strip(): v for k, v in r.items()} for r in reader]
        return headers, rows
    import openpyxl  # local import: only needed for xlsx

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header_row = next(it, None) or ()
    headers = [str(h).strip() if h is not None else "" for h in header_row]
    rows = []
    for values in it:
        if values is None or all(v is None or (isinstance(v, str) and not v.strip()) for v in values):
            continue
        rows.append({headers[i]: values[i] for i in range(min(len(headers), len(values))) if headers[i]})
    wb.close()
    return headers, rows


# --------------------------------------------------------------------- mapping and validation


@dataclass
class MappingPreview:
    mapping: dict[str, str]          # contract field -> file column
    unmapped_required: list[str]
    unused_columns: list[str]


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def propose_mapping(contract: DatasetContract, headers: Sequence[str], explicit: Mapping[str, str] | None = None) -> MappingPreview:
    explicit = dict(explicit or {})
    by_norm = {_norm(h): h for h in headers}
    mapping: dict[str, str] = {}
    for f in contract.fields:
        if f.name in explicit and explicit[f.name] in headers:
            mapping[f.name] = explicit[f.name]
        elif _norm(f.name) in by_norm:
            mapping[f.name] = by_norm[_norm(f.name)]
    unmapped = [f for f in contract.required if f not in mapping]
    unused = [h for h in headers if h not in mapping.values()]
    return MappingPreview(mapping, unmapped, unused)


ISO_CURRENCIES = {"AED", "USD", "EUR", "GBP", "INR", "SAR", "QAR", "KWD", "OMR", "BHD", "CNY", "HKD", "SGD", "JPY", "CHF",
                  "AUD", "CAD", "ZAR", "EGP", "PKR", "BDT", "LKR", "KES", "NGN", "TRY", "MYR", "THB"}


_PLAIN_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_GROUPED_NUMBER = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def _parse(spec: FieldSpec, raw: Any, naive_tz: str | None = None) -> Any:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    if spec.type == "str":
        return str(raw).strip()
    if spec.type == "int":
        if isinstance(raw, bool):
            raise ValueError("not an integer")
        if isinstance(raw, float) and not raw.is_integer():
            raise ValueError("not an integer")
        return int(str(raw).strip().split(".")[0]) if isinstance(raw, float) else int(str(raw).strip())
    if spec.type == "decimal":
        if isinstance(raw, bool):
            raise ValueError("not a number")
        if isinstance(raw, (int, float)):
            text = repr(raw)  # spreadsheet numeric cell; repr avoids binary-float artefacts
        else:
            text = str(raw).strip()
            if _GROUPED_NUMBER.match(text):
                text = text.replace(",", "")
            elif not _PLAIN_NUMBER.match(text):
                raise ValueError(f"ambiguous or invalid number {raw!r}: use digits with '.' as the decimal separator")
        try:
            d = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"not a number: {raw!r}") from exc
        if not d.is_finite():
            raise ValueError("not a finite number")
        return d
    if spec.type == "date":
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        return date.fromisoformat(str(raw).strip()[:10])
    if spec.type == "datetime":
        if isinstance(raw, datetime):
            dt = raw
        else:
            dt = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            if not naive_tz:
                raise ValueError("datetime has no UTC offset; include one (e.g. 2026-10-01T08:00:00+04:00) or declare the file's time zone")
            dt = dt.replace(tzinfo=ZoneInfo(naive_tz))
        return dt.astimezone(timezone.utc)
    if spec.type == "currency":
        c = str(raw).strip().upper()
        if c not in ISO_CURRENCIES:
            raise ValueError(f"unsupported currency {c!r}")
        return c
    if spec.type == "iata_airport":
        c = str(raw).strip().upper()
        if len(c) != 3 or not c.isalpha():
            raise ValueError(f"invalid IATA airport code {raw!r}")
        return c
    if spec.type == "enum":
        v = str(raw).strip().lower()
        if v not in spec.choices:
            raise ValueError(f"must be one of {', '.join(spec.choices)}")
        return v
    if spec.type == "country":
        from ..reference.geography import COUNTRIES

        c = str(raw).strip().upper()
        if c not in COUNTRIES:
            raise ValueError(f"unknown ISO 3166-1 alpha-2 country code {raw!r}")
        return c
    if spec.type == "timezone":
        tz = str(raw).strip()
        try:
            ZoneInfo(tz)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"unknown IANA time zone {raw!r}") from exc
        return tz
    if spec.type == "bool":
        v = str(raw).strip().lower()
        if v in ("yes", "y", "true", "1"):
            return True
        if v in ("no", "n", "false", "0"):
            return False
        raise ValueError("must be yes or no")
    if spec.type == "airline_code":
        c = str(raw).strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{2}", c):
            raise ValueError(f"invalid IATA airline designator {raw!r}")
        return c
    if spec.type == "weekdays":
        parts = [p.strip() for p in str(raw).replace(",", ";").split(";") if p.strip()]
        try:
            days = sorted({int(p) for p in parts})
        except ValueError as exc:
            raise ValueError("weekdays must be numbers 1 (Monday) to 7 (Sunday) separated by ';'") from exc
        if not days or any(d < 1 or d > 7 for d in days):
            raise ValueError("weekdays must be numbers 1 (Monday) to 7 (Sunday)")
        return ";".join(str(d) for d in days)
    if spec.type == "hhmm":
        m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::00)?", str(raw).strip())
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError("time must be HH:MM (24-hour)")
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    raise ValueError(f"unsupported type {spec.type}")


@dataclass
class RowError:
    row_number: int
    field: str | None
    code: str
    message: str
    raw: dict


@dataclass
class ValidRow:
    row_number: int
    key: str
    values: dict[str, Any]
    raw: dict


def _cross_field(dataset: str, v: dict) -> list[tuple[str, str]]:
    errs: list[tuple[str, str]] = []
    if v.get("origin") and v.get("destination") and v["origin"] == v["destination"]:
        errs.append(("destination", "origin and destination must differ"))
    for money, ccy in (("revenue", "currency"), ("amount", "currency")):
        if v.get(money) is not None and v.get(ccy) is None and any(f.name == ccy for f in CONTRACTS[dataset].fields):
            errs.append((ccy, f"{money} requires a currency"))
    for a, b in (("period_start", "period_end"), ("effective_from", "effective_to"), ("valid_from", "valid_to")):
        if v.get(a) and v.get(b) and v[b] < v[a]:
            errs.append((b, f"{b} is before {a}"))
    for w in ("actual_weight", "chargeable_weight", "volume", "amount"):
        if dataset != "finance" and v.get(w) is not None and v[w] < 0:
            errs.append((w, "must not be negative"))
    return errs


_UNKNOWN_DEFAULT = {"exclusivity", "appointment_rights", "remuneration_model"}
_LIST_FIELDS = {"territories", "services"}


def _normalise(dataset: str, v: dict) -> dict:
    """Canonical form so a re-import compares equal to what was stored:
    'unknown' and blank mean the same thing; code lists are upper-cased,
    de-duplicated and sorted."""
    if dataset in ("services", "service_requirements", "territories", "stations"):
        for f in ("code", "service_code", "credential_type"):
            if v.get(f):
                v[f] = str(v[f]).strip().upper()
    if dataset == "training_credentials":
        for f in ("credential_type", "service_code"):
            if v.get(f):
                v[f] = str(v[f]).strip().upper()
    if dataset == "operating_companies" and v.get("is_group_member") is None:
        v["is_group_member"] = True
    if dataset == "contacts" and v.get("is_internal") is None:
        v["is_internal"] = False
    if dataset == "agreements":
        for f in _UNKNOWN_DEFAULT:
            if v.get(f) == "unknown":
                v[f] = None
        for f in _LIST_FIELDS:
            if v.get(f):
                v[f] = ";".join(sorted({p.strip().upper() for p in str(v[f]).split(";") if p.strip()}))
    return v


_NATURAL_KEYS = {"airports": ("iata_code",), "airlines": ("iata_code",), "operating_companies": ("name",), "territories": ("code",),
                 "services": ("code",), "service_requirements": ("service_code", "credential_type"), "stations": ("code",)}


def row_key(dataset: str, v: dict) -> str:
    if dataset in _NATURAL_KEYS:
        return "|".join(str(v.get(k) or "").upper() if k != "name" else str(v.get(k) or "").lower() for k in _NATURAL_KEYS[dataset])
    if "external_id" in v and v["external_id"]:
        return str(v["external_id"])
    if dataset == "capabilities":
        return f"{v.get('operating_company')}|{v.get('service_code')}|{v.get('station') or '*'}"
    if dataset == "finance":
        return f"{v.get('operating_company')}|{v.get('period_start')}|{v.get('period_end')}|{v.get('metric')}|{v.get('currency')}"
    raise ValueError("no key")


ReferenceCheck = Callable[[dict[str, Any]], list[tuple[str, str]]]


def validate_rows(contract: DatasetContract, mapping: Mapping[str, str], rows: Sequence[dict], *,
                  naive_tz: str | None = None, reference_check: ReferenceCheck | None = None) -> tuple[list[ValidRow], list[RowError]]:
    valid: list[ValidRow] = []
    errors: list[RowError] = []
    seen: dict[str, int] = {}
    for i, raw in enumerate(rows, start=2):  # row 1 is the header
        raw_json = {k: (v.isoformat() if isinstance(v, (date, datetime)) else (str(v) if v is not None else None)) for k, v in raw.items()}
        values: dict[str, Any] = {}
        row_errs: list[RowError] = []
        for spec in contract.fields:
            col = mapping.get(spec.name)
            val = raw.get(col) if col else None
            try:
                parsed = _parse(spec, val, naive_tz)
            except (ValueError, TypeError) as exc:
                row_errs.append(RowError(i, spec.name, "invalid_value", str(exc), raw_json))
                continue
            if parsed is None and spec.required:
                row_errs.append(RowError(i, spec.name, "required", f"{spec.name} is required", raw_json))
            values[spec.name] = parsed
        if not row_errs:
            for f, msg in _cross_field(contract.dataset, values):
                row_errs.append(RowError(i, f, "inconsistent", msg, raw_json))
        if not row_errs and reference_check is not None:
            for f, msg in reference_check(values):
                row_errs.append(RowError(i, f, "unresolved_reference", msg, raw_json))
        if row_errs:
            errors.extend(row_errs)
            continue
        values = _normalise(contract.dataset, values)
        key = row_key(contract.dataset, values)
        if key in seen:
            errors.append(RowError(i, "external_id", "duplicate_in_file", f"duplicate of row {seen[key]}", raw_json))
            continue
        seen[key] = i
        valid.append(ValidRow(i, key, values, raw_json))
    return valid, errors


# --------------------------------------------------------------------- upsert planning and reconciliation


@dataclass
class PlannedEffect:
    row_number: int
    key: str
    action: Literal["insert", "update", "unchanged"]
    values: dict
    previous: dict | None


@dataclass
class Reconciliation:
    dataset: str
    file_sha256: str
    schema_version: str
    rows_read: int
    rows_valid: int
    rows_quarantined: int
    inserted: int
    updated: int
    unchanged: int
    sums: dict[str, dict[str, str]] = field(default_factory=dict)  # field -> {currency or unit: total}


def _comparable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return v.normalize()
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat() if v.tzinfo else v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        # values stored as JSON text (e.g. exception reports) compare equal to their parsed form
        try:
            parsed = datetime.fromisoformat(v)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return v


def plan_upserts(valid: Sequence[ValidRow], existing: Mapping[str, Mapping[str, Any]]) -> list[PlannedEffect]:
    out = []
    for r in valid:
        prev = existing.get(r.key)
        if prev is None:
            out.append(PlannedEffect(r.row_number, r.key, "insert", r.values, None))
        elif all(_comparable(prev.get(k)) == _comparable(v) for k, v in r.values.items()):
            out.append(PlannedEffect(r.row_number, r.key, "unchanged", r.values, dict(prev)))
        else:
            out.append(PlannedEffect(r.row_number, r.key, "update", r.values, dict(prev)))
    return out


def reconcile(contract: DatasetContract, data: bytes, rows_read: int, valid: Sequence[ValidRow],
              errors: Sequence[RowError], effects: Sequence[PlannedEffect]) -> Reconciliation:
    sums: dict[str, dict[str, str]] = {}
    for f in contract.reconcile_sums:
        spec = next(s for s in contract.fields if s.name == f)
        acc: dict[str, Decimal] = {}
        for r in valid:
            v = r.values.get(f)
            if v is None:
                continue
            if r.values.get("status") == "cancelled":
                continue
            bucket = r.values.get("currency") if spec.unit is None and "currency" in r.values else (spec.unit or r.values.get("basis") or "value")
            bucket = bucket or "no_currency"
            acc[bucket] = acc.get(bucket, Decimal("0")) + v
        sums[f] = {k: str(v) for k, v in sorted(acc.items())}
    bad_rows = len({e.row_number for e in errors})
    return Reconciliation(
        dataset=contract.dataset, file_sha256=hashlib.sha256(data).hexdigest(), schema_version=SCHEMA_VERSION,
        rows_read=rows_read, rows_valid=len(valid), rows_quarantined=bad_rows,
        inserted=sum(e.action == "insert" for e in effects), updated=sum(e.action == "update" for e in effects),
        unchanged=sum(e.action == "unchanged" for e in effects), sums=sums,
    )


def run_import(dataset: str, filename: str, data: bytes, existing: Mapping[str, Mapping[str, Any]],
               explicit_mapping: Mapping[str, str] | None = None, *, naive_tz: str | None = None,
               reference_check: ReferenceCheck | None = None) -> tuple[MappingPreview, list[PlannedEffect], list[RowError], Reconciliation]:
    """Pure dry run. The service layer persists `effects` only on commit, in
    one transaction, recording `import_row_effects` for reversal."""
    contract = CONTRACTS[dataset]
    kind = validate_upload(filename, data)
    headers, rows = read_rows(kind, data)
    preview = propose_mapping(contract, headers, explicit_mapping)
    if preview.unmapped_required:
        err = RowError(1, None, "mapping", f"required fields not mapped: {', '.join(preview.unmapped_required)}", {"headers": headers})
        return preview, [], [err], reconcile(contract, data, len(rows), [], [err], [])
    if naive_tz:
        ZoneInfo(naive_tz)  # raises for an unknown zone name
    valid, errors = validate_rows(contract, preview.mapping, rows, naive_tz=naive_tz, reference_check=reference_check)
    effects = plan_upserts(valid, existing)
    return preview, effects, errors, reconcile(contract, data, len(rows), valid, errors, effects)


def reversal_plan(effects: Sequence[PlannedEffect]) -> list[tuple[str, Literal["delete", "restore"], dict | None]]:
    """Undo a committed batch: inserted rows are removed, updated rows get
    their previous values back. Unchanged rows are left alone."""
    out: list[tuple[str, Literal["delete", "restore"], dict | None]] = []
    for e in effects:
        if e.action == "insert":
            out.append((e.key, "delete", None))
        elif e.action == "update":
            out.append((e.key, "restore", e.previous))
    return out


def template_csv(dataset: str) -> str:
    contract = CONTRACTS[dataset]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([f.name for f in contract.fields])
    return buf.getvalue()
