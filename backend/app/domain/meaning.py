"""Meaning checks for claim validation (review of 26 Oct 2026, §1).

Keyword presence is not support. These helpers decide what a clause says
about the thing a keyword or country names:

- `polarity`: does the clause AFFIRM the statement, NEGATE it ("is not
  inviting bids"), report it as HISTORY ("invited bids in 2019",
  "previously"), or announce it as a PLAN ("plans to invite", "will issue
  a tender")? Idioms that contain a negation word but are not negations
  ("no later than", "not less than") are ignored.
- `country_roles`: in which role is a country named? `issuer` (where the
  organisation is headquartered or based), `scope` (where the work is
  delivered: "for Kenya", "in Kenya", "at Mombasa, Kenya"), `origin` /
  `destination` (route ends), `name` (part of an organisation's name,
  e.g. "Kenya Airways"), or `unknown` (named, but the sentence does not say
  why). Unknown is never treated as scope.
- `requirement_stated`: is an eligibility requirement actually stated by
  the quote (its content words and numbers, same polarity)?

Everything here is deliberately conservative: when meaning is ambiguous the
caller reports the field as unsupported, so a person reviews it.

English is fully covered; common French and Spanish cues are included for
local-language notices. Text in other languages without matching cues is
reported as ambiguous rather than guessed.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from ..reference.cities import cities_in_text
from ..reference.geography import country_names

Polarity = Literal["affirmed", "negated", "historical", "planned"]
Role = Literal["issuer", "scope", "origin", "destination", "name", "unknown"]


def ascii_text(s: str) -> str:
    """Accent-free text with typographic quotes/dashes normalised, case kept. Positions in this
    string are what the role analysis works on."""
    s = unicodedata.normalize("NFKC", s).replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch)).replace(" ", " ")


# ---------------------------------------------------------------- clauses and polarity

# A sentence end is a full stop followed by a capital or a digit-free start; abbreviations ("Kshs.", "No.", "Ltd.", "i.e.") and a
# number continuing the clause ("Kshs. 100,000") do not break the clause.
_CLAUSE_BREAK = re.compile(r"(?<=\.)(?<!\bKshs\.)(?<!\bKsh\.)(?<!\bNo\.)(?<!\bNos\.)(?<!\bLtd\.)(?<!\bInc\.)(?<!\bRs\.)(?<!\betc\.)(?<!\bi\.e\.)(?<!\be\.g\.)"
                           r"(?<!\bapprox\.)(?<!\bvs\.)(?<!\bmin\.)(?<!\bmax\.)(?<!\bSt\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)\s+(?-i:(?![0-9a-z]))|(?<=[;!?])\s+"
                           r"|\s+(?:but|however|whereas|while|although|mais|pero|sin embargo)\s+|\n+", re.I)


def clause_at(text: str, pos: int) -> str:
    """The clause of `text` that contains character position `pos`."""
    start = 0
    for m in _CLAUSE_BREAK.finditer(text):
        if m.start() >= pos:
            return text[start:m.start()]
        start = m.end()
    return text[start:]


# Phrases that contain a negation word without negating the statement.
_NOT_NEGATION = re.compile(r"\b(no later than|not later than|no less than|not less than|no more than|not more than|"
                           r"no earlier than|not before|no objection|non-refundable|not exceeding|no\.\s*\d+|number|nos?\.)", re.I)
_NEGATION = re.compile(r"\b(not|no|never|none|neither|nor|without|no longer|declined? to|has no plans?|have no plans?|ruled out|"
                       r"denied|denies|refuted|is not|are not|isn't|aren't|wasn't|weren't|won't|doesn't|don't|didn't|cannot|can't|"
                       r"excluding|except|other than|untrue|false that|incorrect|inaccurate|"
                       r"ne\b[^.]{0,40}?\bpas|n'[a-z]+\b[^.]{0,30}?\bpas|aucun|aucune|jamais|ningun|ninguna|nunca|sin)\b|n't\b", re.I)
_HISTORICAL = re.compile(r"\b(previously|formerly|in the past|back in|last (year|month|week|quarter)|ago|had (invited|issued|launched|"
                         r"sought|appointed|awarded|opened|closed|tendered)|was (launched|issued|opened|awarded|closed|held)|"
                         r"were invited|ran from|historically|former|precedent|anteriormente|en el pasado|auparavant)\b", re.I)
_PLANNED = re.compile(r"\b(reserves? the right to|reserve the right to|entitled to|at its (?:sole )?discretion|without (?:any )?obligation|"
                      r"may (?:at any time |at its discretion )?(?:annul|cancel|withdraw|reject|terminate|suspend|amend|extend|modify)|"
                      r"se r[ée]serve le droit|se reserva el derecho|"
                      r"plans? to|planning to|intends? to|intention to|expects? to|is expected to|are expected to|"
                      r"is considering|are considering|considering whether|may (issue|launch|invite|tender|seek|open)|"
                      r"could (issue|launch|invite|tender|seek|open)|will (issue|launch|invite|tender|seek|open|publish)|"
                      r"to be (issued|launched|published|opened)|upcoming|forthcoming|later this year|in due course|"
                      r"is preparing to|are preparing to|prevoit de|prevu|tiene previsto|planea|sera\b|seront\b|ser[áa]n?\b)\b", re.I)
_RESERVED_RIGHT = re.compile(r"\b(?:reserves? the right|entitled to|at its (?:sole )?discretion|se r[ée]serve le droit|se reserva el derecho)\b", re.I)
# A year inside a reference code ("EXA-CGO-2025-31", "RFP/2019/04") is part of an identifier, not a date of the event.
_YEAR = re.compile(r"(?<![A-Za-z0-9][-/_])\b(19[5-9]\d|20\d\d)\b")


# Negation-like wording that does NOT negate the opportunity (amendments of 26 Oct 2026, item 2): it negates a fee,
# a charge or another detail of the process. Neutralised (replaced by spaces, offsets kept) before polarity is read.
_BENIGN = re.compile(
    r"\b(?:no|without|not\s+any|free\s+of)\s+(?:an?\s+|any\s+)?(?:(?:application|registration|tender|bid|bidding|participation|entry|"
    r"submission|document(?:ation)?|processing|administration|admin|joining|access|tender\s+document)\s+)?"
    r"(?:fees?|charges?|costs?|deposits?|payments?|bonds?|guarantees?|security|commission)\b"
    r"|\bfree\s+of\s+charge\b|\bat\s+no\s+(?:cost|charge)\b|\bnon-?(?:refundable|exclusive|binding|mandatory)\b"
    r"|\bnot\s+(?:limited|restricted)\s+to\b|\bnot\s+only\b|\bwithout\s+(?:obligation|prejudice|limitation)\b"
    r"|\bno\s+(?:site\s+visit|pre-?bid\s+(?:meeting|conference))\b[^.;,]{0,20}|\bno\s+(?:prior|previous)\s+(?:registration|experience\s+with\s+us)\b"
    r"|\bsans\s+frais\b|\bgratuit\w*|\bsin\s+costo\b|\bgratuit[oa]s?\b", re.I)

# References to ANOTHER process (an older framework agreement, the previous contract, an earlier tender). Wording inside
# them (years, "expired", "former", "cancelled") describes that other process, not the current opportunity.
_OTHER_PROCESS = re.compile(
    # an earlier contract / agreement / appointment (including the incumbent's current one, which the new process replaces)
    r"\b(?:the\s+|an?\s+|its\s+|their\s+)?(?:(?:19|20)\d\d\s+|\d{4}[-/]\d{2,4}\s+)?(?:previous|prior|earlier|former|old(?:er)?|existing|current|"
    r"expired|expiring|incumbent|last|original)\s+(?:\w+\s+){0,3}?(?:framework\s+)?(?:agreements?|contracts?|mandates?|frameworks?|"
    r"appointments?|arrangements?|provider|agent)\b(?:[^.;]{0,60}?(?:(?:19|20)\d\d|expired|ended|cancelled|"
    r"awarded|closed|signed|terminated))?"
    # an earlier TENDER: only when it is explicitly earlier (never "the current tender" / "the existing tender")
    r"|\b(?:the\s+|an?\s+|its\s+)?(?:(?:19|20)\d\d\s+)?(?:previous|prior|earlier|former|old(?:er)?|last|original)\s+(?:\w+\s+){0,2}?"
    r"(?:tenders?|rfps?|rfqs?|procurement|process(?:es)?|round)\b(?:[^.;]{0,60}?(?:(?:19|20)\d\d|expired|ended|cancelled|awarded|closed|terminated))?"
    r"|\b(?:(?:19|20)\d\d)\s+(?:tender|rfp|rfq|procurement|process|round)\b[^.;]{0,40}"
    r"|\b(?:framework\s+agreements?|frame\s+contracts?)\b(?:\s+(?:signed|awarded|concluded|dated|of|from|in|since|that|which|expiring|"
    r"expired|ending|valid)\b[^.;]{0,50})?"
    r"|\b(?:replac(?:es|ing|e)|succeed(?:s|ing)|supersed(?:es|ing))\b[^.;]{0,80}"
    r"|\b(?:under|pursuant\s+to)\s+(?:the\s+)?(?:(?:19|20)\d\d\s+)?(?:framework|agreement|contract)\b[^.;,]{0,40}", re.I)

_PRE_WINDOW = 8      # tokens before the keyword that can negate / date / plan it
_POST_WINDOW = 10    # tokens after it
# Relative clauses describe something else ("Kenya Airways, which has no plans to exit Uganda, invites ...").
_RELATIVE = re.compile(r",\s*(?:which|who|whose|that)\b[^,;.]{1,120},", re.I)
_DENIAL = re.compile(r"\b(untrue|false that|incorrect|inaccurate|denied|denies|refuted|ruled out|has no plans?|have no plans?|"
                     r"no plans? to|declined? to|it is not true)\b", re.I)
# After the keyword: a negated verb within three words, unless a relative pronoun intervenes ("GSSAs that are not ...").
_TOK = r"(?:\s*(?!(?:that|who|which|whose)\b)\S+)"
_POST_NEGATION = re.compile(r"^" + _TOK + r"{0,3}?\s*\b(?:is|are|was|were|has|have|had|will|shall|would|does|do|did|can|could|may)\s+"
                            r"(?:\w+\s+)?(?:not|never|no\s+longer)\b|^" + _TOK + r"{0,3}?\s*\w+n't\b|^" + _TOK + r"{0,2}?\s*\bno\s+longer\b", re.I)


# Clause-final denials of the whole statement: "... from 3 November is no longer the plan", "... has been scrapped".
_CLAUSE_DENIAL_AFTER = re.compile(r"\b(?:is|are|was|were|has been|have been)\s+(?:no longer|not)\s+(?:the plan|planned|going ahead|happening|"
                                  r"proceeding|true|the case|on|valid|going to happen)\b|\b(?:scrapped|shelved|abandoned|called off|"
                                  r"postponed indefinitely|indefinitely postponed)\b", re.I)


def _blank(m: re.Match[str]) -> str:
    return " " * (m.end() - m.start())


# "The closing date, previously 12 March 2027, is now 26 March 2027": the parenthetical names the OLD value; it does not make the
# clause historical.
_OLD_VALUE_ASIDE = re.compile(r",\s*(?:previously|formerly|originally|initially)\s+[^,;.]{1,40},", re.I)


def _neutralise(clause: str) -> str:
    """Benign negations and references to other processes become spaces (same length, so offsets hold)."""
    return _RELATIVE.sub(_blank, _OTHER_PROCESS.sub(_blank, _BENIGN.sub(_blank, _NOT_NEGATION.sub(_blank, _OLD_VALUE_ASIDE.sub(_blank, clause)))))


def _clause_span(text: str, pos: int) -> tuple[int, int]:
    start = 0
    for m in _CLAUSE_BREAK.finditer(text):
        if m.start() >= pos:
            return start, m.start()
        start = m.end()
    return start, len(text)


def _last_tokens(s: str, n: int) -> str:
    toks = list(re.finditer(r"\S+", s))
    return s[toks[-n].start():] if len(toks) > n else s


def _first_tokens(s: str, n: int) -> str:
    toks = list(re.finditer(r"\S+", s))
    return s[: toks[n - 1].end()] if len(toks) >= n else s


def polarity(text: str, pos: int, *, reference_year: int | None = None, end: int | None = None) -> Polarity:
    """What the text says about the event named at `pos` (to `end`, the end of the keyword): affirmed, negated,
    historical or planned.

    Only wording ATTACHED to that event counts (amendments of 26 Oct 2026, item 2):
    - before it: a negation, date, past or plan marker within the preceding few words ("is not inviting",
      "In 2019 ... invited", "plans to invite"), or a denial anywhere earlier in the clause ("It is untrue that");
    - after it: a negated verb ("the tender is not open", "has not been cancelled"), a past date or past-tense
      marker within the following few words, up to the start of a reference to another process.
    Negations of details ("no application fee", "without charge") and references to other processes ("replacing
    the framework agreement signed in 2019", "the previous contract expired") are neutralised first."""
    t = ascii_text(text)
    a, b = _clause_span(t, pos)
    clause = _neutralise(t[a:b])
    rel = pos - a
    rel_end = (end - a) if end is not None else rel + len((re.match(r"\S*", clause[rel:]) or [""])[0])
    before, after = clause[:rel], clause[max(rel_end, rel):]
    pre = _last_tokens(before, _PRE_WINDOW)
    post = _first_tokens(after, _POST_WINDOW)
    if _DENIAL.search(_last_tokens(before, 14)) or _NEGATION.search(pre):
        return "negated"
    if _POST_NEGATION.search(post) or _CLAUSE_DENIAL_AFTER.search(after):
        return "negated"
    if _HISTORICAL.search(pre) or _HISTORICAL.search(post):
        return "historical"
    if reference_year is not None:
        years = [int(y) for y in _YEAR.findall(pre + " " + post)]
        if years and max(years) < reference_year:
            return "historical"
    if _PLANNED.search(pre) or _PLANNED.search(post):
        return "planned"
    # A reserved right anywhere earlier in the clause governs everything it lists ("reserves the right to accept or reject
    # any Tender, and to annul the Tendering process"): a possibility, not an event.
    if _RESERVED_RIGHT.search(before):
        return "planned"
    return "affirmed"


def refers_to_other_process(text: str, pos: int) -> bool:
    """True when the wording at `pos` sits inside a reference to another process (older framework agreement,
    previous contract, earlier tender)."""
    t = ascii_text(text)
    a, b = _clause_span(t, pos)
    clause = t[a:b]
    rel = pos - a
    return any(m.start() <= rel < m.end() for m in _OTHER_PROCESS.finditer(clause))


def locate(quote: str, document: str) -> int | None:
    """Start of `quote` inside `document` (whitespace- and case-insensitive), in ascii_text(document) coordinates."""
    words = re.findall(r"\S+", ascii_text(quote))
    if not words:
        return None
    m = re.search(r"\s+".join(re.escape(w) for w in words), ascii_text(document), re.I)
    return m.start() if m else None


def polarity_in_context(quote: str, offset: int, document: str | None, *, reference_year: int | None = None,
                        length: int | None = None) -> Polarity:
    """Polarity of position `offset` in `quote`, read in the DOCUMENT clause around the quote, so wording just
    outside the extracted fragment ("... is no longer the plan", "It is untrue that ...") is not lost.
    Falls back to the quote alone if the quote cannot be located."""
    if document:
        at = locate(quote, document)
        if at is not None:
            doc_pol = polarity(document, at + offset, reference_year=reference_year,
                               end=at + offset + length if length is not None else None)
            quote_pol = polarity(quote, offset, reference_year=reference_year, end=offset + length if length is not None else None)
            # the stronger reading wins: a negation or past/plan marker in either is kept
            for p in ("negated", "historical", "planned"):
                if p in (doc_pol, quote_pol):
                    return p  # type: ignore[return-value]
            return "affirmed"
    return polarity(quote, offset, reference_year=reference_year, end=offset + length if length is not None else None)


def first_match(patterns: tuple[str, ...], text: str) -> re.Match[str] | None:
    """Earliest match of any pattern in the (accent-folded, lower-cased) text."""
    t = ascii_text(text).lower()
    best: re.Match[str] | None = None
    for p in patterns:
        m = re.search(p, t)
        if m and (best is None or m.start() < best.start()):
            best = m
    return best


def affirmed_matches(patterns: tuple[str, ...], text: str, *, reference_year: int | None = None,
                     document: str | None = None) -> list[re.Match[str]]:
    """Every match whose clause affirms it (not negated, not historical, not planned), read in the document's context."""
    t = ascii_text(text).lower()
    out = []
    for p in patterns:
        for m in re.finditer(p, t):
            if refers_to_other_process(text, m.start()):
                continue           # "the earlier tender was cancelled" describes another process
            if polarity_in_context(text, m.start(), document, reference_year=reference_year, length=m.end() - m.start()) == "affirmed":
                out.append(m)
    return out


# ---------------------------------------------------------------- geography roles

_ISSUER_BEFORE = re.compile(r"(headquartered|headquarters|head office|based|registered|domiciled|incorporated|"
                            r"basee?|siege|con sede|sede|domiciliada)\s+(?:is\s+|are\s+)?(?:in|at|en|a|au|aux)\s+(?:the\s+)?$", re.I)
_ISSUER_AFTER = re.compile(r"^(?:-|\s)?(based|registered|headquartered|incorporated)\b|^'s\s+(national|flag)\s+carrier", re.I)
_NAME_AFTER = re.compile(r"^\s*(airways|airlines|air\b|aviation|cargo|airport|international airways|national airlines)", re.I)
_SCOPE_PREP = {"in", "for", "at", "across", "within", "covering", "serving", "throughout", "into", "inside", "en", "au", "aux", "pour",
               "em", "no", "na", "nos", "nas", "im", "nach", "für", "fur",
               "dans", "para", "sur", "over", "a"}      # "a" = French/Spanish "à"/"a" after accent folding
_ORIGIN_PREP = {"from", "ex", "depuis", "desde"}
# Walked over on the way back to the governing word: articles, connectives and place descriptors ("the airport of", "l'aéroport de",
# "aeropuerto de"), so "à l'aéroport de Casablanca, Maroc" still reaches "à".
_SKIPPABLE = {"the", "and", ",", "-", "(", ")", "of", "du", "de", "des", "la", "le", "les", "l'", "el", "los", "las", "y", "et", "d'",
              "airport", "airports", "airstrip", "aeroport", "aeroports", "l'aeroport", "aeropuerto", "aeroporto", "flughafen", "international",
              "terminal", "port", "station", "city", "ville", "ciudad"}
# A label whose value is the place of delivery ("Country: Kenya", "País: España", "Lieu d'exécution : Madrid", "Beneficiary countries: ...").
_LABEL_BEFORE = re.compile(r"(?:^|[\n.;(])\s*(?:(?:delivery|beneficiary|destination)\s+)?(?:countr(?:y|ies)|territor(?:y|ies)|markets?|"
                           r"locations?|place of (?:performance|delivery)|lieu(?:x)? d'ex[ée]cution|lieu|pays|pa[ií]s(?:es)?|lugar de ejecuci[oó]n|"
                           r"territorio|zona|zone)\s*[:=\-]\s*(?:[A-Z][\w'.-]*\s*(?:\([A-Z0-9]+\))?\s*,?\s*(?:and\s+|et\s+|y\s+)?)*$", re.I)
# A defined territory, stated without a preposition: '"Territory" shall mean the geographical limits of the country i.e., Qatar',
# "the Territory means Kenya", "Territory: Bahrain", "namely Ghana".
_OFFICIAL = r"(?:(?:state|kingdom|republic|sultanate|emirate|union|federation|commonwealth|people's republic)\s+of\s+)?"
_DEFINED_BEFORE = re.compile(r"(?:territor(?:y|ies)|country|countries|area|market|markets|region)\W{0,3}(?:shall|will|would)?\s*(?:mean|means|include|"
                             r"includes|comprise|comprises|cover|covers|be|is|are|defined as|means the|refers? to)\b[^;]{0,80}?(?:(?:i\.?e\.?|ie\b|namely|viz\.?|"
                             r"that is)\s*,?\s*)?(?:the\s+)?" + _OFFICIAL + r"$"
                             r"|(?:^|\W)(?:i\.?e\.?|namely|viz\.?|that is)\s*,?\s*(?:the\s+)?" + _OFFICIAL + r"$", re.I)
# "Lot 2: Togo (Lomé)", "Schedule A - Kenya", "Package 3) Ghana": the place a lot is delivered in.
_LOT_BEFORE = re.compile(r"(?:^|[\n.;])\s*(?:lot|schedule|package|zone|territory|region)\s*(?:no\.?\s*)?[A-Z0-9]{1,3}\s*[:.\-)]\s*(?:[A-Z][\w'.-]*\s*,?\s*(?:\([^)]*\)\s*,?\s*)?)*$", re.I)
# "Chhatrapati Shivaji Maharaj International Airport, Mumbai, ...": the city after an airport name is where that airport is.
_AIRPORT_APPOSITION = re.compile(r"\b(?:airport|airstrip|aerodrome|a[ée]roport|aeropuerto|aeroporto|flughafen|seaport|port|terminal)\s*,\s*$", re.I)
# A country as part of an organisation's name, named BEFORE it: "Air India", "Royal Jordanian", "Fly Egypt".
_NAME_BEFORE = re.compile(r"\b(?:air|fly|royal|aero|airlines? of|airways of|air cargo)\s+$", re.I)


@dataclass(frozen=True)
class Mention:
    code: str
    start: int
    end: int
    role: Role
    why: str


def _tokens_before(text: str, start: int, limit: int = 26) -> list[str]:
    before = text[:start]
    toks = re.findall(r"[A-Za-z][A-Za-z'.-]*|,|-|\(|\)", before)
    return toks[-limit:][::-1]


def _role_of(text: str, start: int, end: int, route_pair: dict[int, Role]) -> tuple[Role, str]:
    if start in route_pair:
        return route_pair[start], "route pair (first is origin, second is destination)"
    after = text[end:end + 40]
    if _NAME_AFTER.search(after) or _NAME_BEFORE.search(text[max(0, start - 20):start]):
        return "name", "part of an organisation name"
    if _ISSUER_AFTER.search(after):
        return "issuer", f"'{text[start:end]}{after.split()[0] if after.split() else ''}' describes where the organisation is based"
    if _ISSUER_BEFORE.search(text[max(0, start - 60):start]):
        return "issuer", "stated as where the organisation is headquartered or based"
    before70 = text[max(0, start - 90):start]
    if _AIRPORT_APPOSITION.search(text[max(0, start - 30):start]):
        return "scope", "the location of the named airport (apposition after 'Airport,')"
    if _LOT_BEFORE.search(text[max(0, start - 60):start]):
        return "scope", "named by a lot / schedule / package line (where that lot is delivered)"
    if _DEFINED_BEFORE.search(before70):
        return "scope", "stated as the defined territory (no preposition: 'shall mean', 'i.e.', 'namely')"
    if _LABEL_BEFORE.search(text[max(0, start - 120):start]):
        return "scope", "the value of a country / territory / place-of-performance label"
    # Walk back over place names (capitalised words, commas, brackets, 'the', 'International Airport') to the governing word.
    # Prepositions are read whatever their case, so an all-capitals title ("... OF AIR INDIA LIMITED IN QATAR") still resolves.
    passed_and = False
    for tok in _tokens_before(text, start):
        low = tok.lower()
        if low in ("and", "et", "y"):
            passed_and = True
            continue
        if low in ("between", "entre", "zwischen"):
            return ("destination", "'between X and Y': Y is the destination") if passed_and else ("origin", "'between X and Y': X is the origin")
        if low in _ORIGIN_PREP:
            return "origin", f"introduced by '{tok}'"
        if low in ("to", "vers", "hacia"):
            return "destination", f"introduced by '{tok}'"
        if low in _SCOPE_PREP and not (low == "a" and tok == "A"):
            return "scope", f"introduced by '{tok}' (where the work is delivered)"
        if low in _SKIPPABLE or tok[:1].isupper() or low.startswith("internation"):
            continue
        break
    # "between X and Y": Y is the destination
    if re.search(r"\bbetween\s+[A-Z][\w' -]{1,40}\s+and\s+$", text[max(0, start - 60):start]):
        return "destination", "'between X and Y': Y is the destination"
    if re.search(r"\b(?:issued|granted|licen[cs]ed|certified|accredited|approved)\s+(?:by|in)\s*(?:the\s+)?$", text[max(0, start - 40):start], re.I):
        return "issuer", "stated as the issuer of a document, not a place of delivery"
    # A whole cell of a table row ("REF | subject | Doha, Qatar | date") names the place the row is about: the row has no
    # verb or preposition to say so, and a listing's location column is where the work is delivered.
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line = text[line_start:line_end if line_end >= 0 else len(text)]
    if " | " in line:
        cell_before = text[line_start:start].rsplit("|", 1)[-1]
        cell_after = text[end:line_end if line_end >= 0 else len(text)].split("|", 1)[0]
        if re.fullmatch(r"\s*(?:[A-Z][\w'.-]*\s*,?\s*)*", cell_before) and re.fullmatch(r"\s*", cell_after):
            return "scope", "a table cell naming the place (the listing's location column)"
    # Named in parentheses after the subject: "(cargo documentation processing, Germany)".
    open_paren = text.rfind("(", 0, start)
    if open_paren >= 0 and ")" not in text[open_paren:start] and re.fullmatch(r"\s*[^()\n]{1,80}?[,;]\s*", text[open_paren + 1:start]) \
            and re.match(r"\s*\)", text[end:end + 3]):
        return "scope", "named in parentheses after the subject (where the work is delivered)"
    return "unknown", "named, but the sentence does not say whether it is the issuer, the delivery country or a route end"


def _airport_spans(text: str, airport_country) -> list[tuple[int, int, str]]:
    out = []
    for m in re.finditer(r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])", text):
        c = airport_country(m.group(1))
        if c:
            out.append((m.start(), m.end(), c))
    return out


