"""Who holds which role, at which organisation, and on what evidence (instruction of 28 Oct 2026, items 2 and 3).

A person is linked to a role or an organisation only by text that binds them: the title or organisation stated next to the
name in the same clause ("Jane Doe, Head of Cargo at Example Air"), a possessive ("Example Air's Head of Cargo Jane Doe"),
an appointment ("Example Air has appointed Jane Doe as Head of Cargo"), or a listing on the organisation's own leadership
page. A title that appears elsewhere in the document, or an organisation that is merely mentioned in the same sentence, is
never attached to a person: the association stays unresolved.

Every mention keeps:
- the role and whether it is current, former or incoming;
- the organisation the text binds the person to, if any, and the person's relation to the organisation being researched
  (employee, board member, partner, customer, other organisation, or unknown);
- the passage that shows the role and, where different, the passage that shows the organisation;
- a plain explanation of the binding.

Being mentioned, quoted or listed is evidence of involvement only. Nothing here infers decision-making authority.
Framework-free; no I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from ..reference.geography import COUNTRIES
from .relationships import _NAME, _ROLE, _ROLE_LONG, _clean_name, classify_role

# Title words never start a person's name ("President Lars Holm" is a title and a name).
_TITLE_WORDS = {"president", "vice", "vp", "ceo", "cfo", "coo", "cco", "cio", "chairman", "chair", "chairperson", "executive", "lead",
                "leader", "coordinator", "controller", "specialist", "representative", "secretary", "commissioner", "consultant", "adviser",
                "advisor", "analyst", "founder", "supervisor", "planner", "buyer", "administrator", "engineer", "minister", "deputy",
                "acting", "interim", "senior", "principal", "regional", "country", "station", "area", "former", "outgoing", "incoming"}
# Country names (single words) are never the first or last word of a person's name.
_PLACES = {n.lower() for v in COUNTRIES.values() for n in [v[0]] if " " not in n} | {"africa", "asia", "europe", "gulf", "nairobi",
                                                                                       "kampala", "mombasa", "dubai", "entebbe"}

# ------------------------------------------------------------------ vocabulary
_ORG_SUFFIX = (r"(?:Airways|Airlines|Air(?:\s+Cargo)?|Aviation|Authority|Airport|Airports|Ltd|Limited|Group|Company|Corporation|"
               r"Inc|LLC|PLC|SA|AG|GmbH|Logistics|Freight|Holdings|Ministry|Agency|Services|Handling|Partners|Board|Council|"
               r"Commission|Bank|Fund|Cargo|Express|Shipping|Lines|Port|Ports)")
# A capitalised organisation phrase: "Kenya Civil Aviation Authority", "Savanna Example Air", "Blue Nile Cargo Partners Ltd"
_ORG = r"(?:[A-Z][\w&'’.\-]*)(?:\s+(?:(?:of|for|and|de|du|&)\s+)?[A-Z][\w&'’.\-]*){0,7}"
_FORMER = r"(?i:former|ex-|outgoing|previous|retired|then)"
_INCOMING = r"(?i:incoming|new|newly[- ]appointed|designate)"
_SAYS = r"(?:said|says|added|stated|commented|explained|noted|confirmed)"
_APPOINT = (r"(?:has\s+appointed|have\s+appointed|appointed|appoints|has\s+named|named|names|has\s+hired|hired|hires|welcomes|"
            r"has\s+welcomed|announced\s+the\s+appointment\s+of|announces\s+the\s+appointment\s+of|has\s+announced\s+the\s+appointment\s+of|"
            r"confirmed\s+the\s+appointment\s+of|has\s+promoted|promoted)")
_SUCCEED = r"(?:succeeds|succeeding|replaces|replacing|takes\s+over\s+from|taking\s+over\s+from|who\s+succeeds|who\s+replaces)"
_FUTURE = re.compile(r"\b(?:effective|with effect from|from \d{1,2} [A-Z][a-z]+|will (?:take up|assume|join|start)|starting|as of \d)", re.I)
_PARTNER = re.compile(r"\b(?:partner|partnership|alliance|joint venture|agent for|general sales agent|gsa|gssa)\b", re.I)
_CUSTOMER = re.compile(r"\b(?:customer|client|shipper)s?\b", re.I)
_QUOTE_MARKS = re.compile(r"[\"“”]")
_ABBREV = re.compile(r"\b(Mr|Mrs|Ms|Dr|Capt|St|Inc|Ltd|Co|No|Jr|Sr|Prof|Gen|Col|Lt|Rev|Hon|Messrs|e\.g|i\.e|U\.S|U\.K)\.")
_LEADERSHIP_PAGE = re.compile(r"leader|management|executive|our[- ]team|/team|people|who[- ]we[- ]are|board|director", re.I)
_BOARD_PAGE = re.compile(r"board", re.I)
_LISTING_SEP = r"\s*(?:[–—|:]|-|,)\s*"

AFFILIATIONS = ("employee", "board_member", "partner", "customer", "other_organisation", "unknown")
AFFILIATION_LABELS = {
    "employee": "Works at the organisation",
    "board_member": "Board member",
    "partner": "Partner organisation",
    "customer": "Customer organisation",
    "other_organisation": "Another organisation (quoted or mentioned)",
    "unknown": "Organisation not established",
}
ROLE_STATUS_LABELS = {"current": "current", "former": "former", "incoming": "incoming"}


@dataclass
class Mention:
    name: str
    role: str | None
    role_status: str                       # current | former | incoming
    organisation: str | None               # as written in the text (or the page owner for a listing)
    affiliation: str                       # relation to the organisation being researched: see AFFILIATIONS
    quote: str                             # the passage that binds the role (or names the person)
    binding: str                           # plain explanation of what links the person to the role / organisation
    pattern: str
    org_quote: str | None = None           # a separate passage that binds the organisation, when it is not `quote`
    role_on_opportunity: str = "named_in_source"
    relevance_basis: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def role_label(self) -> str | None:
        if not self.role:
            return None
        return self.role if self.role_status == "current" else f"{self.role} ({self.role_status})"


# ------------------------------------------------------------------ helpers
def sentences(text: str) -> list[tuple[int, str]]:
    """(offset, sentence) pairs. Lines are boundaries; common abbreviations never end a sentence."""
    out: list[tuple[int, str]] = []
    for line_m in re.finditer(r"[^\n]+", text):
        line, base = line_m.group(0), line_m.start()
        protected = _ABBREV.sub(lambda m: m.group(0).replace(".", "\x00"), line)
        start = 0
        for m in re.finditer(r"(?<=[.!?])[\"”’)]?\s+(?=[\"“‘(A-Z0-9])", protected):
            seg = protected[start:m.end()].rstrip()
            if seg.strip():
                out.append((base + start, seg.replace("\x00", ".")))
            start = m.end()
        tail = protected[start:]
        if tail.strip():
            out.append((base + start, tail.replace("\x00", ".")))
    return out


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("’", "'").split())


class _Orgs:
    """Known organisation names (from the opportunity) take precedence over capitalised phrases."""

    def __init__(self, names: Iterable[str]):
        self.names = sorted({n.strip() for n in names if n and len(n.strip()) >= 2}, key=len, reverse=True)
        self.alt = "|".join(re.escape(n) for n in self.names) or r"(?!x)x"
        self.known_rx = re.compile(rf"(?i:{self.alt})")

    def canonical(self, phrase: str | None) -> str | None:
        """The known name a phrase refers to, else the phrase itself (trimmed), else None."""
        if not phrase:
            return None
        p = phrase.strip(" ,.;:'’").removeprefix("the ").removeprefix("The ")
        p = re.sub(r"(?:'s|’s)$", "", p).strip()
        for n in self.names:
            if _norm(n) == _norm(p) or _norm(p).startswith(_norm(n) + " ") and len(p) - len(n) <= 4:
                return n
        return p if len(p) >= 2 else None

    def is_known(self, phrase: str | None) -> bool:
        return bool(phrase) and any(_norm(n) == _norm(self.canonical(phrase) or "") for n in self.names)

    def org_rx(self) -> str:
        return rf"(?:(?i:{self.alt})|{_ORG})"


def _split_role_org(role: str, orgs: _Orgs) -> tuple[str, str | None]:
    """'Director General of the Kenya Civil Aviation Authority' stays a title unless its 'of/at X' tail is an organisation:
    a known name, or a phrase ending in an organisation word. 'Head of Cargo' keeps 'of Cargo' (a unit, not an organisation)."""
    m = re.match(r"^(?P<title>.+?)\s+(?:at|of|for|with)\s+(?:the\s+)?(?P<org>[A-Z].+)$", role)
    if not m:
        return role, None
    tail = m.group("org").strip()
    # a bare unit word ("of Cargo", "of Sales") is part of the title; an organisation needs a known name or 2+ words ending
    # in an organisation word ("of the Kenya Civil Aviation Authority")
    if orgs.is_known(tail) or (len(tail.split()) >= 2 and re.search(rf"\b{_ORG_SUFFIX}$", tail)):
        title = m.group("title").strip()
        # 'Head of Cargo at Example Air' -> ('Head of Cargo', 'Example Air'); never strip to a bare qualifier
        if re.search(r"(Head|Director|Manager|Officer|Chief|President|Executive|Lead|Leader|Representative|Secretary|"
                     r"Commissioner|Coordinator|Controller|Specialist|Superintendent|Chairman|Chair|VP|CEO|CCO|COO|CFO|CIO)", title):
            return title, orgs.canonical(tail)
    return role, None


def _affiliation(org: str | None, subject_orgs: _Orgs, sentence: str, *, board: bool = False) -> str:
    """The person's relation to the organisation being researched. Partner or customer only when the sentence describes
    THEIR organisation that way, right after naming it ("Blue Ridge Handling, Savanna Example Air's handling partner")."""
    if not org:
        return "unknown"
    if subject_orgs.is_known(org):
        return "board_member" if board else "employee"
    at = _norm(sentence).find(_norm(org))
    if at != -1:
        after = _norm(sentence)[at + len(_norm(org)):at + len(_norm(org)) + 70]
        described = re.match(r"^\s*(?:,|\(|–|-)\s*(?:the\s+|a\s+|an\s+|its\s+|[\w' ]+'s\s+)?(?P<desc>[^,.;)]*)", after)
        desc = described.group("desc") if described else ""
        if _PARTNER.search(desc):
            return "partner"
        if _CUSTOMER.search(desc):
            return "customer"
    return "other_organisation"


def _trim_role(role: str | None) -> str | None:
    if not role:
        return None
    r = re.sub(r"^(?:the|its|their|our|a|an)\s+", "", role.strip(" ,;()"), flags=re.I)
    r = re.sub(r"\s+(?:said|says|added|stated|commented|explained|noted|confirmed|and|who|will|has|is|was)\b.*$", "", r)
    return (r[:90].rsplit(" ", 1)[0] if len(r) > 90 else r) or None


# ------------------------------------------------------------------ the parser
class _Parser:
    def __init__(self, text: str, organisation_names: Iterable[str], subject_orgs: Iterable[str], page_org: str | None,
                 page_kind: str | None, page_url: str | None):
        self.text = text
        self.orgs = _Orgs(list(organisation_names) + list(subject_orgs) + ([page_org] if page_org else []))
        self.subject = _Orgs(list(subject_orgs) + ([page_org] if page_org else []))
        self.page_org, self.page_kind, self.page_url = page_org, page_kind, page_url
        OX = self.orgs.org_rx()  # noqa: N806 - short pattern names keep the expressions readable
        acting = r"(?:(?:acting|interim|deputy)\s+)?"
        R, RL = acting + _ROLE, acting + _ROLE_LONG  # noqa: N806
        self.rx_name = re.compile(_NAME)
        # after the name ------------------------------------------------------------
        self.r_role_org = re.compile(rf"^\s*,\s*(?:the\s+)?(?:(?P<mod>{_FORMER}|{_INCOMING}|currently|now)\s+)?(?P<role>{RL})\s*,?\s+(?P<prep>at|of|for|with)\s+"
                                     rf"(?:the\s+)?(?P<org>{OX})")
        self.r_org_role = re.compile(rf"^\s*,\s*(?:the\s+)?(?:(?P<mod>{_FORMER}|{_INCOMING})\s+)?(?P<org>(?i:{self.orgs.alt}))(?:'s|’s)?\s+"
                                     rf"(?P<role>{RL})")
        self.r_role = re.compile(rf"^\s*[,(]\s*(?:the\s+)?(?:(?P<mod>{_FORMER}|{_INCOMING}|currently|now)\s+)?(?P<role>{RL})(?:\s*,\s*(?P<org>(?i:{self.orgs.alt})))?")
        # "<Name> was Cargo Sales Manager at Savanna Example Air" / "<Name> is Head of Cargo at ..." / "<Name> served as ..."
        self.r_was = re.compile(rf"^\s*,?\s+(?P<verb>was|had\s+been|served\s+as|is|has\s+been|serves\s+as|remains)\s+(?:the\s+|its\s+)?"
                                rf"(?P<role>{RL})(?:\s+(?:at|of|for|with)\s+(?:the\s+)?(?P<org>{OX}))?")
        self.r_appointed = re.compile(rf"^\s*,?\s+(?:has\s+been|have\s+been|was|is|will\s+be)\s+(?:appointed|named|promoted\s+to|confirmed)\s+"
                                      rf"(?:as\s+)?(?:the\s+)?(?:new\s+)?(?P<role>{R})(?:\s+(?:at|of|for)\s+(?:the\s+)?(?P<org>{OX}))?")
        self.r_joins = re.compile(rf"^\s+(?P<will>will\s+join|is\s+to\s+join|joins|joined|has\s+joined)\s+(?:the\s+)?(?P<org>{OX})\s+as\s+"
                                  rf"(?:its\s+|the\s+|a\s+)?(?:new\s+)?(?P<role>{RL})")
        self.r_previously = re.compile(rf"^\s*,\s*who\s+(?:previously|formerly|until\s+\w+\s+\d{{4}})\s+(?:served|worked|was)\s+(?:as\s+)?(?:the\s+)?"
                                       rf"(?P<role>{R})(?:\s+(?:at|of|for|with)\s+(?:the\s+)?(?P<org>{OX}))?")
        self.r_of_org = re.compile(rf"^\s+(?:of|from|at)\s+(?P<org>(?i:{self.orgs.alt}))\b")
        self.r_as_role = re.compile(rf"^\s+(?:as|to)\s+(?:its\s+|the\s+|their\s+)?(?:new\s+)?(?P<role>{RL})")
        self.l_whose = re.compile(rf"(?P<org>(?i:{self.orgs.alt})),?\s+whose\s+(?:(?P<mod>{_FORMER}|{_INCOMING})\s+)?(?P<role>{RL})\s+$")
        # before the name -------------------------------------------------------------
        self.l_possessive = re.compile(rf"(?:(?P<mod0>{_FORMER}|{_INCOMING})\s+)?(?P<org>(?i:{self.orgs.alt}))(?:'s|’s)?\s+"
                                       rf"(?:(?P<mod>{_FORMER}|{_INCOMING})\s+)?(?P<role>{RL})\s*,?\s*$")
        self.l_role_at_org = re.compile(rf"(?:^|\b)(?:the\s+)?(?:(?P<mod>{_FORMER}|{_INCOMING})\s+)?(?P<role>{R})\s+(?:at|of)\s+(?:the\s+)?"
                                        rf"(?P<org>{OX})\s*,\s*$")
        self.l_appoint = re.compile(rf"(?P<org>{OX})\s+{_APPOINT}\s+(?:its\s+|the\s+)?(?:(?:new|former)\s+)?$")
        self.l_succeed = re.compile(rf"\b{_SUCCEED}\s+(?:the\s+)?(?:{_FORMER}\s+)?$")
        self.l_role = re.compile(rf"(?:(?P<mod>{_FORMER}|{_INCOMING})\s+)?(?P<role>{RL})\s+$")
        self.l_contact = re.compile(r"(?i:\b(?:contact(?:\s+(?:person|officer|point))?|enquiries\s+to|queries\s+to|attention))\s*[:\-–]\s*$")
        self.l_said = re.compile(rf"\b{_SAYS}\s+$")

    # ..............................................................................
    def run(self) -> list[Mention]:
        found: dict[tuple[str, str | None, str], Mention] = {}

        def keep(m: Mention) -> None:
            k = (m.name.lower(), (m.role or "").lower() or None, m.role_status)
            cur = found.get(k)
            if cur is None or (not cur.organisation and m.organisation):
                found[k] = m

        for m in self.listing():
            keep(m)
        for _off, sent in sentences(self.text):
            for m in self.in_sentence(sent):
                keep(m)
        # a name with a bound role must not also appear as a role-less mention of the same status
        out = list(found.values())
        roled = {(m.name.lower(), m.role_status) for m in out if m.role}
        out = [m for m in out if m.role or (m.name.lower(), m.role_status) not in roled]
        return out

    # ..............................................................................
    def listing(self) -> list[Mention]:
        """'Name' followed by 'Title' (or 'Name – Title') on the organisation's own leadership, team or board page."""
        if not (self.page_org and self.page_kind == "leadership"):
            return []
        board = bool(_BOARD_PAGE.search(self.page_url or "")) or bool(_BOARD_PAGE.search(self.text[:200]))
        lines = [ln.strip() for ln in self.text.splitlines()]
        out: list[Mention] = []
        full_name = re.compile(rf"^{_NAME}$")
        inline = re.compile(rf"^(?P<name>{_NAME}){_LISTING_SEP}(?P<role>{_ROLE_LONG})$")
        role_only = re.compile(rf"^(?P<role>{_ROLE_LONG})$")
        for i, ln in enumerate(lines):
            name = role = None
            quote = ln
            mi = inline.match(ln)
            if mi:
                name, role = _clean_name(mi.group("name")), mi.group("role")
            elif full_name.match(ln):
                nxt = next((x for x in lines[i + 1:i + 3] if x), "")
                mr = role_only.match(nxt)
                if mr:
                    name, role, quote = _clean_name(ln), mr.group("role"), f"{ln} — {nxt}"
            if not name or self.orgs.is_known(name):
                continue
            role = _trim_role(role)
            aff = "board_member" if board else "employee"
            out.append(Mention(name, role, "current", self.page_org, aff, quote,
                               f"listed with this title on {self.page_org}'s own {'board' if board else 'leadership or team'} page",
                               "listing", None, classify_role(role)))
        return out

    # ..............................................................................
    def in_sentence(self, sent: str) -> list[Mention]:
        out: list[Mention] = []
        appointment_org: str | None = None
        appointment_role: str | None = None
        for start, end, name in self.names_in(sent):
            before, after = sent[:start], sent[end:]
            for m in self._bind_all(name, before, after, sent):
                if m.pattern == "appointment":
                    appointment_org, appointment_role = m.organisation, m.role
                out.append(m)
        # "... appointed Jane Doe as Head of Cargo, succeeding John Smith": the successor binding needs the appointment's role
        for m in out:
            if m.pattern == "succeeded" and appointment_role and not m.role:
                m.role, m.organisation = appointment_role, m.organisation or appointment_org
                m.affiliation = _affiliation(m.organisation, self.subject, sent)
                m.binding = (f"named as the person being succeeded in the appointment of a new {appointment_role}"
                             + (f" at {m.organisation}" if m.organisation else ""))
                m.role_on_opportunity = classify_role(m.role)
        return out

    def names_in(self, sent: str) -> list[tuple[int, int, str]]:
        """Person names, tried at every capitalised word so a preceding title or organisation ("Chief Commercial Officer
        Amina Yusuf") cannot swallow the name. A known organisation name is never a person."""
        out: list[tuple[int, int, str]] = []
        anchored = re.compile(_NAME)
        pos = 0
        org_spans = [(m.start(), m.end()) for m in self.orgs.known_rx.finditer(sent)]
        for w in re.finditer(r"(?<![\w'’-])[A-Z]", sent):
            if w.start() < pos or any(a <= w.start() < b for a, b in org_spans):
                continue
            m = anchored.match(sent, w.start())
            if not m:
                continue
            raw = m.group(0)
            # try the longest name first, then drop trailing tokens ("Amina Yusuf Said" is not a name)
            toks = raw.split()
            if toks[0].lower() in _PLACES:
                continue                     # "Country Manager Uganda Paul Ssenyonga": a place never starts a name
            for n in range(len(toks), 1, -1):
                cand = " ".join(toks[:n])
                name = _clean_name(cand)
                if name and (toks[n - 1].lower() in _PLACES or toks[0].lower() in _TITLE_WORDS):
                    continue
                if name and not self.orgs.is_known(name) and not self.orgs.known_rx.fullmatch(cand):
                    end = sent.find(toks[n - 1], w.start()) + len(toks[n - 1])
                    out.append((w.start(), end, name))
                    pos = end
                    break
        return out

    def _bind_all(self, name: str, before: str, after: str, sent: str) -> list[Mention]:
        first = self._bind(name, before, after, sent)
        out = [first] if first else []
        # a second statement about the same person later in the clause: "..., former X at A, joined B as Y"
        nxt = re.search(r"(?<![A-Z][a-z])\b(?:has\s+joined|joined|joins|will\s+join)\b", after)
        if first and nxt and first.pattern != "joins" and not self.names_in(after[:nxt.start()]):
            rj = self.r_joins.match(" " + after[nxt.start():])
            if rj:
                status = "incoming" if rj.group("will").startswith(("will", "is")) else "current"
                out.append(self._mk(name, rj.group("role"), status, rj.group("org"), sent, "stated as joining this organisation in this title",
                                    "joins"))
        return out

    def _mk(self, name: str, role: str | None, status: str, org: str | None, sent: str, binding: str, pattern: str,
            *, contact: bool = False) -> Mention:
        role = _trim_role(role)
        if role:
            role, split_org = _split_role_org(role, self.orgs)
            org = org or split_org
        org = self.orgs.canonical(org)
        aff = _affiliation(org, self.subject, sent)
        kind = "procurement_contact" if contact and not role else classify_role(role) if role else "named_in_source"
        if contact and role and classify_role(role) == "named_in_source":
            kind = "procurement_contact"
        return Mention(name, role, status, org, aff, " ".join(sent.split())[:400], binding, pattern, None, kind)

    def _status(self, mod: str | None, default: str = "current") -> str:
        if not mod:
            return default
        return "former" if re.match(_FORMER, mod, re.I) else "incoming" if re.match(_INCOMING, mod, re.I) else default

    def _bind(self, name: str, before: str, after: str, sent: str) -> Mention | None:
        # --- appointment: "<Org> has appointed <Name> as <Role>" -------------------------------------------------
        la = self.l_appoint.search(before)
        if la:
            ra = self.r_as_role.match(after)
            if ra:
                status = "incoming" if _FUTURE.search(sent) else "current"
                return self._mk(name, ra.group("role"), status, la.group("org"), sent,
                                f"appointment announced: {self.orgs.canonical(la.group('org'))} appointed this person as the title stated",
                                "appointment")
        # --- succeeded: "... succeeding <Name>" -> former holder ---------------------------------------------------
        if self.l_succeed.search(before):
            m = self._mk(name, None, "former", None, sent, "named as the person being succeeded", "succeeded")
            return m
        # --- "<Name> has been appointed <Role> (at <Org>)" ---------------------------------------------------------
        ra = self.r_appointed.match(after)
        if ra:
            status = "incoming" if _FUTURE.search(sent) or "will be" in ra.group(0) else "current"
            return self._mk(name, ra.group("role"), status, ra.group("org"), sent,
                            "stated as appointed to this title" + (" at this organisation" if ra.group("org") else ""), "appointed")
        # --- "<Name> joins <Org> as <Role>" -------------------------------------------------------------------------
        rj = self.r_joins.match(after)
        if rj:
            status = "incoming" if rj.group("will").startswith(("will", "is")) or _FUTURE.search(sent) else "current"
            return self._mk(name, rj.group("role"), status, rj.group("org"), sent, "stated as joining this organisation in this title",
                            "joins")
        # --- "<Name>, who previously served as <Role> at <Org>" ----------------------------------------------------
        rp = self.r_previously.match(after)
        if rp:
            return self._mk(name, rp.group("role"), "former", rp.group("org"), sent, "stated as a previous title", "previously")
        # --- "<Org>, whose <Role> <Name> ..." -------------------------------------------------------------------------
        lw = self.l_whose.search(before)
        if lw:
            return self._mk(name, lw.group("role"), self._status(lw.group("mod")), lw.group("org"), sent,
                            "title stated for this organisation immediately before the name ('whose')", "whose")
        # --- "<Org>'s <Role> <Name>" ----------------------------------------------------------------------------------
        lp = self.l_possessive.search(before)
        if lp:
            return self._mk(name, lp.group("role"), self._status(lp.group("mod") or lp.group("mod0")), lp.group("org"), sent,
                            "title and organisation stated immediately before the name (possessive)", "possessive")
        # --- "the <Role> at <Org>, <Name>," -----------------------------------------------------------------------------
        lr = self.l_role_at_org.search(before)
        if lr and re.match(r"^\s*[,.;]|\s+" + _SAYS, after):
            return self._mk(name, lr.group("role"), self._status(lr.group("mod")), lr.group("org"), sent,
                            "title and organisation stated immediately before the name", "role_at_org")
        contact = bool(self.l_contact.search(before))
        # --- "<Name>, <Role> at|of <Org>" ---------------------------------------------------------------------------------
        r1 = self.r_role_org.match(after)
        # "Head of Procurement": after "of"/"for", a capitalised phrase is part of the title unless it is a known organisation or
        # reads as one (two or more words ending in an organisation word); "at"/"with" always introduce the organisation.
        if r1 and r1.group("prep") in ("of", "for") and not (self.orgs.is_known(r1.group("org")) or
                                                              (len(r1.group("org").split()) >= 2 and re.search(rf"\b{_ORG_SUFFIX}$", r1.group("org")))):
            r1 = None
        if r1:
            role, org = r1.group("role"), r1.group("org")
            return self._mk(name, role, self._status(r1.group("mod")), org, sent,
                            "title and organisation stated next to the name in the same clause", "name_role_org", contact=contact)
        # --- "<Name>, <Org>'s <Role>" ----------------------------------------------------------------------------------------
        r2 = self.r_org_role.match(after)
        if r2:
            return self._mk(name, r2.group("role"), self._status(r2.group("mod")), r2.group("org"), sent,
                            "organisation and title stated next to the name in the same clause", "name_org_role", contact=contact)
        # --- "<Name>, <Role>" / "<Name> (<Role>, <Org>)" --------------------------------------------------------------------
        r3 = self.r_role.match(after)
        if r3:
            org = r3.groupdict().get("org")
            return self._mk(name, r3.group("role"), self._status(r3.group("mod")), org, sent,
                            ("title" + (" and organisation" if org else "") + " stated next to the name; "
                             + ("organisation bound in the same parenthesis or clause" if org else "no organisation stated with it")),
                            "name_role", contact=contact)
        # --- "<Name> was <Role> at <Org>" / "<Name> is <Role> at <Org>" ---------------------------------------------------------
        rw = self.r_was.match(after)
        if rw:
            past = rw.group("verb").startswith(("was", "had", "served"))
            return self._mk(name, rw.group("role"), "former" if past else "current", rw.group("org"), sent,
                            ("stated as a previous title" if past else "stated as the person's title") +
                            (" at this organisation" if rw.group("org") else "; no organisation stated with it"), "was")
        # --- "<Role> <Name> said" ---------------------------------------------------------------------------------------------
        lr2 = self.l_role.search(before)
        if lr2 and re.match(rf"^\s*(?:[.,;]|$|\s+{_SAYS}\b)", after):
            return self._mk(name, lr2.group("role"), self._status(lr2.group("mod")), None, sent,
                            "title stated immediately before the name; no organisation stated with it", "role_name")
        # --- "<Name> of <Org>" (organisation only) ------------------------------------------------------------------------------
        ro = self.r_of_org.match(after)
        if ro:
            return self._mk(name, None, "current", ro.group("org"), sent, "organisation stated next to the name; no title stated",
                            "name_of_org", contact=contact)
        if contact:
            return self._mk(name, None, "current", None, sent, "named as the contact for this notice; no title or organisation stated",
                            "contact", contact=True)
        return None


