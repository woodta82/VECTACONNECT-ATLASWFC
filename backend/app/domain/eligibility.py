"""Structured eligibility checks (amendments of 26 Oct 2026, item 3).

An extracted eligibility value is compared with the source wording as STRUCTURE, not only as words:

- numeric requirements: comparator (minimum / maximum / exact / none stated), number and unit
  ("at least 5 years", "no more than 3 aircraft", "USD 2,000,000 minimum turnover", "80% or more");
- dates: the relation and the date ("valid until 31 December 2026", "issued after 1 January 2025");
- AND / OR combinations: alternatives in the source must stay alternatives, and joint requirements must stay joint;
- conditions ("if", "where", "unless", "provided that", "only for applicants based in ...") must be kept;
- polarity ("must hold" vs "need not hold").

Relationship level (amendment of 26 Oct 2026, evening): matching words, numbers and units is not enough. Each
quantity, date and condition is BOUND to the requirement it qualifies and to its subject, and each country to its
role (where the applicant is based, where it operates, who issued a document). "three years of insurance and five
years of GSSA experience" is not "five years of insurance and three years of GSSA experience"; "based in Kenya ...
if operating in France" is not "based in France ... if operating in Kenya"; "valid before 1 January 2027"
(exclusive) is not "valid by 1 January 2027" (inclusive). `VALIDATION_VERSION` names these rules so records checked
under earlier rules can be found and checked again.

Outcomes: `supported` (the structure matches the source), `unsupported` (the value contradicts the source:
min/max reversed, different number, unit or date, an alternative turned into a joint requirement, opposite
polarity), or `review_required` (the value could be a fair reading but drops or reshapes meaning: a dropped
condition, a dropped alternative, a comparator the source does not state, wording the parser cannot read).
`review_required` is never treated as a fact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .meaning import ascii_text

Outcome = tuple[str, str]   # (support, reason)

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                 "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "fifty": 50, "hundred": 100}
_MIN_BEFORE = re.compile(r"\b(at least|a minimum of|minimum(?: of)?|min\.?|not less than|no less than|no fewer than|not fewer than|"
                         r"more than|over|above|exceeding|in excess of|greater than|upwards of|au moins|minimo|al menos)\s*$", re.I)
_STRICT_MIN = re.compile(r"\b(more than|over|above|exceeding|in excess of|greater than)\s*$", re.I)
_MAX_BEFORE = re.compile(r"\b(at most|a maximum of|maximum(?: of)?|max\.?|not more than|no more than|not exceeding|up to|"
                         r"less than|fewer than|under|below|within|no older than|not older than|maximo|au plus)\s*$", re.I)
_STRICT_MAX = re.compile(r"\b(less than|fewer than|under|below)\s*$", re.I)
_MIN_AFTER = re.compile(r"^\s*(\S+\s+){0,3}?(or more|or above|or greater|or higher|plus\b|\+|minimum\b|at a minimum)", re.I)
_MAX_AFTER = re.compile(r"^\s*(\S+\s+){0,3}?(or less|or fewer|or below|or lower|maximum\b|at most|at the most)", re.I)
_LOOSE_MIN = re.compile(r"\b(minimum|min\.|at least|not less than|no less than)\b", re.I)
_LOOSE_MAX = re.compile(r"\b(maximum|max\.|at most|up to|not more than|no more than|not exceeding)\b", re.I)
_EXACT_BEFORE = re.compile(r"\b(exactly|precisely)\s*$", re.I)

_UNITS = [
    (re.compile(r"^\s*(?:full\s+)?(?:years?|yrs?)\b", re.I), "year"),
    (re.compile(r"^\s*months?\b", re.I), "month"),
    (re.compile(r"^\s*(?:\w+\s+){0,2}?(?:aircraft|freighters?|planes?|airplanes?)\b", re.I), "aircraft"),
    (re.compile(r"^\s*(?:\w+\s+){0,2}?(?:employees|staff|personnel|people|persons|full-time staff)\b", re.I), "staff"),
    (re.compile(r"^\s*(?:metric\s+)?(?:tonnes?|tons?|mt)\b", re.I), "tonne"),
    (re.compile(r"^\s*(?:kg|kilograms?|kilos?)\b", re.I), "kg"),
    (re.compile(r"^\s*(?:\w+\s+){0,2}?(?:stations?|offices?|branches|locations|warehouses?)\b", re.I), "site"),
    (re.compile(r"^\s*(?:%|percent|per cent)", re.I), "percent"),
    (re.compile(r"^\s*(?:\w+\s+){0,2}?(?:airlines?|clients?|customers?|accounts?|references?)\b", re.I), "client"),
]
_CURRENCY = re.compile(r"\b(USD|US\$|EUR|GBP|AED|KES|UGX|TZS|XOF|SAR|QAR|INR|CNY)\s*$|\$\s*$|€\s*$|£\s*$", re.I)
_CURRENCY_AFTER = re.compile(r"^\s*(?:million|m|bn|billion|thousand|k)?\s*(USD|US dollars|dollars|EUR|euros?|GBP|AED|dirhams?|KES|shillings?)\b", re.I)
_SCALE = re.compile(r"^\s*(million|m\b|bn|billion|thousand|k\b)", re.I)
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)|\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.I)

_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                                       "november", "december"], 1)}
_DATE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b|\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})\b"
                   r"|\b(\d{4})-(\d{2})-(\d{2})\b", re.I)
_DATE_REL = [(re.compile(r"\b(valid\s+(?:until|through|to)|expir\w*\s+(?:no\s+earlier\s+than|after)|until|through)\s*$", re.I), "valid_until"),
             (re.compile(r"\b(before|by|no later than|not later than|prior to|not after|on or before|at the latest(?: by| on)?|earlier than)\s*$", re.I),
              "on_or_before"),
             (re.compile(r"\b(after|since|from|on or after|no earlier than|not earlier than|not before|later than)\s*$", re.I), "on_or_after")]
# Inclusive / exclusive boundary of a date relation. "before 1 January" ends on 31 December; "by 1 January" includes it.
_EXCLUSIVE = re.compile(r"\b(before|prior to|earlier than|after|later than)\s*$", re.I)
_INCLUSIVE = re.compile(r"\b(by|no later than|not later than|not after|on or before|at the latest(?: by| on)?|since|from|on or after|"
                        r"no earlier than|not earlier than|not before|through|valid\s+to|valid\s+through)\s*$", re.I)

_CONDITION = re.compile(r"\b(if|where|unless|provided that|providing that|subject to|only (?:for|if|where|applies)|in the case of|"
                        r"except(?: for)?|applies to|for (?:applicants|bidders|companies|firms|providers) (?:based|registered|located|operating) in)\b",
                        re.I)
_NEG = re.compile(r"\b(need not|not required|is not required|are not required|no requirement|not necessary|not mandatory|optional|"
                  r"does not need|do not need|not needed|non-mandatory)\b", re.I)
_OR_IDIOM = re.compile(r"\bor (?:more|less|fewer|above|below|greater|higher|lower|equivalent|similar)\b|\bon or (?:before|after)\b|\beither\b", re.I)


VALIDATION_VERSION = 7     # 1: words/numbers/units/comparators; 2: bound to requirement, subject and role (26 Oct); 3: 27 Oct gaps; 4: freight relevance, document-wide geography, status/age, amendments, advisory wording, date conventions (27 Oct, second instruction); 5: meaning-level freight relevance, announced vs open (third); 6: status freshness from the latest document that states the status, truthful publication dates, route launches to capacity and lanes, out-of-scope lots kept as excluded evidence (fourth); 7: status chronology by publication date (retrieval never supersedes a dated status), terminal-only records as historical intelligence, tender context, lot issuers from the introduction (fifth)


@dataclass(frozen=True)
class Atom:
    comparator: str        # min | min_strict | max | max_strict | exact | none
    number: float
    unit: str              # year, month, aircraft, staff, tonne, kg, site, percent, client, money:USD, count
    start: int
    end: int
    head: frozenset[str] = frozenset()   # content words of the requirement this quantity qualifies ("insurance", "gssa experience")


@dataclass(frozen=True)
class DateAtom:
    relation: str          # valid_until | on_or_before | on_or_after | date
    day: date
    start: int
    boundary: str = "unstated"           # inclusive ("by", "no later than", "on or after") | exclusive ("before", "after") | unstated
    head: frozenset[str] = frozenset()


# Segment boundaries: clause breaks, coordination and condition keywords. A quantity, date or country is bound to the
# words of its own segment.
_SEGMENT_BREAK = re.compile(r"[;,.:]|\b(?:and|or|but|if|where|unless|provided that|providing that|subject to|whereas|while|"
                            r"in the case of|except(?: for)?|only (?:for|if|where))\b|\s/\s", re.I)


def _num(m: re.Match[str]) -> float:
    if m.group(2):
        return float(_NUMBER_WORDS[m.group(2).lower()])
    return float(m.group(1).replace(",", ""))


# "5(five) years", "USD 425,000 (US Dollars Four Lakh ...)": the spelt-out repetition of a numeral is not a second quantity.
_SPELT_REPEAT = re.compile(r"(?<=\d)\s*\((?:\s*(?:" + "|".join(_NUMBER_WORDS) + r"|and|hundred|thousand|million|lakh|crore|only|us|dollars?|dollar|euros?|kenya|shillings?|"
                           r"rupees?|dirhams?|riyals?|pounds?)\s*)+\)", re.I)


_SLASH_SUFFIX = re.compile(r"(?<=\d)\s*/-?(?=\s|$|[.,;)])")        # "USD 400,000/-", "1,500,000 /-": a currency formatting suffix, not an alternative


def normalise_amounts(text: str) -> str:
    return _SLASH_SUFFIX.sub(lambda m: " " * (m.end() - m.start()), text)


def atoms(text: str) -> list[Atom]:
    t = _SPELT_REPEAT.sub(lambda m: " " * (m.end() - m.start()), normalise_amounts(ascii_text(text)))
    out: list[Atom] = []
    for m in _NUM.finditer(t):
        if _DATE_SPAN(t, m.start()):
            continue
        before, after = t[max(0, m.start() - 40):m.start()], t[m.end():m.end() + 60]
        value = _num(m)
        sm = _SCALE.match(after)
        if sm:
            value *= {"million": 1e6, "m": 1e6, "bn": 1e9, "billion": 1e9, "thousand": 1e3, "k": 1e3}[sm.group(1).lower()]
        cur = _CURRENCY.search(before)
        ca = _CURRENCY_AFTER.match(after)
        unit = None
        if cur:
            unit = "money:" + {"US$": "USD", "$": "USD", "€": "EUR", "£": "GBP"}.get(cur.group(0).strip(), cur.group(0).strip().upper())
        elif ca:
            word = ca.group(1).lower()
            unit = "money:" + {"us dollars": "USD", "dollars": "USD", "euro": "EUR", "euros": "EUR", "dirham": "AED", "dirhams": "AED",
                               "shilling": "KES", "shillings": "KES"}.get(word, word.upper())
        else:
            for pat, name in _UNITS:
                if pat.match(after):
                    unit = name
                    break
        if unit is None:
            unit = "count"
        mmin, mmax = _MIN_BEFORE.search(before), _MAX_BEFORE.search(before)
        if mmin and mmax:          # "not less than" contains "less than": the longer phrase (earlier start) wins
            mmin, mmax = (mmin, None) if mmin.start() < mmax.start() else (None, mmax)
        if _EXACT_BEFORE.search(before):
            comp = "exact"
        elif mmin:
            comp = "min_strict" if _STRICT_MIN.search(before) and not re.search(r"\b(not|no)\s+(less|fewer)", mmin.group(0), re.I) else "min"
        elif mmax:
            comp = "max_strict" if _STRICT_MAX.search(before) and not re.search(r"\b(not|no)\s+more", mmax.group(0), re.I) else "max"
        elif _MIN_AFTER.match(after):
            comp = "min"
        elif _MAX_AFTER.match(after):
            comp = "max"
        else:
            # A cue earlier in the same phrase: "Minimum annual turnover of USD 2 million", "maximum fleet age of 20 years".
            phrase = re.split(r"[;,.]|\band\b|\bor\b", t[max(0, m.start() - 60):m.start()])[-1]
            if _LOOSE_MAX.search(phrase):
                comp = "max"
            elif _LOOSE_MIN.search(phrase):
                comp = "min"
            else:
                comp = "none"
        out.append(Atom(comp, value, unit, m.start(), m.end(), _head_at(t, m.start())))
    return out


def _segment_span(t: str, pos: int) -> tuple[int, int]:
    start = 0
    end = len(t)
    for b in _SEGMENT_BREAK.finditer(t):
        if b.end() <= pos:
            start = b.end()
        elif b.start() > pos:
            end = b.start()
            break
    return start, end


def _head_at(t: str, pos: int) -> frozenset[str]:
    """Content words of the segment around `pos`, minus comparators, numbers, units and generic words. These are the
    requirement the quantity or date qualifies. Countries are left in: "experience in Kenya" differs from "in France"."""
    a, b = _segment_span(t, pos)
    seg = _COMPARATOR_WORDS.sub(" ", t[a:b])
    seg = _NUM.sub(" ", seg)
    words = {w for w in re.findall(r"[a-z][a-z0-9-]+", ascii_text(seg).lower().replace("licence", "license")) if w not in _STOPWORDS}
    words -= {"years", "year", "yrs", "months", "month", "percent", "million", "billion", "thousand", "usd", "eur", "gbp", "aed", "kes",
              "minimum", "maximum", "least", "most", "than", "no", "not", "annual", "per", "annum", "total", "aggregate"}
    return frozenset(words)


def _DATE_SPAN(t: str, pos: int) -> bool:  # noqa: N802 - small predicate
    return any(m.start() <= pos < m.end() for m in _DATE.finditer(t))


# A date in a submission clause ("proposals are due by", "closing date", "must be submitted by") is the tender's deadline,
# not an eligibility date, even when both sit in one sentence.
_SUBMISSION_DATE = re.compile(r"\b(?:due|deadline|closing(?: date)?|close[sd]?|submi\w*|received|receipt|lodged|tender(?:s)? (?:by|before)|"
                              r"proposals?|bids?|offers?|quotations?|applications?|responses?|date limite|soumis\w*|d[ée]p[ôo]t|plazo|propuestas?|"
                              r"ofertas?|presentar\w*|prazo|propostas?|einzureichen|angebote|frist)\b", re.I)
_ELIGIBILITY_DATE = re.compile(r"\b(?:valid|validity|expir\w*|issued|dated|certificate|certification|licen[cs]e|permit|registration|accredit\w*|"
                               r"incorporated|established|founded|since|experience|audited|financial year)\b", re.I)


def is_submission_date(text: str, start: int) -> bool:
    before = ascii_text(text)[max(0, start - 70):start]
    return bool(_SUBMISSION_DATE.search(before)) and not _ELIGIBILITY_DATE.search(before[-45:])


def dates(text: str) -> list[DateAtom]:
    t = ascii_text(text)
    out: list[DateAtom] = []
    for m in _DATE.finditer(t):
        try:
            if m.group(1):
                d = date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
            elif m.group(4):
                d = date(int(m.group(6)), _MONTHS[m.group(4).lower()], int(m.group(5)))
            else:
                d = date(int(m.group(7)), int(m.group(8)), int(m.group(9)))
        except ValueError:
            continue
        before = t[max(0, m.start() - 40):m.start()]
        rel = next((name for pat, name in _DATE_REL if pat.search(before)), "date")
        if re.search(r"\b(on or before|on or after|not before|not after|no later than|not later than|no earlier than|not earlier than)\s*$",
                     before, re.I) or (_INCLUSIVE.search(before) and not _EXCLUSIVE.search(before)):
            boundary = "inclusive"
        elif _EXCLUSIVE.search(before):
            boundary = "exclusive"
        else:
            boundary = "unstated"
        out.append(DateAtom(rel, d, m.start(), boundary, _head_at(t, m.start())))
    return out


_STOPWORDS = {"the", "a", "an", "of", "to", "in", "for", "and", "or", "must", "should", "shall", "be", "is", "are", "have", "has", "hold",
              "with", "by", "from", "on", "at", "applicants", "bidders", "bidder", "applicant", "providers", "provider", "companies", "company",
              "required", "requirement", "requirements", "both", "either", "their", "its", "valid", "will", "need", "needs"}


# Wording that makes AND-joined requirements one indivisible requirement ("both are required", "all of the following").
_JOINT = re.compile(r"\b(both|all of the following|all of these|together with|in addition to|as well as|jointly|each of)\b", re.I)


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9-]+", ascii_text(text).lower()) if w not in _STOPWORDS}


def _connective(text: str) -> set[str]:
    t = _OR_IDIOM.sub(" ", normalise_amounts(ascii_text(text)).lower())
    found = set()
    if re.search(r"\bor\b|/(?=\s*\w)|\bou\b|\bo\b", t):
        found.add("or")
    if re.search(r"\band\b|\bas well as\b|\bboth\b|\bet\b|\by\b", t):
        found.add("and")
    return found


def _condition(text: str) -> str | None:
    m = _CONDITION.search(ascii_text(text))
    return m.group(0).lower() if m else None


def _comp_class(c: str) -> str:
    return {"min_strict": "min", "max_strict": "max"}.get(c, c)


_COMP_WORDS = {"min": "a minimum", "min_strict": "more than", "max": "a maximum", "max_strict": "less than", "exact": "exactly",
               "none": "no minimum or maximum"}


_COMPARATOR_WORDS = re.compile(r"\b(at least|a minimum of|minimum(?: of)?|min\.?|not less than|no less than|no fewer than|not fewer than|"
                               r"more than|over|above|exceeding|in excess of|greater than|at most|a maximum of|maximum(?: of)?|max\.?|"
                               r"not more than|no more than|not exceeding|up to|less than|fewer than|under|below|or more|or less|or fewer|"
                               r"or above|or below|exactly)\b", re.I)


_DATE_RELATION_WORDS = re.compile(r"\b(no later than|not later than|on or before|on or after|no earlier than|not earlier than|not before|"
                                  r"not after|at the latest|prior to|earlier than|later than|before|after|by|until|through|since|from)\b"
                                  r"(?=\s*(?:the\s+)?(?:\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}))", re.I)


def strip_comparators(text: str) -> str:
    """The text without comparator and date-relation wording (both checked structurally by `compare`), for the
    word-level check."""
    return _DATE_RELATION_WORDS.sub(" ", _COMPARATOR_WORDS.sub(" ", text))


def has_structure(text: str) -> bool:
    return bool(atoms(text) or dates(text))


def _n(x: float) -> str:
    return f"{x:,.0f}" if x >= 1000 and x == int(x) else f"{x:g}"


def _unit_label(unit: str) -> str:
    if unit == "count":
        return ""
    return unit.split(":", 1)[1] if unit.startswith("money:") else (unit + "s" if unit in ("year", "month", "site", "client") else unit)


# ---------------------------------------------------------------- roles, conditions and relationships

from ..reference.geography import COUNTRIES, countries_mentioned, country_names  # noqa: E402


def _cname(code: str) -> str:
    return COUNTRIES.get(code, (code,))[0]


_ROLE_BEFORE = [
    (re.compile(r"\b(?:based|registered|located|incorporated|established|headquartered|domiciled|resident|situated|organi[sz]ed|"
                r"constituted|formed)\s+(?:in|within)\s*(?:the\s+)?$", re.I), "based_in"),
    (re.compile(r"\b(?:based|registered|located|incorporated|established|headquartered|domiciled|resident|situated)\s+outside(?:\s+of)?"
                r"\s*(?:the\s+)?$", re.I), "based_outside"),
    (re.compile(r"\b(?:operat\w*|serv\w*|work\w*|deliver\w*|perform\w*|trad\w*|fly\w*|flights?|handl\w*|provid\w*|activit\w*|business|"
                r"presence|representation|sales|offices?|stations?|branch\w*)\s+(?:in|within|into|to|across|throughout|for)\s*(?:the\s+)?$", re.I),
     "operating_in"),
    (re.compile(r"\b(?:issued|granted|licen[cs]ed|certified|accredited|approved|recogni[sz]ed|authori[sz]ed)\s+(?:by|in)\s*(?:the\s+)?$"
                r"|\b(?:licen[cs]e|permit|certificate|authori[sz]ation|registration|approval)\s+(?:from|of)\s*(?:the\s+)?$", re.I), "issued_by"),
    (re.compile(r"\b(?:experience|track record|references?|contracts?)\s+(?:in|within|across)\s*(?:the\s+)?$", re.I), "experience_in"),
]
_ROLE_LABEL = {"based_in": "where the applicant is based", "based_outside": "applicants based outside it", "operating_in": "where it operates",
               "issued_by": "the issuer of a document", "experience_in": "where experience was gained", "mentioned": "mentioned"}


def country_roles(text: str) -> dict[str, set[str]]:
    """{country code: roles} for every country named in the text (by name or unambiguous alias)."""
    t = ascii_text(text)
    out: dict[str, set[str]] = {}
    for code in countries_mentioned(t):
        spans: list[tuple[int, int]] = []
        for n in country_names(code):
            pat = r"(?<![A-Za-z0-9])" + r"\s+".join(re.escape(w) for w in n.split()) + r"(?![A-Za-z0-9])"
            for m in re.finditer(pat, t, re.I):
                if not any(a <= m.start() < b for a, b in spans):
                    spans.append((m.start(), m.end()))
        for a, _b in spans:
            before = t[max(0, a - 50):a]
            role = next((name for pat, name in _ROLE_BEFORE if pat.search(before)), "mentioned")
            out.setdefault(code, set()).add(role)
    return out


_COND_START = re.compile(r"\b(if|where|unless|provided that|providing that|subject to|only (?:for|if|where)|in the case of|except(?: for)?|"
                         r"for (?:applicants|bidders|companies|firms|providers) (?:based|registered|located|operating) in)\b", re.I)


def conditions(text: str) -> list[tuple[str, frozenset[str]]]:
    """(keyword, content words of the condition clause) for each condition in the text."""
    t = ascii_text(text)
    out = []
    for m in _COND_START.finditer(t):
        body = re.split(r"[;,.]|\b(?:then|and|or)\b", t[m.end():m.end() + 160])[0]
        words = {w for w in re.findall(r"[a-z][a-z0-9-]+", body.lower().replace("licence", "license")) if w not in _STOPWORDS}
        out.append((m.group(0).lower(), frozenset(words)))
    return out


_DATE_RELATION_WORDS_ALL = re.compile(r"\b(no later than|not later than|on or before|on or after|no earlier than|not earlier than|not before|not after|"
                                      r"at the latest|prior to|earlier than|later than|before|after|by|until|through|since|from|valid|expir\w*)\b", re.I)
_GROUP_NOISE = {"as", "an", "per", "such", "any", "all", "own", "than", "later", "earlier", "eligible", "applicant", "applicants", "bidder",
                "bidders", "candidates", "tenderers", "providers", "provider", "must", "shall", "should", "least", "most", "where", "if"}


def _segment_words(text: str) -> list[frozenset[str]]:
    """Content words of each coordination segment (split at and/or/commas/conditions), numbers and units removed: what
    the text binds TOGETHER. "IATA cargo agent accreditation and a Kenyan trading licence" gives two groups."""
    t = _DATE.sub(" ", _DATE_RELATION_WORDS_ALL.sub(" ", strip_comparators(ascii_text(text))))
    out = []
    last = 0
    for b in list(_SEGMENT_BREAK.finditer(t)) + [None]:
        seg = t[last:b.start()] if b else t[last:]
        words = frozenset(w for w in _head_at(seg, 0) if w not in _GROUP_NOISE) if seg.strip() else frozenset()
        if words:
            out.append(words)
        if b:
            last = b.end()
    return out


def _stem(w: str) -> str:
    for suf in ("ies", "es", "s", "ed", "ing"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def _groups_consistent(value: str, source: str) -> str | None:
    """None when every group of words the value binds together is bound together in the source; else a reason."""
    src_groups = [frozenset(_stem(w) for w in g) for g in _segment_words(source)]
    for g in _segment_words(value):
        vg = frozenset(_stem(w) for w in g)
        if len(vg) < 2:
            continue
        if any(vg <= sg for sg in src_groups):
            continue
        best = max(src_groups, key=lambda sg: len(vg & sg), default=frozenset())
        if not (vg & best):
            continue                      # nothing in common: the word-level check reports missing words
        return (f"the value binds '{' '.join(sorted(vg))}' together; the source groups these words differently "
                f"('{' '.join(sorted(best))}')")
    return None


def _heads_overlap(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return True          # nothing to bind on: the word-level check decides
    return bool(a & b) or any(x.startswith(y[:5]) or y.startswith(x[:5]) for x in a for y in b if len(x) > 5 and len(y) > 5)


def _label_head(h: frozenset[str]) -> str:
    return " ".join(sorted(h)) if h else "the requirement"


def compare(value: str, source: str) -> Outcome:
    support, reason = _compare(value, source)
    return support, re.sub(r"\s{2,}", " ", reason).replace(" ,", ",").replace(" ;", ";").replace(" '", " '").strip()


_REPLACE_VERB = r"(?:reduced|increased|raised|lowered|changed|amended|revised|cut|decreased|extended|shortened|replaced|updated|now)"
# "reduced from four years to three years" / "increased from USD 1 million to USD 2 million"
_REPLACE_FROM_TO = re.compile(r"\b" + _REPLACE_VERB + r"\s+from\s+(?P<old>[^.;,]{1,60}?)\s+to\s+(?P<new>[^.;,]{1,60}?)(?=[.;,]|\s+(?:and|with|effective|as)\b|$)", re.I)
# "the requirement for four years of audited accounts is reduced to three years"
_REPLACE_TO = re.compile(r"(?P<old>[^.;,]{1,80}?)\s+(?:is|are|was|were|has been|have been|shall be|will be)\s+" + _REPLACE_VERB +
                         r"\s+(?:from\s+[^.;,]{1,40}?\s+)?to\s+(?P<new>[^.;,]{1,60}?)(?=[.;,]|$)", re.I)


def replaced_spans(source: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """(superseded spans, current spans) of an amendment that replaces one quantity with another, in ascii_text coordinates."""
    t = ascii_text(source)
    old: list[tuple[int, int]] = []
    new: list[tuple[int, int]] = []
    for m in _REPLACE_FROM_TO.finditer(t):
        old.append(m.span("old"))
        new.append(m.span("new"))
    for m in _REPLACE_TO.finditer(t):
        if any(a <= m.start("new") < b for a, b in new):
            continue
        old.append(m.span("old"))
        new.append(m.span("new"))
    return old, new


def _compare(value: str, source: str) -> Outcome:
    """Structural comparison of an extracted eligibility value with the source sentence(s): every number, date,
    condition and country is checked in its RELATIONSHIP to the requirement, subject and role it belongs to."""
    v_atoms, s_atoms = atoms(value), atoms(source)
    # 0. an amendment that replaces a quantity: the replaced figure is superseded, the new one is the requirement
    old_spans, new_spans = replaced_spans(source)
    superseded = [sa for sa in s_atoms if any(a <= sa.start < b for a, b in old_spans)]
    current = [sa for sa in s_atoms if any(a <= sa.start < b for a, b in new_spans)]
    for va in v_atoms:
        if any(sa.number == va.number and sa.unit == va.unit for sa in superseded) and \
                not any(sa.number == va.number and sa.unit == va.unit for sa in current):
            repl = next((sa for sa in current if sa.unit == va.unit), None)
            return "unsupported", (f"the source replaces {_n(va.number)} {_unit_label(va.unit)} with "
                                   f"{_n(repl.number) + ' ' + _unit_label(repl.unit) if repl else 'a new value'} (amendment); the value cites the superseded figure")
    s_atoms = [sa for sa in s_atoms if sa not in superseded]
    # 1. numbers, units and comparators, each bound to the requirement it qualifies
    for va in v_atoms:
        same = [sa for sa in s_atoms if sa.number == va.number and sa.unit == va.unit]
        if same and any(sa in current for sa in same):
            continue                                   # the amended value: the amendment sentence is its binding
        if not same:
            near = [sa for sa in s_atoms if sa.unit == va.unit]
            if near:
                return "unsupported", (f"the source states {_COMP_WORDS[near[0].comparator]} of {_n(near[0].number)} {_unit_label(near[0].unit)}, "
                                       f"not {_n(va.number)}")
            num_only = [sa for sa in s_atoms if sa.number == va.number]
            if num_only:
                return "unsupported", f"the source's {_n(va.number)} is in {_unit_label(num_only[0].unit)}, not {_unit_label(va.unit)}"
            return "unsupported", f"the source does not state {_n(va.number)} {_unit_label(va.unit)}"
        bound = [sa for sa in same if _heads_overlap(va.head, sa.head)]
        # The number must be bound to the words the VALUE attaches it to. When another source quantity of the same unit shares
        # more of those words than the same-number atom does ("USD 425,000 to Air India Express" when the source gives
        # 425,000 to Air India and 1,500,000 to Air India Express), the value swapped the figures.
        if bound and va.head:
            best_same = max(len(va.head & sa.head) for sa in bound)
            closer = [sa for sa in s_atoms if sa.unit == va.unit and sa.number != va.number and len(va.head & sa.head) > best_same]
            if closer:
                return "unsupported", (f"the source attaches {_n(closer[0].number)} {_unit_label(closer[0].unit)} to '{_label_head(closer[0].head)}' and "
                                       f"{_n(va.number)} {_unit_label(va.unit)} to '{_label_head(bound[0].head)}'; the value swaps them")
        if not bound:
            # The same number qualifies something else in the source. Is the value's requirement quantified differently there?
            other = [sa for sa in s_atoms if sa.unit == va.unit and sa.number != va.number and va.head and sa.head and (va.head & sa.head)]
            if other:
                return "unsupported", (f"the source attaches {_n(same[0].number)} {_unit_label(same[0].unit)} to '{_label_head(same[0].head)}' and "
                                       f"{_n(other[0].number)} {_unit_label(other[0].unit)} to '{_label_head(other[0].head)}'; the value swaps them")
            return "review_required", (f"the source attaches {_n(same[0].number)} {_unit_label(same[0].unit)} to '{_label_head(same[0].head)}', "
                                       f"not to '{_label_head(va.head)}'")
        sa = bound[0]
        if _comp_class(sa.comparator) != _comp_class(va.comparator):
            if va.comparator != "none" and sa.comparator == "none":
                return "review_required", (f"the value says {_COMP_WORDS[va.comparator]} of {_n(va.number)} {_unit_label(va.unit)}; the source states the "
                                           "number without a minimum or maximum")
            if va.comparator == "none":
                return "review_required", f"the source states {_COMP_WORDS[sa.comparator]} of {_n(sa.number)} {_unit_label(sa.unit)}; the value drops it"
            return "unsupported", (f"the source states {_COMP_WORDS[sa.comparator]} of {_n(sa.number)} {_unit_label(sa.unit)}; "
                                   f"the value turns it into {_COMP_WORDS[va.comparator]}")
        if sa.comparator != va.comparator:
            return "review_required", (f"the source says {_COMP_WORDS[sa.comparator]} {_n(sa.number)} {_unit_label(sa.unit)}; the value says "
                                       f"{_COMP_WORDS[va.comparator]} (inclusive vs exclusive)")
    # 1b. a quantified requirement in the source that the value leaves out ("experience" vs "at least 5 years of experience")
    v_words = _content_words(value)
    t_src = ascii_text(source)
    for sa in s_atoms:
        if sa.comparator != "none" or sa.unit not in ("count",):
            # only a quantity attached to what the value talks about (the words around it overlap the value)
            around = _content_words(" ".join(re.split(r"[;,.]|\band\b|\bor\b", t_src[sa.start:sa.end + 70])[:1] +
                                             re.split(r"[;,.]|\band\b|\bor\b", t_src[max(0, sa.start - 70):sa.start])[-1:]))
            if not (around & v_words):
                continue
            if not any(va.number == sa.number and va.unit == sa.unit for va in v_atoms):
                return "review_required", (f"the source states {_COMP_WORDS[sa.comparator]} of {_n(sa.number)} {_unit_label(sa.unit)}; "
                                           "the value leaves it out")
    # 2. dates: the day, its relation, its inclusive/exclusive boundary and what it qualifies. A submission deadline stated in
    #    the same sentence is not an eligibility date: it is neither "left out" nor a valid eligibility value.
    s_dates = [d for d in dates(source) if not is_submission_date(source, d.start)]
    v_dates = dates(value)
    for vd in v_dates:
        if is_submission_date(value, vd.start):
            return "review_required", f"the value cites {vd.day.isoformat()} from the submission clause; that is the deadline, not an eligibility date"
        match = [sd for sd in s_dates if sd.day == vd.day]
        if not match:
            if any(d.day == vd.day for d in dates(source)):
                return "unsupported", f"the source's {vd.day.isoformat()} is the submission deadline, not an eligibility date"
            return "unsupported", f"the source does not state the date {vd.day.isoformat()}"
        bound_d = [sd for sd in match if _heads_overlap(vd.head, sd.head)] or match
        if len(s_dates) > 1 and not [sd for sd in match if _heads_overlap(vd.head, sd.head)]:
            return "review_required", f"the source's {vd.day.isoformat()} qualifies '{_label_head(match[0].head)}', not '{_label_head(vd.head)}'"
        sd = bound_d[0]
        if vd.relation != "date" and sd.relation not in ("date", vd.relation):
            return "unsupported", f"the source ties {vd.day.isoformat()} to '{sd.relation.replace('_', ' ')}', not '{vd.relation.replace('_', ' ')}'"
        if vd.relation == "date" and sd.relation != "date":
            return "review_required", (f"the source ties {vd.day.isoformat()} to '{sd.relation.replace('_', ' ')}'; "
                                       "the value does not say how the date applies")
        if vd.relation != "date" and vd.boundary != sd.boundary:
            return "review_required", (f"the source's boundary at {vd.day.isoformat()} is {sd.boundary} and the value's is {vd.boundary}; "
                                       "they may differ by one day (inclusive vs exclusive)")
    for sd in s_dates:
        if not any(vd.day == sd.day for vd in v_dates):
            return "review_required", f"the source's date {sd.day.isoformat()} ({sd.relation.replace('_', ' ')}) is left out of the value"
    # 3. countries keep their roles (where based, where operating, who issued)
    s_geo, v_geo = country_roles(source), country_roles(value)
    for code, v_roles in v_geo.items():
        s_roles = s_geo.get(code)
        if s_roles is None:
            return "unsupported", f"the source does not mention {_cname(code)}"
        if v_roles & s_roles:
            continue
        if "mentioned" in v_roles or "mentioned" in s_roles:
            return "review_required", (f"the source gives {_cname(code)} the role '{_ROLE_LABEL[sorted(s_roles)[0]]}'; "
                                       f"the value's role for it is not clear")
        return "unsupported", (f"the source has {_cname(code)} as {_ROLE_LABEL[sorted(s_roles)[0]]}; the value makes it "
                               f"{_ROLE_LABEL[sorted(v_roles)[0]]} (country roles differ)")
    # 4. AND / OR
    s_conn, v_conn = _connective(source), _connective(value)
    if "or" in s_conn and "or" not in v_conn:
        if "and" in v_conn:
            return "unsupported", "the source gives alternatives (or); the value makes them joint requirements (and)"
        return "review_required", "the source allows alternatives (or); the value states only part of them"
    if "or" in v_conn and "or" not in s_conn and "and" in s_conn:
        return "unsupported", "the value offers alternatives (or); the source requires them jointly (and)"
    if "and" in s_conn and "and" not in v_conn and _JOINT.search(ascii_text(source)):
        s_words = _content_words(source)
        if s_words and len(s_words & v_words) * 10 < len(s_words) * 7:
            return "review_required", "the source requires several things jointly (and); the value states only part of them"
    # 5. conditions: present, and about the same thing
    s_conds, v_conds = conditions(source), conditions(value)
    if s_conds and not v_conds:
        return "review_required", f"the source attaches a condition ('{s_conds[0][0]} ...'); the value drops it"
    if v_conds and not s_conds:
        return "review_required", f"the value adds a condition ('{v_conds[0][0]} ...') the source does not state"
    for _kw, body in v_conds:
        if body and not any(_heads_overlap(body, sb) and (body & sb) for _k, sb in s_conds if sb):
            return "review_required", "the value's condition is about something other than the source's condition"
    # 6. qualifiers stay with their nouns: "IATA cargo agent accreditation and a Kenyan trading licence" is not
    #    "Kenyan cargo agent accreditation and an IATA trading licence"
    grouped = _groups_consistent(value, source)
    if grouped:
        return "review_required", grouped
    # 7. polarity
    if bool(_NEG.search(ascii_text(source))) != bool(_NEG.search(ascii_text(value))):
        return "unsupported", "the source and the value disagree on whether the requirement applies"
    return "supported", "requirement, numbers, dates, roles, combination and conditions match the source"
