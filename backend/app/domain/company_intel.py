"""Company intelligence rules (29 Oct 2026: research purposes beyond tenders). Framework-free.

1. Supplied datasets. A station's GSA list (the BRU example: sheets "GSA | BRU" and "AIRLINE | BRU") is read into organisations,
   their represented airlines and published addresses, every one marked SUPPLIED: awaiting verification against current sources.
   Nothing supplied is shown as current until a person verifies it or research sources it.
2. Organisations named in public text: company names with a legal or trade suffix, or known organisation names, with the sentence
   that names them; published e-mail addresses with the sentence around them; represented-airline statements ("GSA for X, Y and Z",
   "represents ...", lists of designators) bound to the organisation the sentence is about. A passenger-sales mandate (GSA for
   passenger sales / ticketing) is kept apart from cargo representation.
3. Queries for the research purposes: companies, people and market intelligence, from a plain-language brief plus geography,
   airport and the nine capability areas.
4. Relevance of a company to a brief, every point explained.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..reference.airline_codes import resolve, split_codes
from ..reference.airports import airport

# ------------------------------------------------------------------ 1. supplied datasets
KIND_LABELS = {"airline": "Airline", "forwarder": "Freight forwarder", "gssa": "GSA / GSSA (cargo sales agent)", "airport_operator": "Airport operator",
               "trucking_provider": "Trucking / road feeder", "shipper": "Shipper", "handler": "Ground or cargo handler",
               "technology_provider": "Technology provider", "charter_broker": "Charter broker", "integrator": "Integrator",
               "authority": "Authority or regulator", "other": "Other"}
CARRIER_LABELS = {"passenger_belly": "Passenger airline (belly cargo)", "cargo_only": "Cargo-only airline", "combination": "Passenger and freighter",
                  "unknown": "Not established"}
RELATIONSHIP_LABELS = {"cargo_representation": "Cargo representation (GSA/GSSA)", "passenger_representation": "Passenger ticket-sales mandate",
                       "representation_unspecified": "Representation (scope not stated)", "handling": "Handling", "trucking": "Trucking / road feeder",
                       "partnership": "Partnership", "parent": "Parent or group", "other": "Other"}

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_HEADER_WORDS = {"gsa": "company", "gssa": "company", "agent": "company", "company": "company", "name": "company", "organisation": "company",
                 "organization": "company", "represented airlines": "airlines", "airlines": "airlines", "airline": "airlines",
                 "carrier": "airlines", "carriers": "airlines", "e-mail address": "email", "e-mail": "email", "email": "email",
                 "mail": "email", "type": "type", "website": "website", "phone": "phone", "telephone": "phone", "country": "country",
                 "airport": "airport", "city": "city", "contact": "contact", "notes": "notes", "remarks": "notes"}


@dataclass
class SuppliedRow:
    sheet: str
    row_number: int
    raw: dict[str, Any]
    kind: str                           # gssa | airline
    name: str | None                    # company name (GSA sheet) or airline label (airline sheet)
    airline_codes: list[str]
    emails: list[str]
    carrier_type: str | None            # airline sheet: passenger_belly | cargo_only | None
    notes: list[str] = field(default_factory=list)


@dataclass
class SuppliedDataset:
    airport_iata: str | None
    country: str | None
    rows: list[SuppliedRow]
    skipped: list[str]


def _column_roles(headers: list[str]) -> dict[int, str]:
    roles: dict[int, str] = {}
    for i, h in enumerate(headers):
        key = " ".join(str(h or "").strip().lower().split())
        if not key:
            continue
        for word, role in _HEADER_WORDS.items():
            if key == word or key.startswith(word):
                roles.setdefault(i, role)
                break
    return roles


def _airport_from(names: Iterable[str]) -> str | None:
    for n in names:
        for tok in re.findall(r"\b[A-Z]{3}\b", str(n or "")):
            if airport(tok):
                return tok
    return None


def parse_supplied_sheets(sheets: dict[str, list[list[Any]]], *, filename: str | None = None) -> SuppliedDataset:
    """Reads BRU-style sheets: a company sheet (company | represented airlines | e-mail) and an airline sheet (type | airline code(s) |
    e-mail). Column roles are read from the header row; sheets without a recognisable header are skipped and listed."""
    code = _airport_from(list(sheets) + ([filename] if filename else []))
    country = airport(code)[2] if code and airport(code) else None
    rows: list[SuppliedRow] = []
    skipped: list[str] = []
    for sheet, data in sheets.items():
        if not data:
            skipped.append(f"{sheet}: empty")
            continue
        header = [str(c or "") for c in data[0]]
        roles = _column_roles(header)
        role_set = set(roles.values())
        if "company" in role_set:
            kind = "gssa"
        elif "airlines" in role_set and ("type" in role_set or "email" in role_set):
            kind = "airline"
        else:
            skipped.append(f"{sheet}: no recognisable header (found: {', '.join(h for h in header if h) or 'nothing'})")
            continue
        for n, r in enumerate(data[1:], start=2):
            cells = {header[i] if i < len(header) and header[i] else f"col{i + 1}": ("" if v is None else str(v).strip()) for i, v in enumerate(r)}
            if not any(cells.values()):
                continue
            by_role = {roles[i]: ("" if r[i] is None else str(r[i]).strip()) for i in roles if i < len(r)}
            emails = [e.lower() for e in _EMAIL.findall(by_role.get("email", ""))]
            codes_text = by_role.get("airlines", "")
            codes = [] if codes_text.strip().upper() == "ALL" else split_codes(codes_text)
            notes = []
            if codes_text.strip().upper() == "ALL":
                notes.append("represented airlines stated as 'ALL' (no list supplied)")
            if by_role.get("email") and not emails:
                notes.append(f"e-mail column not a valid address: {by_role['email']!r}")
            if kind == "gssa":
                name = by_role.get("company") or None
                if not name:
                    skipped.append(f"{sheet} row {n}: no company name")
                    continue
                rows.append(SuppliedRow(sheet, n, cells, "gssa", name, codes, emails, None, notes))
            else:
                t = by_role.get("type", "").lower()
                ctype = ("cargo_only" if "cargo" in t and "only" in t else "passenger_belly" if ("passenger" in t or "belly" in t) else None)
                label = codes_text.strip() or None
                if not codes and not label:
                    skipped.append(f"{sheet} row {n}: no airline")
                    continue
                rows.append(SuppliedRow(sheet, n, cells, "airline", label, codes, emails, ctype, notes))
    return SuppliedDataset(code, country, rows, skipped)


def airline_labels(codes: Iterable[str]) -> list[dict[str, str | None]]:
    return [{"code": c, "name": resolve(c)[0], "label": resolve(c)[1]} for c in codes]


# ------------------------------------------------------------------ 2. organisations named in public text
_SUFFIX = (r"(?:NV|SA|BV|BVBA|SRL|SPRL|GmbH|AG|Ltd\.?|Limited|LLC|Inc\.?|Plc|PLC|S\.A\.|S\.p\.A\.|SAS|Pty|Pte|Co\.|Corp\.?|Group|Holding|Holdings|"
           r"Aviation|Airlines|Airways|Air|Cargo|Logistics|Freight|Handling|Services|Forwarding|Express|Trucking|Transport|Airport Authority|"
           r"Airports Company|Airports Authority)")
_NAME_WORD = r"[A-Z][A-Za-z0-9&'’\-]+"
_ORG_RX = re.compile(rf"\b((?:{_NAME_WORD}[ \t]+){{0,4}}{_NAME_WORD}[ \t]+{_SUFFIX}(?:[ \t]+(?:{_SUFFIX}))?)(?![ \t]+[A-Z][a-z])(?=[^A-Za-z0-9]|$)")
_NOT_ORG = {"The", "Our", "This", "These", "All", "New", "General", "Total", "Request", "Terms", "Privacy", "Contact", "About", "Home", "Cookie",
            "Passenger", "Welcome", "Kigali", "Nairobi"}
_KIND_WORDS: list[tuple[str, re.Pattern[str]]] = [
    ("gssa", re.compile(r"\b(GSSA|GSA|general sales (?:and service )?agent|cargo sales agent|cargo representation|represent(?:s|ing|ed)? (?:the )?airline)", re.I)),
    ("handler", re.compile(r"\b(ground handl|cargo handl|handling agent|cargo terminal)", re.I)),
    ("trucking_provider", re.compile(r"\b(road feeder|trucking|haulage|RFS)\b", re.I)),
    ("forwarder", re.compile(r"\b(freight forward|forwarder|logistics provider|customs broker)", re.I)),
    ("charter_broker", re.compile(r"\b(charter broker|air charter)", re.I)),
    ("technology_provider", re.compile(r"\b(cargo management system|booking platform|software|technology provider|digital platform)", re.I)),
    ("integrator", re.compile(r"\b(integrator|express parcel)", re.I)),
    ("airline", re.compile(r"\b(airline|carrier|freighter operator|flag carrier)\b", re.I)),
    ("airport_operator", re.compile(r"\b(airport authority|airport operator|airports company)", re.I)),
]
_REPRESENT = re.compile(r"\b(GSA|GSSA|general sales (?:and service )?agent|sales agent|represent(?:s|ing|ed)?|representation|appointed)\b", re.I)
_REP_PHRASE = re.compile(r"\b(?:GSA|GSSA|general sales (?:and service )?agent|sales agent|represents?|representing|representation|agent)\b"
                         r"(?:[ \t]+(?:for|of))?(?:[ \t]+(?:cargo|passenger|freight|ticket(?:ing)?|sales|and|the|services?))*[ \t]+(?:for|of)[ \t]+"
                         r"((?:[A-Z][A-Za-z0-9&'’\-]*(?:[ \t]+(?:[A-Z][A-Za-z0-9&'’\-]*|and|&|,))*))", re.I)
_PASSENGER = re.compile(r"\b(passenger|ticket(?:ing)?|pax)\b", re.I)
_CARGO = re.compile(r"\b(cargo|freight|airfreight)\b", re.I)
_CODE_LIST = re.compile(r"\b([A-Z0-9]{2}(?:[ \t]*[|/,][ \t]*[A-Z0-9]{2}){2,})\b")
_PHRASE_STOP = re.compile(r"\b(in|at|across|for|with|from|since|effective|covering|and its|on)\b")


@dataclass
class OrgMention:
    name: str
    quote: str
    kind: str | None                         # inferred from the sentence; None when nothing says what it is
    kind_basis: str
    emails: list[str] = field(default_factory=list)
    represented: list[str] = field(default_factory=list)     # airline names or codes as written
    representation_scope: str | None = None                  # cargo | passenger | None
    website_hint: str | None = None
    subject: bool = True                                     # the sentence is about this organisation (first named in it)


_SENT_END = re.compile(r"\.(?=\s|$)|\n")


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = 0
    for m in _SENT_END.finditer(text, 0, start):
        left = m.end()
    m2 = _SENT_END.search(text, end)
    right = m2.end() if m2 else len(text)
    return left, right


def _sentence_around(text: str, start: int, end: int) -> str:
    a, b = _sentence_bounds(text, start, end)
    return " ".join(text[a:b].split())[:400]


def _next_sentence(text: str, end_of_sentence: int) -> str:
    """The sentence after a passage, when it is short: a directory entry's contact line ('Contact: cargo@...')."""
    m = _SENT_END.search(text, end_of_sentence + 1)
    nxt = text[end_of_sentence:(m.end() if m else min(len(text), end_of_sentence + 200))]
    nxt = " ".join(nxt.split())
    return nxt if len(nxt) <= 160 else ""


