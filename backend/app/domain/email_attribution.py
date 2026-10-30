"""Person-to-e-mail attribution and currency (30 Oct 2026; tightened in 4.8.0).

OWNERSHIP. An address is attributed to a person ONLY when the page itself ties it to that specific individual:

* an **explicit statement** — the address stands in the same sentence as the person's name, with no other person named between;
* a **labelled contact block** — the name, then the address on one of the next lines of the same block, nobody else between;
* a **structured row** — a table row naming exactly one person beside the address.

A local part that matches a person's name (jane.smith@…, jsmith@…) is SUPPORTING evidence only. On its own it never assigns an address:
the address becomes a candidate pending review ("the local part matches X's name, but nothing on the page says it is X's address") —
a supplier's Jane Smith, a namesake at a partner, or a reused address all look the same.

DOMAIN. When the organisation's own domain is known and the address is on another domain, the address is not assigned automatically —
and not rejected either: subsidiaries, agencies and advisers legitimately use other domains. It is assigned only when the passage explains
the relationship (subsidiary, group company, appointed agency, GSA/GSSA for, acting for, adviser or consultant to); otherwise it is pending
review with the reason "investigate the relationship". A supplier, vendor or partner contact belongs to that outside organisation, never to
a person at the company; a third-party press or agency contact belongs to nobody at the company.

CURRENCY. Wording that an address is obsolete, replaced, withdrawn, no longer monitored or belongs to a former employee marks it
**historical**: kept as evidence, never offered as a current route. A replacement named in the same passage ("replaced by …", "please use …
instead") is current. Publication is never a claim of deliverability.

Shared or departmental mailboxes (info@, cargo@, sales@, press@ …) are company contacts, never a person's. When two people share a passage
and nothing singles one out, the address is a candidate pending review. Nothing is guessed from a pattern.

The module is pure: `attribute(text, names, …)` returns every address on a page with its owner (or none), basis, currency and passage, so the
same rule serves live research, the re-check of earlier assignments and the tests.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_SENT_END = re.compile(r"(?<=[.!?;])\s+|\n{2,}")
_LABEL = re.compile(r"^\s*(?:e-?mail|email|mail|contact|e-?post|courriel|correo)\s*[:：]\s*", re.I)
_CELL = re.compile(r"\s*(?:\||\t)\s*")
_GENERIC_NAME = re.compile(r"\b([A-Z][a-zà-ſ]+(?:[-'][A-Z][a-zà-ſ]+)?)\s+(?:(?:[A-Z]\.|van|von|de|der|den|da|di|du|le|la|del|dos|das|bin|al)\s+)?([A-Z][a-zà-ſ]+(?:[-'][A-Z][a-zà-ſ]+)?)\b")
# an address that is obsolete, withdrawn, or a former employee's
_STALE_CUE = re.compile(r"\bno longer (?:valid|in use|active|monitored|in service|works?|working|used|with (?:us|the company)|at (?:the company|[A-Z]))|"
                        r"\bdo not (?:use|write to|send (?:anything )?to|e-?mail)\b|\bdon't use\b|\bobsolete\b|\bdeprecated\b|\bdiscontinued\b|"
                        r"\b(?:has been|have been|was|were|is being|is) (?:replaced|withdrawn|deactivated|closed|retired|disabled|superseded)\b|"
                        r"\bnot (?:being )?monitored\b|\b(?:old|previous|former|outdated) (?:e-?mail )?address\b|\bformer(?:ly)?\b|\bhas left\b|\bleft the company\b|"
                        r"\bretired\b|\bwill bounce\b|\bbounces?\b|\bout of use\b|\bno longer exists\b", re.I)
# a replacement named alongside: the address after it is the current one
_NEW_CUE = re.compile(r"\breplaced by\b|\bplease (?:use|write to|contact|e-?mail)\b|\binstead\b|\bnew (?:e-?mail )?address\b|\bgoing forward\b|\bfrom now on\b|\bnow (?:at|use)\b", re.I)
# a relationship that explains an address on another domain
_RELATION_CUE = re.compile(r"\bsubsidiar(?:y|ies)\b|\bgroup compan(?:y|ies)\b|\bpart of (?:the )?[A-Z]|\bsister compan|\bparent compan|\bappointed (?:agent|agency|gsa|gssa)\b|"
                           r"\b(?:our|its|the company's) (?:appointed )?(?:agent|agency|gsa|gssa|representative|adviser|advisor|consultant|counsel)\b|"
                           r"\b(?:gsa|gssa|general sales agent|cargo sales agent) for\b|\bacting for\b|\b(?:adviser|advisor|consultant) to\b|\brepresents? (?:us|the company)\b", re.I)
# an outside supplier, vendor or partner: the address is that organisation's, not a person's at the company
_SUPPLIER_CUE = re.compile(r"\bsupplier\b|\bvendor\b|\bprovided by\b|\bpowered by\b|\bservice provider\b|\b(?:it|software|systems?|platform) (?:provider|partner|support)\b|"
                           r"\boutsourced to\b|\bcontractor\b|\bpartner (?:company|organisation|organization|firm)\b|\bour partners?\b", re.I)
_PRESS_CUE = re.compile(r"\b(press|media)\s+(contact|enquir|inquir|office|relations)|\bfor (further|more) information\b|\bon behalf of\b|\b(pr|communications?) agency\b|\bpress office\b", re.I)

SHARED_WORDS = frozenset("""
info information sales cargo cargosales ops operations press media contact contacts office booking bookings reservations reservation support admin
administration hello enquiries enquiry inquiries inquiry team hr jobs careers career marketing customerservice customer service services export exports
import imports accounts accounting finance general mail post welcome station stations handling claims quotes quote rates pricing charter charters dg
pharma perishables express mgmt management secretariat communications comms pr newsroom webmaster noreply no-reply donotreply privacy legal procurement
tenders tender purchasing supply it helpdesk security compliance quality safety gsa gssa agency airport airfreight freight logistics commercial
reception frontdesk desk duty dutyofficer cs csc centre center hq headoffice head-office europe asia africa america americas uk usa
manager director md ceo cfo coo cco vp president chairman secretary officer department dept
""".split())
_ROLE_WORDS = frozenset("""
head of managing director manager chief officer vice president general services service group airlines airline airways airport cargo sales
limited ltd uab sia oü gmbh ag sa nv bv plc inc llc co company holding logistics freight international global express regional country
contact email e-mail tel phone fax press media enquiries information further for more on behalf
partner partners systems solutions consulting agency feeder road air
january february march april may june july august september october november december
""".split())


@dataclass
class Attribution:
    email: str
    person: str | None            # the person the address belongs to, or None
    kind: str                     # personal | shared | third_party | other_person | unassigned
    basis: str                    # name_match | explicit_statement | contact_block | table_row | shared_mailbox | none
    confidence: str               # clear | ambiguous | none
    quote: str
    reason: str
    candidates: list[str] = field(default_factory=list)   # people the address could belong to when ambiguous
    department: str | None = None                           # for a shared mailbox: its local part
    currency: str = "current"                               # current | historical (obsolete, replaced, withdrawn, a former employee's)
    currency_reason: str | None = None
    supporting: list[str] = field(default_factory=list)     # supporting evidence that is not proof (a matching local part, an explained domain)


# ----------------------------------------------------------------------------------------------- names and mailboxes
def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def name_tokens(name: str) -> list[str]:
    toks = [t for t in re.split(r"[^a-z]+", _fold(name)) if t]
    return [t for t in toks if t not in ("van", "von", "de", "der", "den", "da", "di", "du", "le", "la", "del", "dos", "das", "bin", "al", "dr", "mr", "mrs", "ms")] or toks


def _local(email: str) -> str:
    return email.split("@", 1)[0].lower()


def _local_parts(local: str) -> list[str]:
    return [p for p in re.split(r"[._\-+]", re.sub(r"\d+$", "", local)) if p]


def _shared_compound(s: str) -> bool:
    """'cargosalesteam', 'salesdesk', 'infocenter': shared words run together (every piece a shared word of three letters or more)."""
    if s in SHARED_WORDS:
        return True
    return any(s[:i] in SHARED_WORDS and len(s[:i]) >= 3 and _shared_compound(s[i:]) for i in range(3, len(s) - 1))


def mailbox_kind(email: str) -> tuple[str, str]:
    """('shared' | 'name_like' | 'opaque', reason). Shared: a role, department or function mailbox; name_like: reads as a person's
    name (two alphabetic parts, or one long alphabetic part); opaque: initials or codes."""
    local = _local(email)
    parts = _local_parts(local)
    if not parts or local in SHARED_WORDS or parts[0] in SHARED_WORDS or all(_shared_compound(p) for p in parts):
        return "shared", f"'{local}@' is a shared or departmental mailbox, not a person's"
    if any(p in SHARED_WORDS for p in parts) and len(parts) >= 2 and not all(p.isalpha() and len(p) >= 3 for p in parts if p not in SHARED_WORDS):
        return "shared", f"'{local}@' names a function, not a person"
    if len(parts) >= 2 and all(p.isalpha() and len(p) >= 2 for p in parts[:2]):
        return "name_like", f"'{local}@' reads as a person's name"
    if len(parts) == 1 and parts[0].isalpha() and len(parts[0]) >= 5:
        return "name_like", f"'{local}@' reads as a person's name"
    return "opaque", f"'{local}@' is initials or a code"


def name_matches(email: str, name: str, *, initials: bool = False) -> bool:
    """The local part is this person's name. Bare initials ('js@') count only when `initials` is set: on their own they are too weak
    to tie an address to anyone, but they never contradict a structural tie either."""
    toks = name_tokens(name)
    if not toks:
        return False
    local = re.sub(r"\d+$", "", _local(email))
    if len(toks) == 1:
        return local == toks[0]
    first, last = toks[0], toks[-1]
    mids = toks[1:-1]
    forms = {f"{first}.{last}", f"{first}_{last}", f"{first}-{last}", f"{first}{last}", f"{first[0]}{last}", f"{first[0]}.{last}", f"{first[0]}_{last}",
             f"{last}.{first}", f"{last}_{first}", f"{last}-{first}", f"{last}{first}", f"{last}{first[0]}", f"{last}.{first[0]}", f"{first}.{last[0]}",
             f"{first}{last[0]}", f"{first}.{last[:1]}", last if len(last) >= 6 else "", first if len(first) >= 6 else ""}
    if initials:
        forms |= {f"{first[0]}{last[0]}", f"{first[0]}.{last[0]}"}
    for m in mids:
        forms |= {f"{first}.{m}.{last}", f"{first}{m[0]}{last}", f"{first}.{m[0]}.{last}", f"{first[0]}{m[0]}{last}"}
    return local in {f for f in forms if f}


def matches_another(email: str, name: str, others: Iterable[str]) -> str | None:
    """The other person whose name the local part is — and not this person's (jsmith@ matches both Jane and John Smith: the structure decides)."""
    if name_matches(email, name):
        return None
    for o in others:
        if o != name and name_matches(email, o):
            return o
    return None