def country_roles(text: str, code: str, *, airport_country=lambda _c: None) -> list[Mention]:
    """Every mention of country `code` (by name, alias or a registered airport code) and its role."""
    t = ascii_text(text)
    spans: list[tuple[int, int]] = []
    for n in country_names(code):
        pat = r"(?<![A-Za-z0-9])" + r"\s+".join(re.escape(w) for w in n.split()) + r"(?![A-Za-z0-9])"
        for m in re.finditer(pat, t, re.I):
            if not any(s <= m.start() < e for s, e in spans):
                spans.append((m.start(), m.end()))
    airports = _airport_spans(t, airport_country)
    for s, e, c in airports:
        if c == code:
            spans.append((s, e))
    # Cities from the maintained register, unambiguous ones only ("Nairobi" -> KE; "Santiago" is left for a person).
    for s, e, _city, codes in cities_in_text(t):
        if codes == (code,) and not any(a <= s < b for a, b in spans):
            spans.append((s, e))
    # Route pairs written "DXB-NBO", "Dubai - Nairobi", "DXB to NBO" (airport codes): first origin, second destination.
    route_pair: dict[int, Role] = {}
    for i in range(len(airports) - 1):
        (s1, e1, _c1), (s2, _e2, _c2) = airports[i], airports[i + 1]
        if re.fullmatch(r"\s*(-|/|>|to|->)\s*", t[e1:s2], re.I):
            route_pair[s1] = "origin"
            route_pair[s2] = "destination"
    out = []
    for s, e in sorted(spans):
        role, why = _role_of(t, s, e, route_pair)
        out.append(Mention(code, s, e, role, why))
    return out