def _clean_org(raw: str) -> str | None:
    name = " ".join(raw.split()).strip(" ,;:.")
    first = name.split()[0] if name else ""
    if not name or first in _NOT_ORG or len(name) < 4 or len(name.split()) > 7:
        return None
    return name


def _represented_names(sentence: str, subject: str, names_in_sentence: list[str]) -> list[str]:
    """The organisations a representation phrase is about: 'GSSA for X and Y in Rwanda' -> [X, Y] (names that are themselves recognised
    organisations in the sentence, or capitalised names in the phrase up to a stop word)."""
    out: list[str] = []
    for m in _REP_PHRASE.finditer(sentence):
        phrase = m.group(1)
        cut = _PHRASE_STOP.search(phrase)
        phrase = phrase[:cut.start()] if cut else phrase
        for part in re.split(r",|\band\b|&", phrase):
            n = " ".join(part.split()).strip(" ,.")
            if not n or n.lower() == subject.lower() or len(n) < 3 or n in _NOT_ORG:
                continue
            match = next((x for x in names_in_sentence if x.lower() == n.lower() or n.lower().startswith(x.lower()) or x.lower().startswith(n.lower())), None)
            name = match or n
            if name.lower() != subject.lower() and name not in out and re.match(r"[A-Z]", name):
                out.append(name)
    return out


