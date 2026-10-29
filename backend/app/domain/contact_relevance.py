"""Relevance of a discovered contact to a discovery brief (29 Oct 2026). Framework-free.

ATLAS v1.0 asked its AI researcher for a candid 0–100 relevance combining seniority, deal-making authority, regional weight
and fit to the verticals. Here the same four things are scored from recorded facts, so every point is explained:

  Role fit to the capability area   35   the bound title matches a target role of the WFC capability area (brief)
  Seniority and authority           25   from the bound title: executive 25, head/director 20, manager 12, other 5; never from a guess
  Organisation fit                  20   the organisation named in the brief 20; an airline, forwarder, GSSA or airport 12; other 5
  Geography fit                     10   the person's organisation or remit is in a country of the brief
  Evidence strength                 10   listed on a leadership page or appointed 10; stated title in a passage 7; named only 3

Decision-making authority is NOT established by any of this: the score says how worth a look the contact is for the brief.
"""
from __future__ import annotations

import re
from typing import Any

from .relationships import target_roles

WEIGHTS = {"role_fit": 35, "seniority": 25, "organisation": 20, "geography": 10, "evidence": 10}
assert sum(WEIGHTS.values()) == 100

_EXEC = re.compile(r"\b(chief|ceo|cco|coo|cfo|cio|president|managing director|general manager|executive vice|evp|svp|vice[- ]president|vp)\b", re.I)
_HEAD = re.compile(r"\b(head of|director|general counsel|country manager|regional manager|principal)\b", re.I)
_MANAGER = re.compile(r"\b(manager|lead|controller|superintendent|supervisor)\b", re.I)
_ROLE_WORDS = re.compile(r"[a-z]+")
_ORG_KINDS = {"airline": "an airline", "forwarder": "a freight forwarder", "gssa": "a GSSA", "airport_operator": "an airport operator",
              "trucking_provider": "a trucking provider"}


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def score(*, role_title: str | None, organisation: str | None, organisation_kind: str | None, countries: list[str],
          brief_module: str | None, brief_organisation: str | None, brief_countries: list[str], brief_role_focus: str | None,
          binding: str | None, page_kind: str | None) -> dict[str, Any]:
    comps: list[dict[str, Any]] = []

    def add(key: str, pts: int, reason: str) -> None:
        comps.append({"key": key, "label": {"role_fit": "Role fit", "seniority": "Seniority and authority", "organisation": "Organisation fit",
                                             "geography": "Geography fit", "evidence": "Evidence strength"}[key],
                      "points": pts, "max": WEIGHTS[key], "reason": reason})

    title = _norm(role_title)
    # role fit
    pts, why = 0, "No title bound to this person" if not title else "Title does not match a target role of the brief"
    if title:
        focus = _norm(brief_role_focus)
        if focus and all(w in title for w in _ROLE_WORDS.findall(focus)[:3]):
            pts, why = 35, f"Title matches the role focus '{brief_role_focus}'"
        elif brief_module:
            for r in target_roles(brief_module):
                if any(t in title for t in r.search_terms):
                    pts, why = 35, f"Title matches the target role '{r.label}' for this capability area"
                    break
            else:
                if any(w in title for w in ("cargo", "freight", "logistics", "commercial", "procurement", "supply chain")):
                    pts, why = 18, "Title is in the commercial or cargo function, not a target role of the brief"
        elif any(w in title for w in ("cargo", "freight", "logistics", "commercial", "procurement")):
            pts, why = 25, "Title is in the cargo or commercial function (no capability area in the brief)"
    add("role_fit", pts, why)
    # seniority (from the bound title only)
    if not title:
        add("seniority", 0, "No title bound to this person")
    elif _EXEC.search(title):
        add("seniority", 25, "Executive title")
    elif _HEAD.search(title):
        add("seniority", 20, "Head, director or country-level title")
    elif _MANAGER.search(title):
        add("seniority", 12, "Manager-level title")
    else:
        add("seniority", 5, "Title gives no seniority signal")
    # organisation
    org = _norm(organisation)
    if not org:
        add("organisation", 0, "Organisation not established")
    elif brief_organisation and (_norm(brief_organisation) == org or _norm(brief_organisation) in org or org in _norm(brief_organisation)):
        add("organisation", 20, f"The organisation named in the brief ({organisation})")
    elif organisation_kind in _ORG_KINDS:
        add("organisation", 12, f"{organisation} is {_ORG_KINDS[organisation_kind]}")
    else:
        add("organisation", 5, f"{organisation}: kind not recorded")
    # geography
    if not brief_countries:
        add("geography", 5, "No country in the brief")
    elif any(c in brief_countries for c in countries):
        add("geography", 10, "Organisation or remit in a country of the brief")
    elif not countries:
        add("geography", 2, "Country of the organisation or remit not established")
    else:
        add("geography", 0, "Outside the countries of the brief")
    # evidence
    b = _norm(binding)
    if page_kind == "leadership" or "listed with this title" in b:
        add("evidence", 10, "Listed with this title on the organisation's leadership page")
    elif "appointment" in b:
        add("evidence", 10, "Appointment announced by the organisation")
    elif title:
        add("evidence", 7, "Title stated in the passage that names the person")
    else:
        add("evidence", 3, "Named in a passage; no title bound")
    total = sum(c["points"] for c in comps)
    return {"score": total, "components": comps, "rule": "Relevance to the brief, not decision-making authority"}