def currency(text: str, span: tuple[int, int], sentence: tuple[int, int], *, person_sentence: str | None = None) -> tuple[str, str | None]:
    """('current' | 'historical', reason) for the address at `span`.

    Historical when its passage says it is obsolete, replaced, withdrawn, not monitored, or a former employee's. The address named as the
    replacement ('replaced by new@…', 'please use new@… instead') is current. A stale cue AFTER the address applies to it only when no
    replacement cue stands between ('old@… is no longer valid' → historical; 'old@… was replaced by new@…' → old historical, new current)."""
    a, b = sentence
    before, after = text[a:span[0]], text[span[1]:b]
    nb = [m for m in _NEW_CUE.finditer(before)]
    sb = [m for m in _STALE_CUE.finditer(before)]
    if nb and (not sb or nb[-1].start() > sb[-1].start()):
        return "current", None
    if sb:
        return "historical", f"the passage says \"{sb[-1].group(0)}\" before the address"
    sa = _STALE_CUE.search(after)
    if sa:
        na = _NEW_CUE.search(after)
        if na is None or na.start() > sa.start() or "replaced" in sa.group(0).lower():
            return "historical", f"the passage says \"{sa.group(0)}\" about the address"
    if person_sentence:
        sp = _STALE_CUE.search(person_sentence)
        if sp:
            return "historical", f"the person is described as gone (\"{sp.group(0)}\")"
    return "current", None