def organisations_in_text(text: str, known: Iterable[str] = (), airline_names: Iterable[str] = ()) -> list[OrgMention]:
    """Organisations named in a passage, with what the passage says about them. Conservative: a name needs a legal or trade suffix,
    or must be a known organisation; the kind, e-mail addresses and represented airlines bind to the SUBJECT of the sentence (the
    organisation named first); an organisation named only as the represented party is recorded as an airline counterparty."""
    known_map = {k.lower(): k for k in known if k and k.strip()}
    airline_map = {a.lower(): a for a in airline_names if a and a.strip()}
    spans: list[tuple[int, int, str]] = [(m.start(1), m.end(1), m.group(1)) for m in _ORG_RX.finditer(text)]
    for k_low, k in list(known_map.items()) + list(airline_map.items()):
        for m in re.finditer(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z0-9])", text):
            spans.append((m.start(), m.end(), k))
    # one span per position: prefer the longest; drop spans inside another
    spans.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    kept: list[tuple[int, int, str]] = []
    for sp in spans:
        if kept and sp[0] < kept[-1][1]:
            continue
        kept.append(sp)
    # group by sentence
    by_sentence: dict[tuple[int, int], list[tuple[int, int, str]]] = {}
    for sp in kept:
        by_sentence.setdefault(_sentence_bounds(text, sp[0], sp[1]), []).append(sp)
    found: dict[str, OrgMention] = {}
    for (a, b), group in by_sentence.items():
        names = []
        for start, end, raw in group:
            name = _clean_org(raw)
            if name:
                names.append(known_map.get(name.lower(), airline_map.get(name.lower(), name)))
        if not names:
            continue
        sentence = " ".join(text[a:b].split())[:400]
        after = _next_sentence(text, b)
        if after and _EMAIL.search(after) and not _ORG_RX.search(after) and not any(k in after.lower() for k in known_map):
            sentence = (sentence + " " + after)[:400]        # a contact line directly after the entry belongs to it
        subject = names[0]
        rest = names[1:]
        kind, basis = None, "the passage does not say what the organisation is"
        head = sentence[: sentence.lower().find(rest[0].lower())] if rest and rest[0].lower() in sentence.lower() else sentence
        for k, rx in _KIND_WORDS:
            if rx.search(head):
                kind, basis = k, f"the sentence says '{rx.search(head).group(0)}'"
                break
        if subject.lower() in airline_map:
            kind, basis = "airline", "a known airline name"
        emails = [e.lower() for e in _EMAIL.findall(sentence)]
        represented: list[str] = []
        scope = None
        if _REPRESENT.search(sentence):
            scope = "passenger" if (_PASSENGER.search(sentence) and not _CARGO.search(sentence)) else ("cargo" if _CARGO.search(sentence) else None)
            represented = _represented_names(sentence, subject, names)
            for m in _CODE_LIST.finditer(sentence):
                represented.extend(c for c in split_codes(m.group(1)) if c not in represented)
        key = subject.lower()
        if key not in found:
            found[key] = OrgMention(subject, sentence, kind, basis, emails, represented, scope)
        else:
            cur = found[key]
            if len(sentence) > len(cur.quote) and (kind or not cur.kind):
                cur.quote = sentence                           # the fuller statement about the organisation (a heading says little)
            cur.emails = cur.emails + [e for e in emails if e not in cur.emails]
            cur.represented = cur.represented + [r for r in represented if r not in cur.represented]
            cur.representation_scope = cur.representation_scope or scope
            if cur.kind is None and kind:
                cur.kind, cur.kind_basis = kind, basis
        for other in rest:
            okey = other.lower()
            is_rep = any(other.lower() == r.lower() for r in represented)
            okind = "airline" if (okey in airline_map or is_rep) else None
            obasis = ("a known airline name" if okey in airline_map else "named as the represented party of a sales agent" if is_rep else
                      "named in the sentence; the passage does not say what the organisation is")
            if okey not in found:
                found[okey] = OrgMention(other, sentence, okind, obasis, [], [], None, None, subject=False)
            elif found[okey].kind is None and okind:
                found[okey].kind, found[okey].kind_basis = okind, obasis
    return list(found.values())