def mentions(text: str, organisation_names: Iterable[str] = (), *, subject_orgs: Iterable[str] = (), page_org: str | None = None,
             page_kind: str | None = None, page_url: str | None = None) -> list[Mention]:
    """People the text binds to a role and/or an organisation, with the binding evidence.

    organisation_names: organisations known to be involved (never read as person names; preferred when matching).
    subject_orgs: the organisation(s) being researched; `affiliation` is relative to them.
    page_org / page_kind: when the text is a page on an organisation's own website ("leadership" for leadership, team,
    management or board pages); only then is a plain listing read as that organisation's people.
    """
    p = _Parser(text, organisation_names, subject_orgs, page_org, page_kind, page_url)
    out = p.run()
    for m in out:
        m.relevance_basis = _basis(m)
    return out


def _basis(m: Mention) -> str:
    parts = []
    if m.pattern == "contact" or (m.role_on_opportunity == "procurement_contact" and m.pattern in ("name_role", "contact")):
        parts.append("named as the contact for this notice")
    if m.role:
        parts.append(f"{m.role_status} title '{m.role}'" if m.role_status != "current" else f"title '{m.role}'")
    if m.organisation:
        parts.append(f"{AFFILIATION_LABELS[m.affiliation].lower()}: {m.organisation}")
    else:
        parts.append("organisation not established by this passage")
    parts.append(m.binding)
    return "; ".join(parts) + "; decision-making authority is not established by this mention"


def page_kind(url: str, title: str | None, anchor: str | None = None) -> str:
    """'leadership' for leadership, management, team, people and board pages; 'news' for newsrooms and articles; else 'other'."""
    hay = f"{url} {title or ''} {anchor or ''}"
    if _LEADERSHIP_PAGE.search(hay):
        return "leadership"
    if re.search(r"news|press|media|release|announce|stories|blog", hay, re.I):
        return "news"
    return "other"


def binding_confirms(quote: str, name: str, role: str | None, organisation: str | None, organisation_names: Iterable[str]) -> tuple[bool, bool]:
    """For a reading proposed by the AI extractor: does the quoted passage itself bind this person to the proposed role, and
    to the proposed organisation? Returns (role_bound, organisation_bound). The rule parser is the arbiter."""
    found = [m for m in mentions(quote, organisation_names, subject_orgs=organisation_names) if _norm(m.name) == _norm(name)]
    role_ok = role is not None and any(m.role is not None and (_norm(role) in _norm(m.role) or _norm(m.role) in _norm(role)) for m in found)
    org_ok = organisation is not None and any(m.organisation is not None and _norm(m.organisation) == _norm(organisation) for m in found)
    return role_ok, org_ok