# ---------------------------------------------------------------- requirements

_STOP = {"a", "an", "the", "of", "and", "or", "to", "in", "for", "with", "by", "on", "at", "be", "is", "are", "must", "should", "shall",
         "will", "have", "has", "hold", "holds", "possess", "valid", "applicant", "applicants", "bidder", "bidders", "candidate",
         "candidates", "eligible", "required", "requirement", "requirements", "least", "minimum", "their", "its", "any", "all",
         "that", "this", "who", "which", "as", "from", "per", "each", "only", "also", "provide", "proof", "evidence", "demonstrate"}
_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
                 "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30", "fifty": "50", "hundred": "100"}


def _stem(w: str) -> str:
    for suf in ("ies", "es", "s", "ed", "ing"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def _content(s: str) -> tuple[set[str], set[str]]:
    words = re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?", ascii_text(s).lower().replace("licence", "license"))
    nums = {_NUMBER_WORDS.get(w, w).replace(",", "") for w in words if w.isdigit() or w in _NUMBER_WORDS or re.fullmatch(r"\d+[.,]\d+", w)}
    content = {_stem(w) for w in words if w not in _STOP and w not in _NUMBER_WORDS and not w.isdigit()}
    return content, nums


def requirement_stated(value: str, quote: str) -> tuple[bool, str]:
    """True when ONE clause of the quote states the requirement the value claims: every content word and
    every number of the value appears in that clause, with the same polarity."""
    want, want_n = _content(value)
    if not want and not want_n:
        return False, "the value states no requirement"
    v_neg = bool(_NEGATION.search(_NOT_NEGATION.sub(" ", ascii_text(value))))
    clauses = [c for c in _CLAUSE_BREAK.split(ascii_text(quote)) if c and c.strip()]
    best_missing: list[str] | None = None
    for clause in clauses:
        have, have_n = _content(clause)
        missing = sorted(want_n - have_n) + sorted(want - have)
        if not missing:
            q_neg = bool(_NEGATION.search(_NOT_NEGATION.sub(" ", clause)))
            if q_neg == v_neg:
                return True, "requirement stated in the quote"
            return False, "the quote states the opposite requirement"
        if best_missing is None or len(missing) < len(best_missing):
            best_missing = missing
    return False, "the quote does not state: " + ", ".join(best_missing or [])


# ---------------------------------------------------------------- contradictions across the document (amendments item 4)

_ANNOUNCE = (r"\binvit(?:es|ing|ation)\b", r"\b(?:are|is)\s+(?:hereby\s+)?invited\b", r"request for (?:proposals?|quotations?|information)", r"\brfp\b", r"\brfq\b",
             r"call for (?:bids|tenders|proposals|expressions of interest)", r"\bis (?:now )?open\b", r"\bnow open\b",
             r"\bare (?:now )?(?:being )?accept(?:ed|ing)\b", r"\bnow accepting\b", r"\bseeks?\b", r"\bseeking\b",
             r"\bexpressions? of interest\b", r"appel d'offres", r"\blance\b", r"\bconvoca", r"\bausschreib", r"\bschreibt\b")
_TERMINAL = (r"\b(?:has|have|is|are|was|were|been)\s+(?:now\s+)?(?:been\s+)?closed\b",
             r"\bno longer accept\w*", r"\b(?:has|have|is|are|was|were)\s+(?:now\s+)?(?:been\s+)?(?:cancel+ed|withdrawn|annul+ed|terminated|suspended)\b",
             r"\b(?:has|have|is|are|was|were)\s+(?:now\s+)?(?:been\s+)?awarded\b", r"\bawarded\s+to\b", r"\b(?:contract|tender|mandate)\s+awarded\b",
             r"(?:^|\n|[.!:]\s+)(?:tender\s+|status:\s*)?cancel+ed\b", r"(?:^|\n|[.!:]\s+)(?:tender\s+|status:\s*)?closed\b",
             r"\bhas appointed\b[^.;]{0,50}\b(?:gssa|general sales|agent|representative|provider)\b",
             r"\bsubmissions? (?:period )?(?:has|have) ended\b",
             r"\bthe (?:deadline|closing date) has passed\b", r"\b(?:process|tender|rfp|rfq|procurement) (?:is|has been) (?:closed|cancel+ed|"
             r"terminated|suspended|concluded)\b", r"\bis now closed\b", r"\bnot accepting\b", r"\bclosed to new\b")


@dataclass(frozen=True)
class Contradiction:
    announcement: str
    terminal: str

    def describe(self) -> str:
        return (f"the source announces the opportunity (\"{self.announcement}\") but also says the process has ended "
                f"(\"{self.terminal}\")")


def _sentence_at(t: str, pos: int) -> str:
    a = max(t.rfind(". ", 0, pos), t.rfind("\n", 0, pos))
    b_candidates = [x for x in (t.find(". ", pos), t.find("\n", pos)) if x >= 0]
    b = min(b_candidates) if b_candidates else len(t)
    return " ".join(t[a + 1 if a >= 0 else 0:b + 1].split())[:220]


def status_contradiction(document: str, *, reference_year: int | None = None) -> Contradiction | None:
    """A passage that announces the opportunity AND another (anywhere in the document) that says the process is
    closed, cancelled or awarded — both affirmed, and neither describing another process ("the earlier tender",
    "the 2019 framework agreement"). None when the document is consistent."""
    t = ascii_text(document)
    low = t.lower()

    def affirmed(patterns: tuple[str, ...], terminal: bool) -> list[int]:
        out = []
        for p in patterns:
            for m in re.finditer(p, low):
                if refers_to_other_process(t, m.start()):
                    continue
                pol = polarity(t, m.start(), reference_year=reference_year, end=m.end())
                # a terminal statement like "no longer accepting" carries its own negation word: accept it unless negated BEFORE it
                if pol == "affirmed" or (terminal and pol == "negated" and not _NEGATION.search(_last_tokens(_neutralise(
                        low[_clause_span(low, m.start())[0]:m.start()]), 4))):
                    out.append(m.start())
        return sorted(set(out))

    ann = affirmed(_ANNOUNCE, False)
    if not ann:
        return None
    term = affirmed(_TERMINAL, True)
    if not term:
        return None
    return Contradiction(_sentence_at(t, ann[0]), _sentence_at(t, term[0]))


# ---------------------------------------------------------------- geography across the whole document (27 Oct 2026, second instruction, item 2)

_TERRITORY_DEFINITION = re.compile(r"\b(?:territor(?:y|ies)|area of operation|scope of territory|contract territory)\b\W{0,3}(?:shall|will)?\s*"
                                   r"(?:mean|means|be|is|are|include|includes|comprise|comprises|cover|covers|defined as|refers? to)\b", re.I)
_LOT_LINE = re.compile(r"(?:^|\n|(?<=[.;]\s))\s*(?:lot|schedule|package|zone|region|territory)\s*(?:no\.?\s*)?[A-Z0-9]{1,3}\s*[:.\-–—)]", re.I)
_DISCLAIMER = re.compile(r"\b(?:disclaimer|notwithstanding|for the avoidance of doubt|governed by the laws of|jurisdiction|nothing in this|"
                         r"without prejudice|this document is (?:not|issued)|shall not be construed)\b", re.I)


def defines_territory(text: str) -> bool:
    """True when the text is itself a territory definition ('"Territory" shall mean ...')."""
    return bool(_TERRITORY_DEFINITION.search(text))


@dataclass(frozen=True)
class DocumentTerritories:
    title: frozenset[str]
    definitions: frozenset[str]
    lots: frozenset[str]
    other_scope: dict[str, str]          # country -> the sentence (elsewhere) that names it as a place of delivery
    unread_definition: str | None = None  # a territory definition whose country could not be read

    @property
    def stated(self) -> frozenset[str]:
        """The territories the notice itself defines: its title, its territory definitions and its lots/schedules."""
        return self.title | self.definitions | self.lots


# Abbreviations that end in a full stop without ending the sentence ("i.e. Bahrain", "No. 2", "Kshs. 100").
_ABBREV_END = re.compile(r"(?:\bi\.e\.|\be\.g\.|\bviz\.|\bcf\.|\bNo\.|\bNos\.|\bKshs?\.|\bRs\.|\bLtd\.|\bInc\.|\bCo\.|\bSt\.|\bMr\.|\bMs\.|\bDr\.|"
                         r"\betc\.|\bapprox\.|\bvs\.|\bmin\.|\bmax\.|\bRef\.|\bArt\.|\bcl\.|\bpara\.)$", re.I)


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for block in re.split(r"\n+", text):
        buf = ""
        for piece in re.split(r"(?<=[.;!?])\s+", block):
            buf = f"{buf} {piece}".strip() if buf else piece
            if not _ABBREV_END.search(buf):
                out.append(buf)
                buf = ""
        if buf:
            out.append(buf)
    return [x.strip() for x in out if x and x.strip()]


def _scope_codes(text: str, codes: list[str], airport_country) -> set[str]:
    out = set()
    for code in codes:
        if any(m.role in ("scope", "destination", "origin") for m in country_roles(text, code, airport_country=airport_country)):
            out.add(code)
    return out


def document_territories(document: str, title: str | None, *, countries_in, airport_country=lambda _c: None) -> DocumentTerritories:
    """Where the notice says the work is delivered, by passage kind: the title, territory definitions ('"Territory" shall
    mean ... Qatar'), lot/schedule lines, and any other passage that names a place of delivery (a disclaimer, for example).
    `countries_in(text)` lists the country codes a text names (names, aliases, registered cities)."""
    title_text = title or (_sentences(document)[0] if document.strip() else "")
    t_codes = set()
    for code in countries_in(title_text):
        roles = {m.role for m in country_roles(title_text, code, airport_country=airport_country)}
        if roles - {"name", "issuer"}:
            t_codes.add(code)
    defs: set[str] = set()
    lots: set[str] = set()
    other: dict[str, str] = {}
    unread: str | None = None
    for sent in _sentences(document):
        codes = list(countries_in(sent))
        if not codes:
            if _TERRITORY_DEFINITION.search(sent) and unread is None:
                unread = sent[:220]
            continue
        if _TERRITORY_DEFINITION.search(sent):
            defs |= _scope_codes(sent, codes, airport_country) or {c for c in codes if not any(
                m.role in ("name", "issuer") for m in country_roles(sent, c, airport_country=airport_country))}
        elif _LOT_LINE.search(sent):
            lots |= {c for c in codes if not any(m.role in ("name", "issuer") for m in country_roles(sent, c, airport_country=airport_country))}
        elif sent != title_text:
            for c in _scope_codes(sent, codes, airport_country):
                other.setdefault(c, sent[:220])
    return DocumentTerritories(frozenset(t_codes), frozenset(defs), frozenset(lots), other, None if defs else unread)


@dataclass(frozen=True)
class GeographyConflict:
    stated: tuple[str, ...]              # territories the notice defines (title / definition / lots)
    conflicting: dict[str, str]          # country -> passage that names it elsewhere as a place of delivery

    def describe(self, name_of) -> str:
        parts = [f"{name_of(c)} (\"{p}\")" for c, p in sorted(self.conflicting.items())]
        return (f"the notice's title or territory definition names {', '.join(name_of(c) for c in self.stated)} as the territory, "
                f"but another passage names {'; '.join(parts)}; a reviewer must say which is the delivery territory")


def geography_conflict(terr: DocumentTerritories) -> GeographyConflict | None:
    """A conflict exists when the notice defines its territory (title, definition or lots) and another passage names a
    DIFFERENT country as a place of delivery. Several countries in the definition are a multi-country mandate, not a conflict."""
    stated = terr.stated
    if not stated:
        return None
    conflicting = {c: p for c, p in terr.other_scope.items() if c not in stated}
    if not conflicting:
        return None
    return GeographyConflict(tuple(sorted(stated)), conflicting)


# ---------------------------------------------------------------- multi-stop rotations (27 Oct 2026, third instruction, item 4)
_ROT_STOP = r"(?:[A-Z][A-Za-z'.]+(?:\s[A-Z][A-Za-z'.]+)?|[A-Z]{3})"
_ROTATION = re.compile(_ROT_STOP + r"(?:\s?[-\u2013\u2014/>]\s?" + _ROT_STOP + r"){2,}")


def rotation_in(text: str) -> list[str] | None:
    """The stops of a multi-stop rotation written as a chain of three or more places ("Doha-Budapest-Helsinki-Doha",
    "NBO-EBB-KGL-NBO"), or None. A rotation is not a single origin-destination pair."""
    t = ascii_text(text).replace("\u2013", "-").replace("\u2014", "-")
    m = _ROTATION.search(t)
    if not m:
        return None
    stops = [x.strip() for x in re.split(r"\s?[-/>]\s?", m.group(0)) if x.strip()]
    return stops if len(stops) >= 3 else None