# ----------------------------------------------------------------------------------------------- the page
def _mentions(text: str, names: list[str], org_names: Iterable[str]) -> list[tuple[int, int, str, bool]]:
    """(start, end, name, known) for every person named on the page: the known people, plus generic 'Firstname Lastname' pairs that are
    neither roles nor organisation names — enough to notice that *another* person stands between a name and an address."""
    out: list[tuple[int, int, str, bool]] = []
    for n in names:
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text, re.I):
            out.append((m.start(), m.end(), n, True))
    org_words = {w for o in org_names for w in name_tokens(o)}
    for m in _GENERIC_NAME.finditer(text):
        a, b = m.group(1), m.group(2)
        if any(x in _ROLE_WORDS or x in org_words for x in (_fold(a), _fold(b))):
            continue
        if any(s <= m.start() < e or s < m.end() <= e for s, e, _, _ in out):
            continue
        out.append((m.start(), m.end(), f"{a} {b}", False))
    out.sort()
    return out


def _sentence(text: str, pos: int) -> tuple[int, int]:
    left = 0
    for m in _SENT_END.finditer(text, 0, pos):
        left = m.end()
    m2 = _SENT_END.search(text, pos)
    return left, (m2.start() if m2 else len(text))


def _clean(s: str) -> str:
    return " ".join(s.split())[:300]