def emails_in_text(text: str, site_host: str | None) -> list[dict[str, str]]:
    """Published e-mail addresses in a page, with the sentence around each and whether the domain is the page's own site."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _EMAIL.finditer(text):
        e = m.group(0).lower()
        if e in seen or e.endswith((".png", ".jpg", ".svg")):
            continue
        seen.add(e)
        domain = e.split("@", 1)[1]
        own = bool(site_host) and (domain == site_host or domain.endswith("." + site_host) or site_host.endswith("." + domain))
        out.append({"email": e, "quote": _sentence_around(text, m.start(), m.end()), "own_site": "yes" if own else "no"})
    return out[:40]


# ------------------------------------------------------------------ 3. queries for the research purposes
@dataclass(frozen=True)
class PurposeQuery:
    purpose: str
    text: str
    country: str | None


_KIND_TERMS = {"gssa": '("GSSA" OR "GSA" OR "cargo sales agent" OR "general sales agent") cargo',
               "airline": '(airline OR "cargo airline" OR freighter) cargo',
               "forwarder": '("freight forwarder" OR "freight forwarding" OR logistics)',
               "handler": '("ground handling" OR "cargo handling" OR "cargo terminal")',
               "trucking_provider": '("road feeder" OR trucking OR haulage) cargo',
               "technology_provider": '("cargo management system" OR "booking platform" OR "cargo software")',
               "charter_broker": '("charter broker" OR "air charter") cargo',
               "integrator": '(integrator OR "express cargo")',
               "airport_operator": '("airport" OR "cargo hub") cargo'}
_AREA_COMPANY_KINDS = {"airline_representation": ["gssa", "airline"], "account_growth": ["airline", "gssa"], "forwarder_sales": ["forwarder"],
                       "capacity_lanes": ["airline", "charter_broker"], "service_operations": ["handler", "airport_operator"],
                       "trucking_gateways": ["trucking_provider", "handler"], "outsourcing_training": ["gssa", "handler"],
                       "technology_solutions": ["technology_provider"], "network_development": ["gssa", "forwarder", "integrator"]}
_MARKET_TERMS = ['("new route" OR launches OR "freighter service" OR "cargo capacity") airline cargo',
                 '(appoints OR appointed OR "new GSSA" OR "representation") cargo',
                 '(investment OR expansion OR "new terminal" OR "cargo hub" OR partnership) air cargo',
                 '("market report" OR outlook OR "cargo volumes" OR demand) air cargo']


def kinds_for(modules: Iterable[str], explicit: Iterable[str] = ()) -> list[str]:
    out = [k for k in explicit if k in _KIND_TERMS]
    for m in modules:
        for k in _AREA_COMPANY_KINDS.get(m, []):
            if k not in out:
                out.append(k)
    return out or ["gssa", "airline", "forwarder", "handler", "trucking_provider"]


def brief_terms(brief: str | None) -> str:
    """The brief's content words, quoted when they form a short phrase."""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", brief or "")
             if w.lower() not in {"find", "identify", "research", "the", "and", "that", "could", "create", "operating", "serving", "relevant",
                                  "providers", "companies", "people", "list", "with", "they", "their", "who", "which", "for", "from", "into"}]
    return " ".join(words[:8])


