"""Freight relevance at the meaning level (27 Oct 2026, second and third instructions).

A representation or service tender enters the freight pipeline only when the notice gives EVIDENCE that the requested work
concerns freight. Keyword presence is not evidence: every cue is read in its clause (`domain.meaning`) and classified as

- REQUIRED   — affirmed, in the clause that states the mandate or the requested work (an invitation, appointment, lot or
               scope sentence) or in the notice's title: "invites proposals for cargo sales representation";
- EXCLUDED   — negated or explicitly excluded: "Cargo sales are excluded from this mandate", "not part of this appointment",
               "excluding cargo", "se excluye la carga", "hors fret";
- BACKGROUND — historical, inside a relative clause, or about another subject: "which appointed a cargo GSA in 2019",
               "the airline's cargo business is handled by its own cargo division".

Readings (`Scope`):

- `cargo`        — cargo is required and nowhere excluded;
- `conflicting`  — cargo is required in one passage and excluded in another: a person decides;
- `mixed`        — cargo and passenger are both required ("passenger and cargo sales");
- `passenger`    — passenger work is required and cargo is not: EXCLUDED from the freight pipeline;
- `not_freight`  — cargo is excluded, or the requested work is outside the freight capability scope (no freight service and no
                   cargo requirement: "ramp lighting maintenance", catering, a retail concession): EXCLUDED;
- `unclear`      — generic representation wording ("general sales agents for representation") or freight-capable work without
                   a cargo requirement (ground handling, trucking with no stated goods): pending review.

Broad cues that are not evidence on their own were removed: "ramp", "loading", "tonnes", "mail", "courier", bare service
abbreviations (RFS, TCM, CSA, ULD). Only cues that name freight itself count (cargo, freight, freighter, air waybill, GSSA /
general sales and service agent, road feeder, total cargo management, fret, carga aérea, Luftfracht ...).

The reading never comes from the extractor's label; a reviewer's correction replaces it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from . import meaning
from .meaning import ascii_text

Scope = Literal["cargo", "passenger", "mixed", "unclear", "not_freight", "conflicting"]
EXCLUDED_SCOPES = ("passenger", "not_freight")
REVIEW_SCOPES = ("mixed", "unclear", "conflicting")

CARGO_CUES: tuple[str, ...] = (
    r"\bcargo\b", r"\bfreight\b", r"\bfreighters?\b", r"\bair ?waybills?\b", r"\bgssas?\b",
    r"\bgeneral sales (?:and|&) service agents?\b", r"\bcargo sales agents?\b", r"\broad feeder\b", r"\btotal cargo management\b",
    r"\bperishables? (?:cargo|shipments?)\b", r"\bbellyhold\b",
    # French, Spanish, Portuguese, German
    r"\bfret\b", r"\bmarchandises\b", r"\bcarga aerea\b", r"\bcarga\b", r"\bmercancias\b", r"\bfracht\b", r"\bluftfracht\b",
)
PASSENGER_CUES: tuple[str, ...] = (
    r"\bpassengers?\b", r"\bpax\b", r"\bticketing\b", r"\bbsp\b", r"\btravel (?:business|agents?|agency|agencies|trade)\b",
    r"\bpublic service obligations?\b", r"\bcheck-?in\b", r"\bbaggage\b", r"\bin-?flight\b", r"\bfrequent flyer\b",
    r"\bpassagers?\b", r"\bbilletterie\b", r"\bbagages?\b", r"\bobligations? de service public\b", r"\bpasajeros?\b", r"\bbilletes?\b",
    r"\bequipajes?\b", r"\bobligaciones? de servicio publico\b", r"\bpassageiros?\b", r"\bpassagiere?\b",
)
# Passenger-side tasks that are also part of ordinary ground handling: with a freight-capable service stated they do not make the
# mandate passenger-only (an airport's handling categories list baggage next to aircraft loading).
WEAK_PASSENGER = {"baggage", "bagages", "bagage", "equipaje", "equipajes", "check-in", "checkin"}
# Wording that excludes cargo from the mandate, in either order ("cargo ... excluded", "excluding cargo").
_EXCL_AFTER = re.compile(r"^[^.;]{0,60}?\b(?:(?:is|are|will be|shall be)\s+(?:expressly\s+|specifically\s+)?(?:excluded|not (?:part of|included|covered|within|in scope)|"
                         r"outside (?:the )?scope|out of scope)|(?:does|do) not (?:form part|apply)|excluded from|is not covered|not included|"
                         r"queda(?:n)? excluid|est(?:a|an) excluid|no (?:esta|estan) incluid|est exclu|sont exclu|n'est pas (?:inclus|compris)|ausgenommen)", re.I)
_EXCL_BEFORE = re.compile(r"\b(?:excluding|except(?: for)?|other than|apart from|without|not including|no|non-|hors|a l'exclusion d(?:u|e la|es)|sauf|"
                          r"se excluye(?:n)?(?: la| el| los| las)?|excepto|salvo|sin|ohne)\s*(?:the\s+|any\s+|la\s+|el\s+|le\s+)?$", re.I)
# Clauses that state the mandate or the requested work.
_MANDATE = re.compile(r"\b(?:invit\w*|seek\w*|request(?:s|ed)? for|rfp|rfq|tender\w*|bids?|proposals?|quotations?|offers?|appoint\w*|"
                      r"mandate|scope|lot\s*\w+|schedule\s*\w+|services? (?:required|include)|requir\w*|procure\w*|expressions? of interest|eoi|"
                      r"agents? (?:for|to)|represent\w*|selection|select\w*|concession|licen[cs]e|"
                      r"appel|consultation|recherche|selection|convoca\w*|licitaci\w*|solicita\w*|concurso|propuestas?|ofertas?|ausschreib\w*|"
                      r"requested|sought|needed|wanted|required|requier\w*|necesita\w*|contrata\w*|busca\w*|cherche\w*|demande\w*|procura\w*|requer\w*)\b", re.I)
_GENERIC_REP = (r"\bgsas?\b", r"\bgeneral sales agents?\b", r"\bsales agents?\b", r"\brepresentation\b", r"\bagentes? generales? de ventas?\b",
                r"\bagents? generaux de vente\b")
# Freight-capable services: their presence makes an unclear reading pending review rather than outside the freight scope.
FREIGHT_CAPABLE_SERVICES = {"GSSA", "TCM", "HANDLING", "TRUCKING", "DATA_PROCESSING", "ACCOUNTING", "INVOICING", "COLLECTIONS",
                            "TRAINING", "TECHNOLOGY"}
SCOPED_TYPES = {"gssa_tender", "service_tender", "tcm_signal", "representation_change"}


@dataclass(frozen=True)
class Cue:
    word: str
    kind: Literal["required", "excluded", "background"]
    where: str            # 'title' or 'passage' or 'document'
    sentence: str


@dataclass(frozen=True)
class FreightScope:
    scope: Scope
    reason: str
    cargo_cues: tuple[str, ...] = field(default_factory=tuple)
    passenger_cues: tuple[str, ...] = field(default_factory=tuple)
    cues: tuple[Cue, ...] = field(default_factory=tuple)

    @property
    def support(self) -> str:
        if self.scope == "cargo":
            return "supported"
        if self.scope in EXCLUDED_SCOPES:
            return "unsupported"
        return "review_required"


def _sentences(text: str) -> list[str]:
    return meaning._sentences(text) if text else []


def _relative_spans(sent: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r",\s*(?:which|who|whose|that|where)\b[^,;.]{1,140}(?:,|$)", sent, re.I)] + \
           [(m.start(), m.end()) for m in re.finditer(r"\((?:[^()]{0,120})\)", sent) if not re.search(r"\b(?:lot|schedule)\b", m.group(0), re.I)]


def _classify(sent: str, start: int, end: int, where: str, reference_year: int | None) -> Literal["required", "excluded", "background"]:
    explicit = bool(_EXCL_AFTER.search(sent[end:end + 90]) or _EXCL_BEFORE.search(sent[max(0, start - 40):start]))
    # Background first: a cue about another subject or another time cannot exclude or require anything.
    if any(a <= start < b for a, b in _relative_spans(sent)) or meaning.refers_to_other_process(sent, start):
        return "background"
    if re.search(r"\b(?:its|their|the airline'?s|the carrier'?s|our)\s+(?:own\s+)?(?:\w+\s+)?$", sent[max(0, start - 30):start], re.I):
        return "background"
    if explicit:
        return "excluded"
    pol = meaning.polarity(sent, start, reference_year=reference_year, end=end)
    if pol == "historical":
        return "background"
    if where == "document":
        return "background"          # outside the mandate's passage only an explicit exclusion counts
    if pol == "negated":
        return "excluded"
    if where == "title":
        return "required"
    # A row of a tender listing ("subject | reference | category | dates") names the requested work in its first cell.
    if " | " in sent and "|" not in sent[:start]:
        return "required"
    # The cue must sit in a clause that states the mandate or the requested work.
    clause = meaning.clause_at(sent, start)
    if not _MANDATE.search(clause):
        return "background"
    return "required"


def _cues(patterns: tuple[str, ...], text: str, where: str, reference_year: int | None) -> list[Cue]:
    out: list[Cue] = []
    for sent in _sentences(ascii_text(text)):
        low = sent.lower()
        for p in patterns:
            for m in re.finditer(p, low):
                out.append(Cue(m.group(0), _classify(sent, m.start(), m.end(), where, reference_year), where, sent[:200]))
    return out


def freight_scope(claim_type: str, service_code: str | None, quote: str, title: str | None = None, *,
                  document: str | None = None, service_supported: bool = True, reference_year: int | None = None) -> FreightScope:
    """The freight reading of a mandate, from the passage that states it, the notice's title and (for exclusions stated
    elsewhere) the whole document."""
    title_cargo = _cues(CARGO_CUES, title or "", "title", reference_year)
    title_pax = _cues(PASSENGER_CUES, title or "", "title", reference_year)
    pas_cargo = _cues(CARGO_CUES, quote or "", "passage", reference_year)
    pas_pax = _cues(PASSENGER_CUES, quote or "", "passage", reference_year)
    # Exclusions anywhere in the document apply to the whole mandate (a lot line for passengers is not an exclusion of cargo).
    doc_excl = [c for c in _cues(CARGO_CUES, document or "", "document", reference_year) if c.kind == "excluded"] if document else []
    cargo = title_cargo + pas_cargo
    pax = title_pax + pas_pax
    req_c = sorted({c.word for c in cargo if c.kind == "required"})
    exc_c = sorted({c.word for c in cargo + doc_excl if c.kind == "excluded"})
    bg_c = sorted({c.word for c in cargo if c.kind == "background"})
    req_p = sorted({c.word for c in pax if c.kind == "required"})
    all_cues = tuple(cargo + pax + doc_excl)
    # A passenger-only TITLE does not override a passage that requires cargo (a lot inside a mixed notice), and vice versa.
    if req_c and exc_c:
        return FreightScope("conflicting", f"the notice both requires cargo ({', '.join(req_c)}) and excludes it ({', '.join(exc_c)}): "
                                           "a reviewer must say whether the freight part is in scope", tuple(req_c), tuple(req_p), all_cues)
    if req_c and req_p:
        passage_c = {c.word for c in pas_cargo if c.kind == "required"}
        passage_p = {c.word for c in pas_pax if c.kind == "required"}
        if passage_c and not passage_p:
            return FreightScope("cargo", f"cargo required by the passage ({', '.join(sorted(passage_c))}); passenger wording only in the title",
                                tuple(req_c), tuple(req_p), all_cues)
        if passage_p and not passage_c:
            return FreightScope("passenger", f"passenger work required by the passage ({', '.join(sorted(passage_p))}); cargo wording only in the "
                                             "title: excluded from the freight pipeline", (), tuple(req_p), all_cues)
        return FreightScope("mixed", f"the mandate requires both cargo ({', '.join(req_c)}) and passenger ({', '.join(req_p)}) work: "
                                     "a reviewer must say whether the freight part is a real opportunity", tuple(req_c), tuple(req_p), all_cues)
    if req_c:
        note = f"; background cargo wording ignored ({', '.join(bg_c)})" if bg_c and set(bg_c) - set(req_c) else ""
        return FreightScope("cargo", f"cargo required by the mandate ({', '.join(req_c)}){note}", tuple(req_c), (), all_cues)
    svc_u = (service_code or "").upper()
    if req_p and set(req_p) <= WEAK_PASSENGER and service_supported and svc_u in FREIGHT_CAPABLE_SERVICES and not exc_c:
        return FreightScope("unclear", f"a {svc_u.lower().replace('_', ' ')} service is requested and its tasks include passenger-side work "
                                       f"({', '.join(req_p)}) but no cargo requirement is stated: pending review", (), tuple(req_p), all_cues)
    if req_p:
        bg = f"; cargo wording only as background ({', '.join(bg_c)})" if bg_c else ""
        ex = f"; cargo excluded ({', '.join(exc_c)})" if exc_c else ""
        return FreightScope("passenger", f"passenger work required ({', '.join(req_p)}) and no cargo requirement{bg}{ex}: excluded from the freight "
                                         "pipeline", (), tuple(req_p), all_cues)
    if exc_c:
        return FreightScope("not_freight", f"cargo is excluded from the mandate ({', '.join(exc_c)}): excluded from the freight pipeline",
                            (), (), all_cues)
    svc = (service_code or "").upper()
    generic = [m.group(0) for p in _GENERIC_REP for m in [re.search(p, ascii_text(f"{title or ''} {quote or ''}").lower())] if m]
    if generic or claim_type in ("gssa_tender", "tcm_signal", "representation_change"):
        what = f"generic representation wording ({', '.join(sorted(set(generic)))})" if generic else "a representation mandate"
        return FreightScope("unclear", f"{what} with neither a cargo nor a passenger requirement stated: freight relevance not established; "
                                       "pending review" + (f" (cargo wording only as background: {', '.join(bg_c)})" if bg_c else ""), (), (), all_cues)
    if svc in FREIGHT_CAPABLE_SERVICES and service_supported:
        return FreightScope("unclear", f"a {svc.lower().replace('_', ' ')} service within the capability scope is requested, but the notice does not "
                                       "say it concerns freight: pending review", (), (), all_cues)
    return FreightScope("not_freight", "no freight service within the capability scope and no cargo requirement is stated (the requested work is "
                                       "outside the freight scope): excluded from the freight pipeline", (), (), all_cues)


def combine(scopes: list[str]) -> Scope:
    """One reading for a signal from the readings of its live anchor claims."""
    s = set(scopes)
    if "conflicting" in s:
        return "conflicting"
    if "mixed" in s or ({"cargo", "passenger"} <= s):
        return "mixed"
    if "cargo" in s and s & {"not_freight"}:
        return "conflicting"
    if "cargo" in s:
        return "cargo"
    if s and s <= {"passenger"}:
        return "passenger"
    if s and s <= {"not_freight", "passenger"}:
        return "not_freight" if "not_freight" in s else "passenger"
    return "unclear"