def attribute(text: str, names: list[str], *, org_domains: Iterable[str] = (), org_names: Iterable[str] = ()) -> list[Attribution]:
    text = text.replace("\r", "")
    names = [n for n in dict.fromkeys(n.strip() for n in names if n and n.strip())]
    org_domains = {d.lower().removeprefix("www.") for d in org_domains if d}
    org_names = [o for o in org_names if o]
    mentions = _mentions(text, names, org_names)
    lines: list[tuple[int, int]] = []
    pos = 0
    for ln in text.split("\n"):
        lines.append((pos, pos + len(ln)))
        pos += len(ln) + 1
    emails = list(EMAIL.finditer(text))
    email_spans = [(m.start(), m.end()) for m in emails]

    def line_of(p: int) -> int:
        for i, (x, y) in enumerate(lines):
            if x <= p <= y:
                return i
        return len(lines) - 1

    def names_in(x: int, y: int) -> list[tuple[int, int, str, bool]]:
        return [m for m in mentions if x <= m[0] and m[1] <= y]

    def emails_in(x: int, y: int, *, excluding: tuple[int, int]) -> bool:
        return any(x <= s0 and e0 <= y and (s0, e0) != excluding for s0, e0 in email_spans)

    def person_sentence(who: str, near: int) -> str | None:
        """The sentence naming the person closest before the address (for 'X has left the company')."""
        best = None
        for st, _en, n, _k in mentions:
            if n == who and st <= near:
                best = st
        if best is None:
            return None
        a0, b0 = _sentence(text, best)
        return text[a0:b0]

    out: list[Attribution] = []
    for m in emails:
        email = m.group(0).lower()
        if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
            continue
        span = (m.start(), m.end())
        kind, why = mailbox_kind(email)
        s_a, s_b = _sentence(text, m.start())
        sentence = text[s_a:s_b]
        context = text[max(0, s_a - 240):s_b]
        domain = email.split("@", 1)[1].removeprefix("www.")
        cur, cur_why = currency(text, span, (s_a, s_b))
        if kind == "shared":
            out.append(Attribution(email, None, "shared", "shared_mailbox", "none", _clean(sentence), why, department=_local(email),
                                   currency=cur, currency_reason=cur_why))
            continue
        press = bool(_PRESS_CUE.search(sentence)) or bool(_PRESS_CUE.search(context))
        supplier = bool(_SUPPLIER_CUE.search(sentence)) or bool(_SUPPLIER_CUE.search(text[max(0, s_a - 160):s_a]) and not _SENT_END.search(text[max(0, s_a - 2):s_a].replace(";", "")))
        foreign = bool(org_domains) and domain not in org_domains and not any(domain.endswith("." + d) for d in org_domains)
        relation = _RELATION_CUE.search(context) if foreign else None
        owners = [n for n in names if name_matches(email, n)]
        # structure: a table row, a labelled contact block, an explicit statement
        li = line_of(m.start())
        la, lb = lines[li]
        line = text[la:lb]
        tie: tuple[str, str, bool, str] | None = None       # (basis, name, known, quote)
        amb: list[str] = []
        if _CELL.search(line) and len(_CELL.split(line.strip())) >= 2:
            row_names = names_in(la, lb)
            if len(row_names) == 1:
                tie = ("table_row", row_names[0][2], row_names[0][3], _clean(line))
            elif len(row_names) > 1:
                amb = [n[2] for n in row_names]
        if tie is None and not amb:
            j, hops = li - 1, 0
            while j >= 0 and hops < 4:
                x, y = lines[j]
                raw = text[x:y]
                if not raw.strip():
                    if j < li - 1 and not text[lines[j + 1][0]:lines[j + 1][1]].strip():
                        break
                    j -= 1
                    continue
                hops += 1
                if emails_in(x, y, excluding=span):
                    break
                here = names_in(x, y)
                if here:
                    if len(here) == 1 and ((here[0][1] - here[0][0]) >= 0.3 * len(raw.strip()) or re.match(r"^\s*" + re.escape(here[0][2]), raw, re.I)):
                        tie = ("contact_block", here[0][2], here[0][3], _clean(text[x:lb]))
                    elif len(here) == 1 and not names_in(s_a, s_b):
                        tie = ("contact_block", here[0][2], here[0][3], _clean(text[x:lb]))
                    else:
                        amb = [n[2] for n in here]
                    break
                j -= 1
        if tie is None and not amb:
            before = [n for n in names_in(s_a, s_b) if n[1] <= m.start()]
            after = [n for n in names_in(s_a, s_b) if n[0] >= m.end()]
            if before:
                nearest = before[-1]
                between = text[nearest[1]:m.start()]
                if not emails_in(nearest[1], m.start(), excluding=span):
                    tie = ("explicit_statement", nearest[2], nearest[3], _clean(sentence))
                if re.search(r"\b(and|&)\s*$", between.strip()) or ("," in between and len(before) > 1 and re.search(r"\band\b", between)):
                    amb, tie = [n[2] for n in before[-2:]], None
            elif len(after) == 1 and not emails_in(m.end(), s_b, excluding=span):
                tie = ("explicit_statement", after[0][2], after[0][3], _clean(sentence))
            elif len(after) > 1:
                amb = [n[2] for n in after]
        if tie is None and not amb and not names_in(s_a, s_b):
            own = text[s_a:s_b]
            if (len(own.strip()) <= 120 or _LABEL.match(own)) and "\n\n" not in text[max(0, s_a - 2):s_a + 1]:
                p_a, p_b = _sentence(text, max(0, s_a - 2))
                if p_b <= s_a and "\n\n" not in text[p_b:s_a]:
                    prev = names_in(p_a, p_b)
                    if len(prev) == 1 and not emails_in(p_a, p_b, excluding=span):
                        tie = ("explicit_statement", prev[0][2], prev[0][3], _clean(text[p_a:s_b]))
                    elif len(prev) > 1:
                        amb = [n[2] for n in prev]

        def make(person: str | None, kind_: str, basis: str, conf: str, quote: str, reason: str, cands=(), supporting=(), about: str | None = None,
                 _at=(email, span, s_a, s_b, cur, cur_why)) -> Attribution:
            e_, sp_, a_, b_, c2, w2 = _at
            if about and c2 == "current":
                c2, w2 = currency(text, sp_, (a_, b_), person_sentence=person_sentence(about, sp_[0]))
            return Attribution(e_, person, kind_, basis, conf, quote, reason, candidates=list(cands), currency=c2, currency_reason=w2,
                               supporting=list(supporting))

        if tie:
            basis, who, known, quote = tie
            sup = [f"the local part is {who}'s own name"] if name_matches(email, who) else []
            other = matches_another(email, who, names)
            if other:
                out.append(make(None, "other_person", basis, "none", quote, f"the local part is {other}'s name, not {who}'s: not assigned to {who}", (who, other)))
                continue
            if kind == "name_like" and not name_matches(email, who) and len(_local_parts(_local(email))) >= 2:
                out.append(make(None, "other_person", basis, "ambiguous", quote,
                                f"the local part reads as another person's name ({'.'.join(_local_parts(_local(email)))}), not {who}'s: pending review", (who,)))
                continue
            if supplier and (foreign or not org_domains):
                out.append(make(None, "third_party", basis, "ambiguous" if known else "none", quote,
                                (f"the passage gives it as an outside supplier's or partner's contact ({domain}); the same name is not proof that it is "
                                 f"{who}'s at the company: pending review") if known else f"an outside supplier's or partner's contact ({who}, {domain})",
                                (who,) if known else (), sup))
                continue
            if press and foreign:
                out.append(make(None, "third_party", basis, "ambiguous" if known else "none", quote,
                                f"a press or agency contact on another domain ({domain}) beside {who}: pending review" if known
                                else f"a third-party press contact ({who}, {domain}), not a person at the company", (who,) if known else ()))
                continue
            if not known:
                out.append(make(None, "unassigned", basis, "none", quote, f"tied to {who}, who is not a person bound to the organisation by its pages", (who,)))
                continue
            if foreign and not relation:
                out.append(make(None, "investigate", basis, "ambiguous", quote,
                                f"tied to {who} on the page, but on another domain ({domain}) than the organisation's ({', '.join(sorted(org_domains))}) and the "
                                "passage does not explain the relationship: investigate before using it", (who,), sup, about=who))
                continue
            label = {"explicit_statement": f"stated in the same sentence as {who}, no other person between",
                     "contact_block": f"in {who}'s contact block", "table_row": f"in the row naming only {who}"}[basis]
            extra = list(sup) + ([f"another domain ({domain}), explained by the passage: '{relation.group(0)}'"] if relation else [])
            out.append(make(who, "personal", basis, "clear", quote, label, (), extra, about=who))
            continue
        if amb:
            known_amb = [n for n in dict.fromkeys(amb) if n in names]
            out.append(make(None, "unassigned", "none", "ambiguous" if known_amb else "none", _clean(sentence),
                            f"{len(dict.fromkeys(amb))} people share the passage ({', '.join(dict.fromkeys(amb))}); nothing ties the address to one: pending review",
                            known_amb))
            continue
        if owners:
            # a matching local part alone is never proof (a supplier's or partner's namesake, a reused address): pending review at most
            match_note = f"the local part matches {' and '.join(owners)}"
            if supplier or (press and foreign):
                reason = (f"{match_note}, but the passage gives it as an outside supplier's, partner's or agency's contact ({domain}): "
                          "not established as the person's at the company — pending review")
                out.append(make(None, "third_party", "none", "ambiguous", _clean(sentence), reason, owners, [match_note]))
            else:
                reason = (match_note + (" (several people share it)" if len(owners) > 1 else "") +
                          ", but nothing on the page states whose address it is" + (f"; it is on another domain ({domain})" if foreign else "") + ": pending review")
                out.append(make(None, "name_only", "none", "ambiguous", _clean(sentence), reason, owners, [match_note]))
            continue
        near = names_in(max(0, s_a - 1), s_b)
        out.append(make(None, "third_party" if (press or supplier) and foreign else "unassigned", "none", "none", _clean(sentence),
                        "a third-party or supplier contact on another domain" if (press or supplier) and foreign else "no person tied to the address on this page",
                        [n[2] for n in near if n[3]]))
    # a replacement named for a person's withdrawn address, in the same paragraph ("Do not use jb@… — no longer valid. Please write to new@…
    # instead."): the replacement is that person's current address — the page states the association
    spans = [(mm.start(), mm.end()) for mm in emails if not mm.group(0).lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"))]
    for i, at in enumerate(out):
        if at.person or at.kind not in ("unassigned",) or at.currency != "current" or i == 0:
            continue
        s0, _e0 = spans[i]
        a0, _b0 = _sentence(text, s0)
        if not _NEW_CUE.search(text[a0:s0]):
            continue
        prev = out[i - 1]
        ps, pe = spans[i - 1]
        if prev.person and prev.confidence == "clear" and prev.currency == "historical" and "\n\n" not in text[pe:s0] and not names_in(pe, s0):
            dom_ok = at.email.split("@", 1)[1] == prev.email.split("@", 1)[1]
            if dom_ok or not org_domains:
                out[i] = Attribution(at.email, prev.person, "personal", "explicit_statement", "clear", _clean(text[_sentence(text, ps)[0]:_sentence(text, s0)[1]]),
                                     f"named as the replacement of {prev.person}'s withdrawn address {prev.email}", currency="current",
                                     supporting=[f"replaces {prev.email} ({prev.currency_reason})"])
    return out


def for_person(attributions: list[Attribution], name: str, *, include_historical: bool = False) -> tuple[Attribution | None, list[Attribution]]:
    """(the clear, CURRENT attribution for this person, the ambiguous candidates naming them). Historical addresses are evidence, never a
    current route: returned here only with `include_historical`."""
    clear = [a for a in attributions if a.person == name and a.confidence == "clear" and (include_historical or a.currency == "current")]
    order = {"explicit_statement": 0, "table_row": 0, "contact_block": 1}
    clear.sort(key=lambda a: (order.get(a.basis, 9), -len(a.supporting)))
    pending = [a for a in attributions if a.person is None and a.confidence == "ambiguous" and name in a.candidates and a.currency == "current"]
    return (clear[0] if clear else None), pending


def historical_for(attributions: list[Attribution], name: str) -> list[Attribution]:
    """Addresses tied to this person (clearly, or as candidates) that the page marks obsolete, replaced, withdrawn or a former employee's."""
    return [a for a in attributions if a.currency == "historical" and (a.person == name or name in a.candidates)]


def currency_in(passage: str, email: str) -> tuple[str, str | None]:
    """The currency of an address inside a short passage (a company contact line): current, or historical with the reason."""
    m = re.search(re.escape(email), passage, re.I)
    if not m:
        return "current", None
    a, b = _sentence(passage, m.start())
    return currency(passage, (m.start(), m.end()), (a, b))