def build_purpose_queries(*, purpose: str, brief: str | None, countries: list[str | None], country_names: dict[str, str], modules: list[str],
                          kinds: list[str], airport_iata: str | None, organisation: str | None, max_per_country: int = 8) -> list[PurposeQuery]:
    where_parts: list[str] = []
    ap = airport(airport_iata)
    if ap:
        where_parts.append(f'("{ap[0]}" OR {airport_iata.upper()} OR "{ap[1]}")')
    focus = f'"{organisation.strip()}"' if organisation and organisation.strip() else ""
    bt = brief_terms(brief)
    out: list[PurposeQuery] = []
    for c in countries or [None]:
        cn = f' "{country_names.get(c, c)}"' if c else ""
        where = (" " + " ".join(where_parts) if where_parts else "") + cn
        per: list[str] = []
        if bt or focus:
            per.append(" ".join(x for x in (focus, bt, "cargo OR freight OR airline") if x) + where)
        if purpose == "companies":
            for k in kinds:
                per.append(" ".join(x for x in (focus, _KIND_TERMS[k]) if x) + where)
            if "gssa" in kinds or "airline" in kinds:
                per.append(" ".join(x for x in (focus, '("represented airlines" OR "airlines we represent" OR "our principals" OR "GSA for")') if x) + where)
            per.append(" ".join(x for x in (focus, '(directory OR members OR "list of") (GSSA OR "cargo agents" OR forwarders OR handlers)') if x) + where)
        elif purpose == "people":
            roles = '("head of cargo" OR "cargo manager" OR "commercial director" OR "country manager" OR "sales manager" OR "managing director")'
            per.append(" ".join(x for x in (focus, roles, "cargo OR GSSA OR forwarder") if x) + where)
            per.append(" ".join(x for x in (focus, "(appoints OR appointed OR joins OR promoted) cargo") if x) + where)
            per.append(" ".join(x for x in (focus, '("our team" OR "leadership" OR "management team") cargo GSSA OR forwarder') if x) + where)
        elif purpose == "market":
            for t in _MARKET_TERMS:
                per.append(" ".join(x for x in (focus, t) if x) + where)
        seen: set[str] = set()
        for t in per:
            if t.lower() not in seen:
                seen.add(t.lower())
                out.append(PurposeQuery(purpose, t, c))
            if len([q for q in out if q.country == c]) >= max_per_country:
                break
    return out


