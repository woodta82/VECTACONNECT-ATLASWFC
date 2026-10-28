"""Import documentation rendered from the live contracts, so the documentation cannot drift from the code.

`render()` returns {relative path: content} for docs/import-templates/*.csv, docs/import-templates/FIELDS.md and the
generated dataset section of docs/CONNECTORS_AND_DATASETS.md. tools/gen_import_templates.py writes them;
tests/unit/test_import_docs.py fails if the files on disk differ from what the code would generate.
"""
from __future__ import annotations

from . import imports as im

# The business workflows that read each dataset (modules_service.*: the `_loaded(...)` sources of each view).
USED_BY: dict[str, tuple[str, ...]] = {
    "bookings": ("Forwarder sales", "Capacity and lanes", "Account growth (airline booking evidence)", "Technology and solutions (adoption)"),
    "quotes": ("Forwarder sales (conversion, lost reasons)",),
    "capacity": ("Capacity and lanes (utilisation, spare capacity)",),
    "exceptions": ("Service and operations (alert, task, resolution history)",),
    "agreements": ("Account growth (mandates, appointment rights)", "Network development (coverage gaps)", "Qualification (territory conflict)"),
    "capabilities": ("Qualification (capability check)", "Account growth", "Outsourcing and training", "Network development"),
    "training_credentials": ("Outsourcing and training (valid credentials)", "Qualification (credential requirements)"),
    "service_requirements": ("Qualification (credentials each service requires)",),
    "trucking": ("Trucking and gateways (feeder feasibility)", "Technology and solutions (combined service)"),
    "gateway_connections": ("Trucking and gateways (connection cutoffs)",),
    "channel_events": ("Technology and solutions (funnel, integration failures, adoption)",),
    "finance": ("Briefing and account context (month-end aggregates; not used for scoring)",),
    "airports": ("Reference: airport country and time zone for lanes, deadlines and cutoffs",),
    "airlines": ("Reference: airline identity for agreements, bookings and discovery",),
    "operating_companies": ("Reference: WFC group companies for every dataset",),
    "territories": ("Reference: territory definitions for agreements and discovery regions",),
    "services": ("Reference: service catalogue for capabilities and qualification",),
    "stations": ("Reference: WFC stations and offline points (capability location, trucking)",),
    "contacts": ("Reference: internal owners and relationship records (no VECTA contacts are imported)",),
}

# Why a required field is required. Field names repeat across datasets with the same meaning.
WHY_REQUIRED: dict[str, str] = {
    "external_id": "stable source id: the duplicate key that makes a re-import an update, not a second row, and makes reversal exact",
    "origin": "lane direction; utilisation and yield are computed per directional lane",
    "destination": "lane direction; utilisation and yield are computed per directional lane",
    "booked_at": "when the booking was made, with a UTC offset; dates the record",
    "status": "the record's state in the source; cancelled records are excluded from volumes",
    "forwarder": "the account the record belongs to",
    "quoted_at": "dates the quote for the reporting period",
    "airline_iata": "identifies the represented airline",
    "airline_name": "names the airline if it is not yet in the reference list",
    "operating_company": "the WFC company that holds the record",
    "territories": "the countries the mandate covers (ISO codes, ';' separated)",
    "services": "the services the mandate covers (service codes, ';' separated)",
    "service_code": "the service from the WFC service catalogue",
    "period_start": "start of the period the figure applies to",
    "period_end": "end of the period the figure applies to",
    "basis": "what the figure measures; figures on different bases are never combined",
    "capacity_type": "bookable or physical capacity; only like-for-like capacity is compared",
    "amount": "the figure itself, in the unit or currency stated",
    "snapshot_at": "when the capacity was published; dates its freshness",
    "exception_type": "routes the alert and task",
    "severity": "decides alert urgency",
    "description": "what went wrong, as recorded",
    "provider": "the trucking provider",
    "origin_station": "the offline station the feeder serves",
    "gateway": "the airport the feeder reaches",
    "departure_days": "ISO weekdays (1=Mon … 7=Sun, ';' separated); a feeder not running on the ship date is infeasible",
    "departure_time": "local departure time at the departure point",
    "metric": "which month-end figure this is",
    "currency": "ISO 4217 code; amounts in different currencies are never summed",
    "event_type": "the funnel stage or failure type",
    "channel": "the digital channel the event came from",
    "occurred_at": "when the event happened, with a UTC offset",
    "credential_type": "the credential, matched against what each service requires",
    "issued_on": "start of the credential's validity",
    "iata_code": "the IATA code: the natural duplicate key",
    "name": "the display name and, for operating companies, the natural duplicate key",
    "country": "ISO 3166 alpha-2 country, used for territory and discovery geography",
    "timezone": "IANA time zone, used for deadlines and cutoffs",
    "code": "the natural duplicate key",
    "category": "groups the service in the catalogue",
    "full_name": "identifies the person",
    "is_offline": "marks an offline point served by road feeder",
    "flight_number": "identifies the connecting flight",
    "connection_cutoff_minutes": "how long before departure cargo must arrive",
    "kind": "whether the territory is a country or a grouping (region), which decides how discovery expands it",
}

KEY_DESCRIPTION: dict[str, str] = {
    "capabilities": "operating_company + service_code + station ('*' if company-wide)",
    "finance": "operating_company + period_start + period_end + metric + currency",
}


def duplicate_key(dataset: str) -> str:
    if dataset in im._NATURAL_KEYS:
        return " + ".join(im._NATURAL_KEYS[dataset])
    if dataset in KEY_DESCRIPTION:
        return KEY_DESCRIPTION[dataset]
    return "external_id"


