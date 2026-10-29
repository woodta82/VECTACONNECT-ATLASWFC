"""Local stand-ins used by the integration tests, the browser journeys and the
local demonstration stack. SIMULATED, clearly labelled, never used in
production:

- `FixtureSite`: serves tests/fixtures/site (synthetic airline portal, trade
  press and a procurement search endpoint) on 127.0.0.1.
- `FakeAIProvider`: implements POST /v1/messages of the Anthropic Messages
  API. It does NOT interpret documents: it returns canned claim JSON keyed
  by a unique phrase in each fixture document (the tender reference or
  headline), with token usage for cost accounting. One fixture deliberately
  returns an unsupported field and one returns a malformed claim, so the
  validation and review paths are exercised.

Run standalone with tools/fixture_site.py and tools/fake_ai_provider.py.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SITE = Path(__file__).resolve().parent / "site"

SEARCH_INDEX = {
    "CI": [("/procure/ci-formation-fret.html", "Appel d'offres : formation du personnel fret")],
    "AE": [("/procure/ae-rfs-sample-airways.html", "RFQ SAW-RFS-2026-07: Road feeder services, UAE")],
}


# Simulated search index (relationship research and open-web discovery): (words the query must contain, fixture path, title).
# Discovery queries carry the country name in quotes and the area's terms; the index answers a few of them with fixture pages
# (one of which is registration-restricted, to show that a restricted result is labelled and does not stop the search).
SEARCH_STANDIN = [
    (("savanna example air", "appoint"), "/sea-press/appointment.html", "Savanna Example Air appoints Country Manager Uganda"),
    (("oman", "ground handling"), "/tradewire/oman-handling.html", "Coastal Handling signs partnership agreement in Oman"),
    (("oman", "ground handling"), "/restricted/oman-handling-tender.html", "Tender: cargo terminal handling services, Muscat (members only)"),
    (("united arab emirates", "road feeder"), "/procure/ae-rfs-sample-airways.html", "RFQ SAW-RFS-2026-07: Road feeder services, UAE"),
    (("côte d'ivoire", "outsourcing"), "/procure/ci-formation-fret.html", "Appel d'offres : formation du personnel fret"),
    (("ivory coast", "outsourcing"), "/procure/ci-formation-fret.html", "Appel d'offres : formation du personnel fret"),
]


class _SiteHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):  # noqa: N802
        parts = urlsplit(self.path)
        if parts.path == "/procure/search":
            q = parse_qs(parts.query)
            country = (q.get("country") or [""])[0].upper()
            links = "".join(f'<li><a href="{u}">{t}</a></li>' for u, t in SEARCH_INDEX.get(country, []))
            body = (f"<!doctype html><html lang='en'><head><title>Search results {country}</title></head><body><main>"
                    f"<h1>Results for {country}</h1><ul>{links}</ul></main></body></html>").encode()
            return self._send(200, "text/html; charset=utf-8", body)
        if parts.path == "/broken/":
            return self._send(503, "text/html", b"<html><body>Service unavailable</body></html>")
        if parts.path.startswith("/restricted/"):
            # a registration-restricted result: labelled by discovery, never read, never bypassed
            return self._send(401, "text/html", b"<html><body>Please log in or register to view this tender notice.</body></html>")
        if parts.path == "/search-api/res/v1/web/search":
            return self._search(parse_qs(parts.query))
        rel = parts.path.lstrip("/")
        if rel.endswith("/") or rel == "":
            rel += "index.html"
        f = (SITE / rel).resolve()
        if not str(f).startswith(str(SITE)) or not f.is_file():
            return self._send(404, "text/html", b"<html><body>Not found</body></html>")
        ctype = {".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8"}.get(f.suffix, "text/html; charset=utf-8")
        return self._send(200, ctype, f.read_bytes())

    def _search(self, q: dict) -> None:
        """SIMULATED stand-in for the Brave Search API (local stack and tests only): a fixed index of fixture pages."""
        if not self.headers.get("X-Subscription-Token"):
            return self._send(401, "application/json", b'{"error": "missing token"}')
        text = (q.get("q") or [""])[0].lower()
        base = f"http://{self.headers.get('Host')}"
        hits = []
        for keys, path, title in SEARCH_STANDIN:
            if all(k in text for k in keys):
                hits.append({"url": base + path, "title": title, "description": "fixture page (simulated search result)"})
        return self._send(200, "application/json", json.dumps({"web": {"results": hits}}).encode())

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _f(value: str, quote: str) -> dict[str, str]:
    return {"value": value, "quote": quote}


Q14 = "Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya."
Q22 = "Example Air invites proposals for a General Sales and Service Agent for cargo at Moi International Airport, Mombasa, Kenya."
Q31 = ("Example Air invites proposals from GSSA providers for cargo representation across Kenya, Uganda and Tanzania under one "
       "regional agreement.")
QRFS = "Sample Airways invites quotations for road feeder trucking services between Dubai and Abu Dhabi in the United Arab Emirates."
QCI = "Sample Airways lance un appel d'offres pour la formation de son personnel fret en Côte d'Ivoire."

CANNED: list[tuple[str, dict]] = [
    ("Addendum 1 to RFP EXA-CGO-2026-014", {"language": "en", "claims": [
        {"claim_type": "tender_deadline", "stance": "supports", "deadline_timezone": "Africa/Nairobi",
         "quote": "The submission deadline is extended to 14 December 2026 at 17:00 EAT.",
         "fields": {"airline": _f("Example Air", "Example Air has extended the submission deadline for tender reference EXA-CGO-2026-014."),
                    "tender_ref": _f("EXA-CGO-2026-014", "tender reference EXA-CGO-2026-014"),
                    "status": _f("revised", "The submission deadline is extended to 14 December 2026 at 17:00 EAT."),
                    "deadline": _f("2026-12-14T17:00:00", "The submission deadline is extended to 14 December 2026 at 17:00 EAT.")}}]}),
    ("Tender reference EXA-CGO-2026-014.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "deadline_timezone": "Africa/Nairobi", "quote": Q14,
         "fields": {"airline": _f("Example Air", Q14), "country": _f("Kenya", Q14), "service": _f("GSSA", Q14),
                    "tender_ref": _f("EXA-CGO-2026-014", "Tender reference EXA-CGO-2026-014."), "status": _f("open", Q14),
                    "deadline": _f("2026-11-30T17:00:00", "Proposals must be submitted by 30 November 2026 at 17:00 EAT."),
                    # Deliberately unsupported: the document never names the issuer's country.
                    "issuer_country": _f("United Arab Emirates", Q14)}},
        {"claim_type": "eligibility", "stance": "supports",
         "quote": "Eligible bidders must hold IATA cargo agent accreditation and a Kenyan trading licence.",
         "fields": {"eligibility": _f("IATA cargo agent accreditation; Kenyan trading licence",
                                      "Eligible bidders must hold IATA cargo agent accreditation and a Kenyan trading licence.")}}]}),
    ("Tender reference EXA-CGO-2026-022.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "deadline_timezone": "Africa/Nairobi", "quote": Q22,
         "fields": {"airline": _f("Example Air", Q22), "country": _f("Kenya", Q22), "service": _f("GSSA", Q22),
                    "tender_ref": _f("EXA-CGO-2026-022", "Tender reference EXA-CGO-2026-022."), "status": _f("open", Q22),
                    "deadline": _f("2026-12-15T12:00:00", "Submissions are due by 15 December 2026 at 12:00 EAT.")}}]}),
    ("Tender reference EXA-CGO-2026-031.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "deadline_timezone": "Africa/Nairobi", "quote": Q31,
         "fields": {"airline": _f("Example Air", Q31), "country": _f("Kenya", Q31), "contract_territory": _f("Uganda", Q31),
                    "service": _f("GSSA", Q31), "tender_ref": _f("EXA-CGO-2026-031", "Tender reference EXA-CGO-2026-031."),
                    "status": _f("open", Q31),
                    "deadline": _f("2027-01-15T17:00:00", "Proposals must be submitted by 15 January 2027 at 17:00 EAT.")}},
        # A malformed claim (unknown field) is rejected individually into the review queue.
        {"claim_type": "gssa_tender", "quote": Q31, "fields": {"airline": _f("Example Air", Q31)}, "confidence": "high"}]}),
    ("twice-weekly Boeing 777F service from Dubai (DXB) to Nairobi (NBO)", {"language": "en", "claims": [
        {"claim_type": "route_launch", "stance": "supports",
         "quote": "Example Air will operate a twice-weekly Boeing 777F service from Dubai (DXB) to Nairobi (NBO) from 3 November 2026.",
         "fields": {"airline": _f("Example Air", "Example Air will operate a twice-weekly Boeing 777F service from Dubai (DXB) to Nairobi (NBO) from 3 November 2026."),
                    "origin": _f("DXB", "from Dubai (DXB) to Nairobi (NBO)"), "destination": _f("NBO", "from Dubai (DXB) to Nairobi (NBO)"),
                    # A route announcement cannot establish a tender status: recorded as not applicable.
                    "status": _f("open", "The new route expands the carrier's African cargo network.")}}]}),
    ("Trade sources say Sample Airways has issued a request for quotation", {"language": "en", "claims": [
        {"claim_type": "service_tender", "stance": "supports",
         "quote": "Trade sources say Sample Airways has issued a request for quotation for road feeder trucking services between Dubai and Abu Dhabi in the United Arab Emirates.",
         "fields": {"airline": _f("Sample Airways", "Trade sources say Sample Airways has issued a request for quotation"),
                    "country": _f("United Arab Emirates", "between Dubai and Abu Dhabi in the United Arab Emirates"),
                    "service": _f("TRUCKING", "road feeder trucking services")}}]}),
    ("Reference SAW-RFS-2026-07.", {"language": "en", "claims": [
        {"claim_type": "service_tender", "stance": "supports", "deadline_timezone": "Asia/Dubai", "quote": QRFS,
         "fields": {"airline": _f("Sample Airways", QRFS), "country": _f("United Arab Emirates", QRFS), "service": _f("TRUCKING", QRFS),
                    "tender_ref": _f("SAW-RFS-2026-07", "Reference SAW-RFS-2026-07."), "status": _f("open", QRFS),
                    "deadline": _f("2026-12-05T16:00:00", "Quotations must be submitted by 5 December 2026 at 16:00 GST.")}}]}),
    ("Coastal Handling has signed a partnership agreement", {"language": "en", "claims": [
        {"claim_type": "partnership", "stance": "supports",
         "quote": "Coastal Handling has signed a partnership agreement with a cargo terminal operator in Oman covering export handling at Muscat.",
         "fields": {"organisation": _f("Coastal Handling", "Coastal Handling has signed a partnership agreement"),
                    "country": _f("Oman", "a cargo terminal operator in Oman")}}]}),
    ("SAW-FORM-2026-03", {"language": "fr",
                          "summary_en": "Sample Airways is tendering for cargo staff training in Côte d'Ivoire; offers due 18 December 2026 12:00 GMT.",
                          "claims": [
        {"claim_type": "service_tender", "stance": "supports", "deadline_timezone": "Africa/Abidjan", "quote": QCI,
         "fields": {"airline": _f("Sample Airways", QCI), "country": _f("Côte d'Ivoire", QCI), "service": _f("TRAINING", QCI),
                    "tender_ref": _f("SAW-FORM-2026-03", "Référence de l'appel d'offres : SAW-FORM-2026-03."), "status": _f("open", QCI),
                    "deadline": _f("2026-12-18T12:00:00", "Les offres doivent être soumises au plus tard le 18 décembre 2026 à 12:00 GMT.")}}]}),
]


# Long Mauritius notice (fixture site /long/): the announcement is in the first section, the reference and the
# date-only deadline only in the last one, so a complete read is needed to find them.
QMU = "Mauritius Cargo Airways invites proposals from GSSA providers for cargo sales and service representation in Mauritius."
QMU_END = "Proposals are due on 15 January 2027."
CANNED += [
    ("Tender reference MCA-GSSA-2027-01.", {"language": "en", "claims": [
        {"claim_type": "tender_deadline", "stance": "supports", "quote": QMU_END,
         "fields": {"tender_ref": _f("MCA-GSSA-2027-01", "Tender reference MCA-GSSA-2027-01."), "deadline": _f("2027-01-15", QMU_END)}}]}),
    (QMU, {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "quote": QMU,
         "fields": {"airline": _f("Mauritius Cargo Airways", QMU), "country": _f("Mauritius", QMU), "service": _f("GSSA", QMU),
                    "status": _f("open", QMU)}}]}),
]


# Freight relevance, status/age and geography conflict notices (fixture site /relevance/, 27 Oct 2026 second instruction).
QPAX_T = "REQUEST FOR PROPOSAL FOR APPOINTMENT OF A GENERAL SALES AGENT (GSA) FOR PASSENGER SALES OF GULF EXAMPLE AIRWAYS IN OMAN"
QPAX = "Gulf Example Airways invites proposals for the appointment of a General Sales Agent (GSA) for passenger sales and ticketing in Oman. Tender reference GEA-PAX-2026-11."
QPAX_D = "Proposals must be submitted by 20 January 2027 at 16:00 GST."
QOLD = "Gulf Example Airways. Reference GEA-GSSA-2022-3. Request for proposal for the appointment of a cargo GSSA in Oman."
QOLD_B = "Applicants shall submit a separate application for each territory they apply for."
QTER_T = "REQUEST FOR PROPOSAL FOR APPOINTMENT OF CARGO GENERAL SALES AND SERVICE AGENT (GSSA) OF GULF EXAMPLE AIRWAYS IN OMAN"
QTER_A = "Date of Issue: 15-10-2026. Reference GEA-GSSA-2026-9."
QTER_B = '"Territory" shall mean the geographical limits of the country i.e., Oman.'
QTER_C = "Disclaimer: this request for proposal is issued for cargo sales in Kingdom of Saudi Arabia."
QTER_D = "Last date for submission of proposal 06-12-2026."
CANNED += [
    ("Tender reference GEA-PAX-2026-11.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "quote": QPAX, "deadline_timezone": "Asia/Muscat",
         "fields": {"airline": _f("Gulf Example Airways", QPAX), "country": _f("Oman", QPAX), "service": _f("GSSA", QPAX_T), "status": _f("open", QPAX_D),
                    "tender_ref": _f("GEA-PAX-2026-11", QPAX), "deadline": _f("2027-01-20T16:00:00", QPAX_D)}}]}),
    ("Reference GEA-GSSA-2022-3.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "quote": QOLD,
         "fields": {"airline": _f("Gulf Example Airways", QOLD), "country": _f("Oman", QOLD), "service": _f("GSSA", QOLD), "status": _f("open", QOLD_B),
                    "tender_ref": _f("GEA-GSSA-2022-3", QOLD)}}]}),
    ("Reference GEA-GSSA-2026-9.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "quote": QTER_T,
         "fields": {"airline": _f("Gulf Example Airways", QTER_T), "country": _f("Oman", QTER_B), "service": _f("GSSA", QTER_T), "status": _f("open", QTER_D),
                    "tender_ref": _f("GEA-GSSA-2026-9", QTER_A), "deadline": _f("2026-12-06", QTER_D)}},
        {"claim_type": "gssa_tender", "stance": "supports", "quote": QTER_T,
         "fields": {"airline": _f("Gulf Example Airways", QTER_T), "country": _f("Saudi Arabia", QTER_C), "service": _f("GSSA", QTER_T), "status": _f("open", QTER_D),
                    "tender_ref": _f("GEA-GSSA-2026-9", QTER_A)}}]}),
]


# Meaning-level relevance and announced status notices (fixture site /meaning/, third instruction of 27 Oct 2026).
QEX = "Rift Example Air invites proposals from general sales agents for representation in Ethiopia. Cargo sales are excluded from this mandate."
QEX_R = "Tender reference REA-GSA-2027-40. Proposals are due on 12 March 2027."
QRAMP = "Rift Example Air invites tenders for ramp lighting maintenance at Addis Ababa airport, Ethiopia. Tender reference REA-ENG-2027-3. Bids are due on 30 March 2027."
QTITLE = "Request for proposal for the appointment of a cargo GSSA in Ethiopia. Rift Example Air. Reference REA-CGO-2027-17."
QCONF = "Rift Example Air invites proposals for cargo sales representation in Ethiopia. Reference REA-GSA-2027-14."
QCONF_B = "Cargo sales are not part of this appointment. Proposals are due on 25 March 2027."
CANNED += [
    ("Cargo sales are excluded from this mandate.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "quote": QEX,
         "fields": {"airline": _f("Rift Example Air", QEX), "country": _f("Ethiopia", QEX), "service": _f("GSSA", QEX), "status": _f("open", QEX_R),
                    "tender_ref": _f("REA-GSA-2027-40", QEX_R), "deadline": _f("2027-03-12", QEX_R)}}]}),
    ("ramp lighting maintenance", {"language": "en", "claims": [
        {"claim_type": "service_tender", "stance": "supports", "quote": QRAMP,
         "fields": {"airline": _f("Rift Example Air", QRAMP), "country": _f("Ethiopia", QRAMP), "service": _f("HANDLING", QRAMP), "status": _f("open", QRAMP),
                    "tender_ref": _f("REA-ENG-2027-3", QRAMP), "deadline": _f("2027-03-30", QRAMP)}}]}),
    ("Reference REA-CGO-2027-17.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "quote": QTITLE,
         "fields": {"airline": _f("Rift Example Air", QTITLE), "country": _f("Ethiopia", QTITLE), "service": _f("GSSA", QTITLE), "status": _f("open", QTITLE),
                    "tender_ref": _f("REA-CGO-2027-17", QTITLE)}}]}),
    ("Cargo sales are not part of this appointment.", {"language": "en", "claims": [
        {"claim_type": "gssa_tender", "stance": "supports", "quote": QCONF,
         "fields": {"airline": _f("Rift Example Air", QCONF), "country": _f("Ethiopia", QCONF), "service": _f("GSSA", QCONF), "status": _f("open", QCONF_B),
                    "tender_ref": _f("REA-GSA-2027-14", QCONF), "deadline": _f("2027-03-25", QCONF_B)}}]}),
]


# Status freshness and publication dates (fixture site /freshness/, fourth instruction of 27 Oct 2026).
QFO = "Kilimanjaro Example Air invites proposals from cargo general sales and service agents for Tanzania. Reference KEA-CGO-2025-31."
QFC = ("Kilimanjaro Example Air request for proposals KEA-CGO-2025-31, cargo general sales and service agent for Tanzania. "
       "Contact for enquiries: commercial office, Dar es Salaam.")
QFF = "Kilimanjaro Example Air invites proposals from cargo general sales and service agents for Tanzania. Reference KEA-CGO-2026-53."
QFP = "Request for proposal: cargo GSSA in Tanzania. Kilimanjaro Example Air. Reference KEA-CGO-2022-4."
QFR = "Kilimanjaro Example Cargo will start a twice-weekly freighter service between Dar es Salaam and Dubai from 4 January 2027."


def _kea(quote: str, ref: str, *, status: bool) -> dict:
    fields = {"airline": _f("Kilimanjaro Example Air", quote), "country": _f("Tanzania", quote), "service": _f("GSSA", quote),
              "tender_ref": _f(ref, quote)}
    if status:
        fields["status"] = _f("open", quote)
    return {"language": "en", "claims": [{"claim_type": "gssa_tender", "stance": "supports", "quote": quote, "fields": fields}]}


CANNED += [
    ("Contact for enquiries: commercial office, Dar es Salaam.", _kea(QFC, "KEA-CGO-2025-31", status=False)),
    ("Reference KEA-CGO-2025-31.", _kea(QFO, "KEA-CGO-2025-31", status=True)),
    ("Reference KEA-CGO-2026-53.", _kea(QFF, "KEA-CGO-2026-53", status=True)),
    ("KEA-CGO-2022-4.", _kea(QFP, "KEA-CGO-2022-4", status=True)),
    ("freighter service between Dar es Salaam and Dubai", {"language": "en", "claims": [
        {"claim_type": "route_launch", "stance": "supports", "quote": QFR,
         "fields": {"airline": _f("Kilimanjaro Example Cargo", QFR), "origin": _f("Tanzania", QFR), "destination": _f("United Arab Emirates", QFR)}}]}),
]


# Status chronology (fixture site /chronology/, fifth instruction of 27 Oct 2026).
def _zea_open(ref: str, deadline_text: str, deadline: str) -> dict:
    q = (f"Zambezi Example Air invites proposals from cargo general sales and service agents for Zambia. Reference {ref}. "
         f"Proposals must be submitted by {deadline_text}.")
    return {"language": "en", "claims": [{"claim_type": "gssa_tender", "stance": "supports", "quote": q, "fields": {
        "airline": _f("Zambezi Example Air", q), "country": _f("Zambia", q), "service": _f("GSSA", q), "status": _f("open", q),
        "tender_ref": _f(ref, q), "deadline": _f(deadline, q)}}]}


def _zea_cancel(ref: str) -> dict:
    q = f"Tender {ref} (cargo GSSA, Zambia, Zambezi Example Air) has been cancelled."
    return {"language": "en", "claims": [{"claim_type": "tender_status", "stance": "supports", "quote": q, "fields": {
        "airline": _f("Zambezi Example Air", q), "tender_ref": _f(ref, q), "status": _f("cancelled", q)}}]}


CANNED += [
    ("Tender ZEA-CGO-2026-61 (cargo GSSA", _zea_cancel("ZEA-CGO-2026-61")),
    ("Tender ZEA-CGO-2026-65 (cargo GSSA", _zea_cancel("ZEA-CGO-2026-65")),
    ("Reference ZEA-CGO-2026-61.", _zea_open("ZEA-CGO-2026-61", "20 January 2027", "2027-01-20")),
    ("Reference ZEA-CGO-2026-65.", _zea_open("ZEA-CGO-2026-65", "15 December 2026", "2026-12-15")),
]


# Relationship-intelligence journey (fixture site /people/ and /people-later/, 28 Oct 2026).
QSK = ("Savanna Example Air invites proposals from cargo general sales and service agents for Kenya. Reference SEA-CGO-2026-81. "
       "Proposals must be submitted by 15 March 2027.")
QSU = ("Savanna Example Air invites proposals from cargo general sales and service agents for Uganda. Reference SEA-CGO-2026-82. "
       "Proposals must be submitted by 22 March 2027.")
QSR = "Savanna Example Air will start a twice-weekly freighter service between Nairobi and Dubai from 5 January 2027"
QSC = "Tender SEA-CGO-2026-81 (cargo GSSA, Kenya, Savanna Example Air) has been cancelled."


def _sea(quote: str, ref: str, country: str, deadline: str) -> dict:
    return {"language": "en", "claims": [{"claim_type": "gssa_tender", "stance": "supports", "quote": quote, "fields": {
        "airline": _f("Savanna Example Air", quote), "country": _f(country, quote), "service": _f("GSSA", quote), "status": _f("open", quote),
        "tender_ref": _f(ref, quote), "deadline": _f(deadline, quote)}}]}


CANNED += [
    ("Tender SEA-CGO-2026-81 (cargo GSSA", {"language": "en", "claims": [{"claim_type": "tender_status", "stance": "supports", "quote": QSC,
                                            "fields": {"airline": _f("Savanna Example Air", QSC), "tender_ref": _f("SEA-CGO-2026-81", QSC),
                                                       "status": _f("cancelled", QSC)}}]}),
    ("Reference SEA-CGO-2026-81.", _sea(QSK, "SEA-CGO-2026-81", "Kenya", "2027-03-15")),
    ("Reference SEA-CGO-2026-82.", _sea(QSU, "SEA-CGO-2026-82", "Uganda", "2027-03-22")),
    ("freighter service between Nairobi and Dubai", {"language": "en", "claims": [
        {"claim_type": "route_launch", "stance": "supports", "quote": QSR,
         "fields": {"airline": _f("Savanna Example Air", QSR), "origin": _f("Kenya", QSR), "destination": _f("United Arab Emirates", QSR)}}]}),
]

# SIMULATED replies to the people-reading prompt (app/ai/people.py): the people each fixture document names, with a quote.
PEOPLE_CANNED = [
    ("Contact: Grace Achieng", {"people": [{"name": "Grace Achieng", "role": "Cargo Procurement Manager", "organisation": None,
                                            "quote": "Contact: Grace Achieng, Cargo Procurement Manager."}]}),
    ("Head of Cargo Daniel Mwangi", {"people": [{"name": "Daniel Mwangi", "role": "Head of Cargo", "organisation": "Savanna Example Air",
                                                 "quote": "said Head of Cargo Daniel Mwangi."}]}),
]


class _AIHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []
    delay: float = 0.0          # seconds per call; lets process tests stop a worker mid-extraction

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/messages" or not self.headers.get("x-api-key"):
            return self._json(401 if not self.headers.get("x-api-key") else 404, {"error": "bad request"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        if _AIHandler.delay:
            time.sleep(_AIHandler.delay)
        user = body["messages"][0]["content"]
        m = re.search(r"<document>\n(.*)\n</document>", user, re.S)
        doc = m.group(1) if m else ""
        out: dict = {"language": "en", "claims": []}
        if "the people it explicitly names" in str(body.get("system", "")):
            out = {"people": []}
            for key, response in PEOPLE_CANNED:
                if key in doc:
                    out = response
                    break
        else:
            for key, response in CANNED:
                if key in doc:
                    out = response
                    break
        _AIHandler.calls.append({"model": body.get("model"), "matched": out is not None})
        text = json.dumps(out, ensure_ascii=False)
        return self._json(200, {"id": "msg_fixture", "type": "message", "role": "assistant", "model": body.get("model"),
                                "content": [{"type": "text", "text": text}],
                                "usage": {"input_tokens": max(1, len(user) // 4), "output_tokens": max(1, len(text) // 4)}})

    def _json(self, code: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _Server:
    def __init__(self, handler, port: int = 0):
        # FIXTURE_BIND_HOST=0.0.0.0 only inside the verification containers (tools/docker_substitute/compose.e2e.yml).
        self.httpd = ThreadingHTTPServer((os.environ.get("FIXTURE_BIND_HOST", "127.0.0.1"), port), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def FixtureSite(port: int = 0) -> _Server:  # noqa: N802
    return _Server(_SiteHandler, port)


def FakeAIProvider(port: int = 0, delay: float = 0.0) -> _Server:  # noqa: N802
    _AIHandler.delay = delay
    return _Server(_AIHandler, port)
