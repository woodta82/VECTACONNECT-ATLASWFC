"""Relationship intelligence rules (28 Oct 2026 refocus). Framework-free.

Principles carried through every function:
- A person's research state is DERIVED from recorded facts; it is never typed in:
    research_candidate      -> found, identity or role not yet confirmed by a person
    identity_confirmed      -> a person confirmed who they are and their role, with a basis
    introduction_available  -> a route whose introducer relationship AND willingness are confirmed
    existing_relationship   -> someone at WFC holds a current relationship, with a basis
- Being named in an announcement is evidence of involvement, not of decision-making authority.
- A public association between two people is at most a POSSIBLE introduction route.
- A generated LinkedIn search link is a search suggestion, never a researched or confirmed identity.
- No win probabilities are computed. The relationship HEALTH score (domain/relationship_health.py, 29 Oct 2026, the ATLAS v1.0
  parameters) measures the upkeep of a relationship from recorded engagements and the team's own stakeholder judgements, with
  its breakdown shown wherever it appears; it never changes a derived state and is never a probability of winning.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

STATES = ("research_candidate", "identity_confirmed", "introduction_available", "existing_relationship")
STATE_LABELS = {
    "research_candidate": "Research candidate",
    "identity_confirmed": "Identity and role confirmed",
    "introduction_available": "Introduction available",
    "existing_relationship": "Existing relationship",
    "merged": "Merged into another record",
}

LINKEDIN_PEOPLE_SEARCH = "https://www.linkedin.com/search/results/people/?keywords="
_PROFILE_URL = re.compile(r"^https://(?:www\.|[a-z]{2}\.)?linkedin\.com/in/([^/?#]+)/?$")


def derive_state(*, identity_confirmed: bool, current_relationships: int, available_routes: int) -> str:
    if current_relationships > 0:
        return "existing_relationship"
    if available_routes > 0:
        return "introduction_available"
    if identity_confirmed:
        return "identity_confirmed"
    return "research_candidate"


# ------------------------------------------------------------------ LinkedIn
def linkedin_search_url(*parts: str | None) -> str:
    """A LinkedIn people-search link a person opens and reviews themselves. Not a profile, not an API call."""
    words = " ".join(p.strip() for p in parts if p and p.strip())
    return LINKEDIN_PEOPLE_SEARCH + urllib.parse.quote(words)


def normalise_profile_url(url: str) -> str:
    """Accepts only a public LinkedIn member profile URL (https://[www.|xx.]linkedin.com/in/<slug>) and returns its
    canonical form. Raises ValueError for anything else: search pages, company pages and other sites are not profiles."""
    u = url.strip()
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    u = u.split("?", 1)[0].split("#", 1)[0]
    m = _PROFILE_URL.match(u)
    if not m:
        raise ValueError("not a LinkedIn member profile URL (expected https://www.linkedin.com/in/<name>)")
    return f"https://www.linkedin.com/in/{m.group(1)}/"


# ------------------------------------------------------------------ roles to look for, by capability category
@dataclass(frozen=True)
class TargetRole:
    key: str                      # role_on_opportunity
    label: str
    search_terms: tuple[str, ...]  # used in LinkedIn searches together with the organisation and country


_PROC = TargetRole("procurement_contact", "Procurement or tender contact", ("procurement", "tender"))
_COMM = TargetRole("commercial_leader", "Head of cargo / commercial leader", ("head of cargo", "cargo director", "commercial director"))
_REG = TargetRole("regional_representative", "Country or regional representative", ("country manager", "regional manager"))
_OPS = TargetRole("department_lead", "Operations or ground handling lead", ("ground operations", "cargo operations"))
_HR = TargetRole("department_lead", "Training or learning lead", ("training manager", "learning and development"))
_FIN = TargetRole("department_lead", "Finance or revenue accounting lead", ("revenue accounting", "finance director"))
_TECH = TargetRole("department_lead", "Digital or IT lead", ("digital", "chief information officer"))
_NET = TargetRole("partner", "Partner or agency principal", ("managing director", "general manager"))

TARGET_ROLES: dict[str, tuple[TargetRole, ...]] = {
    "airline_representation": (_PROC, _COMM, _REG),
    "account_growth": (_COMM, _REG),
    "forwarder_sales": (_COMM, _REG),
    "capacity_lanes": (_COMM, _REG),
    "service_operations": (_OPS, _COMM),
    "trucking_gateways": (_OPS, _COMM),
    "outsourcing_training": (_PROC, _HR, _FIN, _OPS),
    "technology_solutions": (_TECH, _COMM),
    "network_development": (_NET, _REG),
}


def target_roles(module: str) -> tuple[TargetRole, ...]:
    return TARGET_ROLES.get(module, (_PROC, _COMM, _REG))


# ------------------------------------------------------------------ people named in source text
_ROLE_WORDS = (r"(?:Head|Director|Manager|Officer|Chief|President|Vice[- ]President|VP|CEO|CCO|COO|CFO|CIO|Chairman|Chair|"
               r"Executive|Lead|Leader|Coordinator|Controller|Superintendent|Specialist|Representative|Secretary|Commissioner|Consultant|"
               r"Adviser|Advisor|Analyst|Founder|Supervisor|Planner|Buyer|Administrator|Engineer)")
_NAME_TOKEN = r"(?:[A-Z]['’][A-Z][a-z]+|[A-Z][a-z]+(?:-[A-Z][a-z]+)?)"
_PARTICLE = r"(?:al|bin|van|von|de|da|del|di|le|la)"
# A name stays on one line: a heading above it must never be read as a first name.
_NAME = rf"(?:(?:Mr|Mrs|Ms|Dr|Capt|Captain)\.?[ \t]+)?{_NAME_TOKEN}(?:[ \t]+(?:{_PARTICLE}[- ])?{_NAME_TOKEN}){{1,3}}"
_CAP = r"[A-Z][A-Za-z&\-]+"
# A stated title: up to four capitalised qualifiers, a role word, an optional "General", an optional "of/for <Unit>".
_ROLE = (rf"(?:{_CAP}\s+){{0,4}}{_ROLE_WORDS}(?:\s+General)?"
         rf"(?:\s+(?:of|for)\s+(?:the\s+)?{_CAP}(?:\s+{_CAP}){{0,5}})?")
# After a name and a comma the title may run on ("Vice President Cargo Sales"), since no name follows it.
_ROLE_LONG = rf"{_ROLE}(?:\s+{_CAP}){{0,3}}"

# 1. "Contact: Jane Smith, Procurement Manager" / "Enquiries to: Peter Otieno (Senior Procurement Officer)"
_P_CONTACT = re.compile(rf"(?i:\b(?:contact(?:\s+(?:person|officer|point))?|enquiries\s+to|queries\s+to|attention))\s*[:\-–]\s*"
                        rf"(?P<name>{_NAME})(?:\s*[,(]\s*(?P<role>{_ROLE_LONG}))?")
# 2. "Jane Smith, Head of Cargo at Example Air" / "John Kamau, Director General of the Kenya Civil Aviation Authority"
_P_NAME_ROLE = re.compile(rf"(?P<name>{_NAME}),\s+(?:the\s+)?(?P<role>{_ROLE_LONG})")
# 3. "Head of Cargo Maria Lopez said" / "said Chief Commercial Officer Ahmed Al-Mansouri"
_P_ROLE_NAME = re.compile(rf"(?P<role>{_ROLE})\s+(?P<name>{_NAME})(?=\s+(?:said|says|added|stated|commented|explained)\b|[.,;]|$)")

_NOT_NAMES = {"the", "this", "our", "all", "any", "request", "proposal", "proposals", "tender", "cargo", "general", "sales", "service",
              "services", "airline", "airlines", "airport", "international", "group", "limited", "company", "department", "ministry",
              "authority", "board", "committee", "office", "head", "director", "manager", "chief", "officer", "air", "airways",
              "aviation", "logistics", "express", "holdings", "freight", "global", "national", "corporation", "agency",
              # business units and functions: "Head of Cargo Revenue Management" never yields a person called "Revenue Management"
              "management", "revenue", "operations", "development", "commercial", "marketing", "finance", "network", "planning",
              "strategy", "communications", "procurement", "handling", "terminal", "sustainability"}


@dataclass
class NamedPerson:
    name: str
    role: str | None
    quote: str
    pattern: str                       # contact | name_role | role_name
    role_on_opportunity: str = "named_in_source"
    relevance_basis: str = ""


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start))
    right_candidates = [i for i in (text.find(".", end), text.find("\n", end)) if i != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return " ".join(text[left + 1: right + 1].split())[:400]


def _clean_name(raw: str) -> str | None:
    name = re.sub(r"^(?:Mr|Mrs|Ms|Dr|Capt|Captain)\.?\s+", "", raw.strip())
    tokens = name.split()
    if len(tokens) < 2 or any(t.lower().strip(".,") in _NOT_NAMES for t in tokens):
        return None
    return name


def classify_role(role: str | None) -> str:
    """Maps a stated title to the kind of involvement it shows. Seniority alone never makes someone a decision maker."""
    r = (role or "").lower()
    if re.search(r"procure|tender|purchas|sourcing|contract", r):
        return "procurement_contact"
    if re.search(r"country manager|regional|station manager|area manager|general manager,? [a-z]+", r):
        return "regional_representative"
    if re.search(r"cargo|commercial|sales|revenue|marketing", r):
        return "commercial_leader"
    if re.search(r"operations|handling|training|learning|finance|account|digital|information|technology|it\b", r):
        return "department_lead"
    return "named_in_source"


def people_in_text(text: str, organisation_names: Iterable[str] = ()) -> list[NamedPerson]:
    """People explicitly named in a source passage, with the sentence that names them. Conservative by design: a name
    needs a contact label or a stated title next to it, and a known organisation name is never taken for a person.
    Returns at most one entry per name (the most specific mention)."""
    orgs = {o.strip().lower() for o in organisation_names if o and o.strip()}
    found: dict[str, NamedPerson] = {}
    for pattern, rx in (("contact", _P_CONTACT), ("name_role", _P_NAME_ROLE), ("role_name", _P_ROLE_NAME)):
        for m in rx.finditer(text):
            name = _clean_name(m.group("name"))
            if not name or name.lower() in orgs or any(name.lower() in o or o in name.lower() for o in orgs):
                continue
            role = (m.groupdict().get("role") or "").strip(" ,;()") or None
            if role and len(role) > 90:
                role = role[:90].rsplit(" ", 1)[0]
            key = name.lower()
            if key in found and (found[key].role or not role):
                continue
            kind = classify_role(role) if role else ("procurement_contact" if pattern == "contact" else "named_in_source")
            basis = {
                "contact": "named as the contact for this notice",
                "name_role": f"named in the source with the title '{role}'" if role else "named in the source",
                "role_name": f"quoted in the source as '{role}'" if role else "quoted in the source",
            }[pattern]
            found[key] = NamedPerson(name, role, _sentence_around(text, m.start(), m.end()), pattern, kind,
                                     basis + "; decision-making authority is not established by this mention")
    return list(found.values())


# ------------------------------------------------------------------ gaps and next actions
@dataclass
class Coverage:
    people_total: int = 0
    candidates: int = 0
    confirmed: int = 0
    with_relationship: int = 0
    with_introduction: int = 0
    roles_covered: set[str] = field(default_factory=set)

    @property
    def level(self) -> str:
        if self.with_relationship:
            return "existing_relationship"
        if self.with_introduction:
            return "introduction_available"
        if self.confirmed:
            return "people_confirmed"
        if self.candidates:
            return "candidates_only"
        return "none"


COVERAGE_LABELS = {"existing_relationship": "Existing relationship", "introduction_available": "Introduction available",
                   "people_confirmed": "People confirmed, no relationship", "candidates_only": "Research candidates only",
                   "none": "No relationship research yet"}


def coverage(people: Iterable[dict[str, Any]]) -> Coverage:
    c = Coverage()
    for p in people:
        if p.get("link_status") == "not_relevant":
            continue
        c.people_total += 1
        st = p.get("state")
        if st == "research_candidate":
            c.candidates += 1
        else:
            c.confirmed += 1
        if st == "existing_relationship":
            c.with_relationship += 1
        if st == "introduction_available":
            c.with_introduction += 1
        if st != "research_candidate" and p.get("role_on_opportunity"):
            c.roles_covered.add(str(p["role_on_opportunity"]))
    return c


def gaps_and_actions(module: str, organisations: Sequence[str], people: Sequence[dict[str, Any]], *,
                     researched: bool) -> tuple[list[str], list[str]]:
    """What relationship information is missing, and the useful next actions. Plain statements, no scores."""
    cov = coverage(people)
    org = organisations[0] if organisations else "the issuing organisation"
    gaps: list[str] = []
    actions: list[str] = []
    if not researched:
        gaps.append("Relationship research has not been run for this opportunity")
        actions.append("Run Research relationships")
    for role in target_roles(module):
        if role.key not in cov.roles_covered:
            gaps.append(f"No confirmed {role.label.lower()} at {org}")
    if cov.candidates and not cov.confirmed:
        actions.append(f"Confirm the identity and role of the {cov.candidates} research candidate(s) (sources and LinkedIn search)")
    if not cov.with_relationship:
        gaps.append(f"No existing WFC relationship recorded with anyone at {org}")
        if cov.confirmed:
            actions.append("Ask the team who knows the confirmed people, and record any existing relationship")
    if not cov.with_relationship and not cov.with_introduction:
        gaps.append("No introduction route with a confirmed, willing introducer")
        actions.append("Identify a possible introducer and confirm their relationship and willingness before relying on it")
    unverified = [p for p in people if p.get("state") != "research_candidate" and not p.get("last_verified_at")]
    if unverified:
        gaps.append(f"{len(unverified)} person(s) without a recorded verification date")
    return gaps, actions