def refresh_requirement(dataset: str) -> str:
    """The label shown wherever the dataset is used, while no live feed is connected."""
    c = im.CONTRACTS[dataset]
    if c.freshness_sla_hours:
        h = c.freshness_sla_hours
        span = f"{h} hours" if h < 48 else f"{h // 24} days"
        return (f"Manual import (no live feed connected): re-import at least every {span}; after that the data is shown as "
                "Stale and recommendations that depend on it are labelled stale")
    return "Register data: re-import whenever the source register changes; it does not go stale by age"


def correction_mode(dataset: str) -> str:
    if dataset in im.REVERSIBLE:
        return ("Reversible: a committed import can be reversed (inserted rows removed, updated rows restored to their previous "
                "values); correct by editing the file and re-importing")
    return ("Correct by re-import: re-import the corrected rows with the same duplicate key; reversal is refused because these "
            "records are referenced by qualification, agreements or history")


def _units(c: im.DatasetContract) -> str:
    parts = [f"`{f.name}` in {f.unit}" for f in c.fields if f.unit]
    if any(f.type == "currency" for f in c.fields):
        parts.append("money with its ISO 4217 `currency` (never converted or summed across currencies)")
    if any(f.type == "datetime" for f in c.fields):
        parts.append("timestamps with a UTC offset (or a stated time zone at upload)")
    return "; ".join(parts) or "none"


def fields_md() -> str:
    lines = ["# Import templates and fields", "",
             "Generated by `tools/gen_import_templates.py` from `backend/app/domain/imports.py`; a test fails if this file drifts.",
             "Each CSV in this folder holds the header row only; the same template downloads in the app under Data Sources and Imports.",
             "",
             "Every import follows the same path: **upload → mapping preview → validation → preview → commit → reconciliation**.",
             "Nothing is written until the reviewed preview is committed, and the commit applies exactly that preview. Rows that fail",
             "validation are quarantined with a reason and never committed. A re-import with an existing duplicate key updates the row",
             "(or is reported unchanged); it never creates a second record.", "",
             "Setup (master data) datasets load first on a fresh installation, in this order: operating companies, airports,",
             "airlines, territories, services, service requirements, stations, contacts.", ""]
    for name in sorted(im.CONTRACTS):
        c = im.CONTRACTS[name]
        kind = "Setup (master data)" if name in im.MASTER_DATA else "Operational"
        lines += [f"## {name}", "",
                  f"- **Kind:** {kind}. **Source of truth:** {c.source_of_truth}.",
                  f"- **Used by:** {'; '.join(USED_BY.get(name, ('—',)))}.",
                  f"- **Refresh:** {refresh_requirement(name)}.",
                  f"- **Duplicate key:** {duplicate_key(name)}.",
                  f"- **Corrections:** {correction_mode(name)}.",
                  "- **Reconciliation:** rows read = committed + quarantined" + (f"; column totals checked: {', '.join(c.reconcile_sums)}"
                                                                                  if c.reconcile_sums else "") + ".",
                  f"- **Units:** {_units(c)}.",
                  f"- **Retention:** {c.retention}.", "",
                  "| Field | Type | Required | Allowed values / unit | Meaning / why required |", "|---|---|---|---|---|"]
        for f in c.fields:
            allowed = ", ".join(f.choices) if f.choices else (f.unit or "")
            why = f.description or ""
            if f.required and f.name in WHY_REQUIRED:
                why = (why + "; " if why else "") + WHY_REQUIRED[f.name]
            lines.append(f"| `{f.name}` | {f.type} | {'yes' if f.required else 'no'} | {allowed} | {why} |")
        lines.append("")
    return "\n".join(lines)


def datasets_section() -> str:
    lines = [DATASETS_BEGIN, "",
             f"All {len(im.CONTRACTS)} datasets support upload, mapping, validation, preview, commit and reconciliation. "
             "Generated from the contracts; field detail is in `docs/import-templates/FIELDS.md`.", "",
             "| Dataset | Kind | Target table | Source of truth | Refresh | Duplicate key | Corrections | Required fields | Reconciliation totals |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name in sorted(im.CONTRACTS):
        c = im.CONTRACTS[name]
        req = ", ".join(f"`{f.name}`" for f in c.fields if f.required)
        refresh = f"every {c.freshness_sla_hours} h" if c.freshness_sla_hours else "on change"
        lines.append(f"| {name} | {'setup' if name in im.MASTER_DATA else 'operational'} | `{c.target_table}` | {c.source_of_truth} | {refresh} | "
                     f"{duplicate_key(name)} | {'reversible' if name in im.REVERSIBLE else 're-import'} | {req} | "
                     f"{', '.join(c.reconcile_sums) or '—'} |")
    lines += ["", DATASETS_END]
    return "\n".join(lines)


DATASETS_BEGIN = "<!-- BEGIN GENERATED DATASETS (tools/gen_import_templates.py) -->"
DATASETS_END = "<!-- END GENERATED DATASETS -->"


def splice(doc: str) -> str:
    """Replace the generated section of CONNECTORS_AND_DATASETS.md."""
    head, _, rest = doc.partition(DATASETS_BEGIN)
    _, _, tail = rest.partition(DATASETS_END)
    return head + datasets_section() + tail


def render(connectors_doc: str) -> dict[str, str]:
    out = {f"docs/import-templates/{n}.csv": ",".join(f.name for f in im.CONTRACTS[n].fields) + "\n" for n in im.CONTRACTS}
    out["docs/import-templates/FIELDS.md"] = fields_md()
    out["docs/CONNECTORS_AND_DATASETS.md"] = splice(connectors_doc)
    return out