# ------------------------------------------------------------------ 4. relevance of a company to a brief
def company_relevance(*, kind: str | None, wanted_kinds: list[str], country: str | None, brief_countries: list[str], airport_iata: str | None,
                      brief_airport: str | None, represented: int, emails: int, website: bool, evidence_count: int,
                      brief_terms_hit: bool) -> dict[str, Any]:
    comps = []

    def add(key: str, label: str, pts: int, mx: int, reason: str) -> None:
        comps.append({"key": key, "label": label, "points": pts, "max": mx, "reason": reason})
    if kind and kind in wanted_kinds:
        add("kind", "Kind of organisation", 30, 30, f"{KIND_LABELS.get(kind, kind)}: a kind the brief asks for")
    elif kind:
        add("kind", "Kind of organisation", 10, 30, f"{KIND_LABELS.get(kind, kind)}: not a kind the brief asks for")
    else:
        add("kind", "Kind of organisation", 0, 30, "Kind not established by any source")
    if brief_airport and airport_iata == brief_airport:
        add("geography", "Geography", 25, 25, f"At the airport in the brief ({brief_airport})")
    elif brief_countries and country in brief_countries:
        add("geography", "Geography", 20, 25, "In a country of the brief")
    elif not brief_countries and not brief_airport:
        add("geography", "Geography", 15, 25, "No geography in the brief")
    elif country:
        add("geography", "Geography", 0, 25, "Outside the geography of the brief")
    else:
        add("geography", "Geography", 5, 25, "Country not established")
    add("profile", "Profile completeness", min(20, (8 if website else 0) + min(6, emails * 3) + min(6, represented * 2)), 20,
        f"website {'recorded' if website else 'missing'}; {emails} published address(es); {represented} represented airline(s) or partner(s)")
    add("brief", "Brief terms", 15 if brief_terms_hit else 0, 15, "The source matches the brief's words" if brief_terms_hit else "No match with the brief's words")
    add("evidence", "Evidence", min(10, evidence_count * 3), 10, f"{evidence_count} evidence passage(s)")
    return {"score": sum(c["points"] for c in comps), "components": comps, "rule": "Relevance to the brief, not a commercial judgement"}
