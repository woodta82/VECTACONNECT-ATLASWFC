"""A person's evidenced involvement with the organisation researched (4.9.0).

    employee                  works at the organisation (the passage binds them to it)
    appointed_representative  acts for it under an appointment: GSA / GSSA, cargo sales agent, appointed agent or representative
    external_adviser          advises it from outside: consultant, legal or financial adviser, law firm, advisory
    press_contact             named as the press / media contact for an announcement (an agency, or a communications role)
    unresolved                the passage does not establish the involvement

Only the first two can be commercial contacts. Press contacts and external advisers are kept, with their actual role and organisation, as
external contacts — never counted in an opportunity's relationship coverage or ranking, never presented as decision makers. A person named
"for more information" who holds a commercial role at the company (Head of Cargo Sales) is not a press contact: the role decides.

Pure: `classify(quote, role, organisation, affiliation, subject_orgs)` returns (involvement, basis).
"""
from __future__ import annotations

import re
from typing import Iterable

INVOLVEMENTS = ("employee", "appointed_representative", "external_adviser", "press_contact", "unresolved")
LABELS = {"employee": "Employee", "appointed_representative": "Appointed representative", "external_adviser": "External adviser",
          "press_contact": "Press / media contact", "unresolved": "Involvement not established"}
COMMERCIAL = ("employee", "appointed_representative", "unresolved")   # unresolved stays a research candidate until a person decides
EXTERNAL = ("external_adviser", "press_contact")

_PRESS_CUE = re.compile(r"\b(?:press|media)\s+(?:contacts?|enquir\w*|inquir\w*|office|relations|desk)\b|\bfor (?:further|more) (?:information|details)\b|"
                        r"\b(?:pr|public relations|communications?|comms) (?:agency|firm|consultancy|partner)\b|\bissued by\b|\bpress release\b|"
                        r"\bnotes? to editors\b|\bmedia (?:kit|pack)\b", re.I)
_PRESS_ROLE = re.compile(r"\b(?:press|media|communications?|comms|public relations|pr|spokes(?:person|woman|man)|corporate affairs|marketing communications)\b", re.I)
_AGENCY_ORG = re.compile(r"\b(?:pr|public relations|communications?|comms|media|press|marketing)\b.*\b(?:agency|consultancy|partners?|group|ltd|limited|llc|sia|uab|gmbh|bv)\b|"
                         r"\bagency\b", re.I)
_ADVISER_CUE = re.compile(r"\b(?:advis[eo]rs?|advisory|consultants?|consultancy|counsel|law firm|solicitors?|attorneys?|legal adviser|financial adviser|"
                          r"advises|advised|auditors?)\b", re.I)
_REPRESENTATIVE_CUE = re.compile(r"\b(?:appoint(?:s|ed|ment)?\b.{0,80}?\b(?:gsa|gssa|general sales agen\w*|cargo sales agen\w*|representative|agent|agency)\b|"
                                 r"\b(?:gsa|gssa|general sales agent|cargo sales agent|sales representative|cargo representative)\s+for\b|"
                                 r"\brepresents?\b.{0,60}?\b(?:airline|carrier|cargo)\b|\bacting (?:for|on behalf of)\b)", re.I)
_COMMERCIAL_ROLE = re.compile(r"\b(?:cargo|sales|commercial|freight|business development|account|station|country|regional|general|managing|chief|"
                              r"director|head|procurement|purchasing|operations)\b", re.I)


def _fold(s: str | None) -> str:
    return (s or "").lower().strip()


def classify(quote: str, role: str | None, organisation: str | None, affiliation: str, subject_orgs: Iterable[str] = ()) -> tuple[str, str]:
    q = quote or ""
    subjects = [_fold(s) for s in subject_orgs if s]
    org = _fold(organisation)
    at_subject = bool(org) and any(org == s or org in s or s in org for s in subjects)
    outside = bool(org) and not at_subject
    press_role = bool(role and _PRESS_ROLE.search(role))
    commercial_role = bool(role and _COMMERCIAL_ROLE.search(role)) and not press_role
    # 1. a press or media contact: the passage presents them as such, and their role or organisation is a communications one, or they are
    #    outside the organisation. A commercial role at the organisation named "for more information" is NOT a press contact.
    if _PRESS_CUE.search(q) and (press_role or (outside and not commercial_role) or bool(organisation and _AGENCY_ORG.search(organisation))
                                 or (not org and not commercial_role)):
        where = f" ({organisation})" if organisation else ""
        return "press_contact", f"named as the press or media contact{where}: \"{_cue(_PRESS_CUE, q)}\"; not a commercial contact"
    # 2. an external adviser
    if _ADVISER_CUE.search(q) and (outside or not org or (role and _ADVISER_CUE.search(role))) and affiliation != "employee":
        return "external_adviser", f"advises from outside{(' (' + organisation + ')') if organisation else ''}: \"{_cue(_ADVISER_CUE, q)}\"; not a decision maker at the organisation"
    if role and _ADVISER_CUE.search(role) and outside:
        return "external_adviser", f"title '{role}' at {organisation}, outside the organisation"
    # 3. an appointed representative (a GSA / GSSA, an appointed agent)
    if _REPRESENTATIVE_CUE.search(q) and (outside or affiliation in ("partner", "other_organisation")):
        return "appointed_representative", f"acts for the organisation under an appointment: \"{_cue(_REPRESENTATIVE_CUE, q)}\""
    # 4. an employee: the passage binds them to the organisation
    if affiliation in ("employee", "board_member") or at_subject:
        return "employee", "the passage binds the person to the organisation" + (f" as {role}" if role else "")
    return "unresolved", "the passage does not establish how the person is involved with the organisation"


def _cue(rx: re.Pattern, q: str) -> str:
    m = rx.search(q)
    if not m:
        return ""
    a, b = max(0, m.start() - 30), min(len(q), m.end() + 30)
    return " ".join(q[a:b].split())
