"""Planning relationship research (instruction of 28 Oct 2026, items 1 and 4). Framework-free; no I/O.

- Search queries built from the opportunity, its organisations, geography and the target roles of its category.
- Links worth following on an organisation's own pages: leadership, management, team and board pages, the newsroom, and
  news items that mention an appointment, the organisation, cargo or the opportunity. Same site only.
- Long documents are read in sections so reading can stop at a budget limit and resume where it stopped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .relationships import target_roles

SECTION_CHARS = 6_000
MAX_FOLLOWED_PER_ORG = 6
FALLBACK_PATHS = ("about", "leadership", "management", "team", "news")    # used only when a page offers no such links


@dataclass(frozen=True)
class Query:
    purpose: str      # e.g. "Head of cargo / commercial leader at Example Air (Kenya)"
    text: str


def build_queries(*, module: str, title: str, reference: str | None, organisations: list[str], countries: list[str],
                  limit: int = 8) -> list[Query]:
    """Targeted searches, most specific first. Organisation names are quoted; country names narrow role searches."""
    out: list[Query] = []
    country = countries[0] if countries else None
    for org in organisations[:2]:
        quoted = f'"{org}"'
        for r in target_roles(module):
            terms = " OR ".join(f'"{t}"' for t in r.search_terms[:2])
            out.append(Query(f"{r.label} at {org}" + (f" ({country})" if country else ""),
                             f"{quoted} ({terms})" + (f" {country}" if country else "")))
        out.append(Query(f"Appointment announcements by {org}", f"{quoted} appoints OR appointed OR \"joins as\""))
        out.append(Query(f"Leadership and management of {org}", f"{quoted} leadership team OR management team"))
        out.append(Query(f"Press releases and market reports on {org}" + (f" in {country}" if country else ""),
                         f"{quoted} press release" + (f" {country}" if country else "") + " cargo"))
    if reference:
        out.append(Query(f"Other publications of the notice {reference}", f'"{reference}"'))
    elif title:
        out.append(Query("Other publications of this opportunity", f'"{title[:90]}"'))
    seen: set[str] = set()
    uniq: list[Query] = []
    for q in out:
        if q.text.lower() not in seen:
            seen.add(q.text.lower())
            uniq.append(q)
    return uniq[:limit]


def build_discovery_queries(*, module: str | None, organisation: str | None, countries: list[str], role_focus: str | None,
                            limit: int = 8) -> list[Query]:
    """Open-market contact searches for a discovery brief (29 Oct 2026): the target roles of the WFC capability area, the
    organisation when named, the country names, and a role focus typed by the team. Most specific first."""
    out: list[Query] = []
    country = countries[0] if countries else None
    where = f" {country}" if country else ""
    roles = target_roles(module) if module else ()
    quoted = f'"{organisation}"' if organisation else None
    if role_focus:
        rf = f'"{role_focus.strip()}"'
        out.append(Query(f"{role_focus} at {organisation}" if organisation else f"{role_focus}{where}",
                         (f"{quoted} {rf}" if quoted else f"{rf} cargo OR freight OR airline") + where))
    if quoted:
        for r in roles:
            terms = " OR ".join(f'"{t}"' for t in r.search_terms[:2])
            out.append(Query(f"{r.label} at {organisation}", f"{quoted} ({terms}){where}"))
        out.append(Query(f"Appointment announcements by {organisation}", f"{quoted} appoints OR appointed OR \"joins as\" cargo"))
        out.append(Query(f"Leadership and management of {organisation}", f"{quoted} leadership team OR management team"))
    else:
        for r in roles:
            terms = " OR ".join(f'"{t}"' for t in r.search_terms[:2])
            out.append(Query(f"{r.label}{(' in ' + country) if country else ''}", f"({terms}) cargo airline OR forwarder OR GSSA{where}"))
        if country:
            out.append(Query(f"Cargo appointments in {country}", f"appointed OR appoints \"head of cargo\" OR \"cargo manager\" {country}"))
            out.append(Query(f"Air cargo and freight news in {country}", f"air cargo OR freight forwarder news {country}"))
    seen: set[str] = set()
    uniq: list[Query] = []
    for q in out:
        if q.text.lower() not in seen:
            seen.add(q.text.lower())
            uniq.append(q)
    return uniq[:limit]


_LEADER = re.compile(r"leader|management|executive|our[- ]?team|\bteam\b|our[- ]?people|who[- ]?we[- ]?are|board|directors|about", re.I)
_NEWSROOM = re.compile(r"\bnews\b|newsroom|press|media[- ]?(?:centre|center|room)?|releases?|announcements?", re.I)
_ITEM = re.compile(r"appoint|join|names|welcome|promot|cargo|freight|gsa|gssa|tender|procure|partner|director|manager|head of|chief", re.I)


_PROFILE = re.compile(r"airlines|represent|principals|partners?|services|contact|locations?|offices|stations?|network|about|company|group", re.I)


def link_kind(url: str, anchor: str, *, company: bool = False) -> str | None:
    path = urlsplit(url).path
    hay = f"{path} {anchor}"
    segs = [x for x in path.split("/") if x]
    if company and _PROFILE.search(hay) and not _NEWSROOM.search(hay):
        # company research (29 Oct 2026): the pages that describe what an organisation does, whom it represents and how to reach it
        return "leadership" if _LEADER.search(hay) else "profile"
    if _LEADER.search(hay) and not (len(anchor.split()) >= 5 and _ITEM.search(anchor)):
        return "leadership"
    if _NEWSROOM.search(hay):
        # a page below the newsroom (/news/2026/some-headline) is a news item; the newsroom itself is a listing
        news_at = next((i for i, x in enumerate(segs) if _NEWSROOM.search(x)), None)
        if news_at is not None and news_at < len(segs) - 1:
            return "article"
        return "news"
    if _ITEM.search(hay):
        return "article"
    return None


def links_to_follow(links: list[tuple[str, str]], page_url: str, keywords: list[str], limit: int = MAX_FOLLOWED_PER_ORG, *,
                    company: bool = False) -> list[tuple[str, str, str]]:
    """(url, anchor text, kind) on the same site, in priority order: leadership pages, the newsroom, then news items whose
    link text or address mentions the organisation, an appointment, cargo or the opportunity's keywords."""
    host = (urlsplit(page_url).hostname or "").lower()
    kw = [k.lower() for k in keywords if k and len(k) > 2]
    ranked: list[tuple[int, int, str, str, str]] = []
    seen: set[str] = set()
    for i, (url, anchor) in enumerate(links):
        u = url.split("#", 1)[0]
        parts = urlsplit(u)
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() != host or u.rstrip("/") == page_url.rstrip("/"):
            continue
        if u in seen or re.search(r"\.(jpg|jpeg|png|gif|svg|css|js|zip|xlsx?|pptx?)$", parts.path, re.I):
            continue
        kind = link_kind(u, anchor or "", company=company)
        hay = f"{parts.path} {anchor}".lower()
        if kind is None and kw and any(k in hay for k in kw):
            kind = "article"
        if kind is None:
            continue
        seen.add(u)
        rank = {"leadership": 0, "profile": 1, "news": 1, "article": 2}[kind]
        ranked.append((rank, i, u, anchor or "", kind))
    ranked.sort()
    return [(u, a, k) for _r, _i, u, a, k in ranked[:limit]]


def sections(text: str, size: int = SECTION_CHARS) -> list[str]:
    """Split a long text into sections of about `size` characters at paragraph (or sentence) boundaries. Nothing is
    dropped: the sections joined together are the whole text."""
    t = text.strip()
    if not t:
        return []
    if len(t) <= size:
        return [t]
    out: list[str] = []
    cur = ""
    for para in re.split(r"(\n\s*\n)", t):
        if len(cur) + len(para) <= size:
            cur += para
            continue
        if cur.strip():
            out.append(cur)
        cur = ""
        while len(para) > size:                      # a single very long paragraph: cut at a sentence end
            cut = max(para.rfind(". ", 0, size), para.rfind("\n", 0, size))
            cut = cut + 1 if cut > size // 3 else size
            out.append(para[:cut])
            para = para[cut:]
        cur = para
    if cur.strip():
        out.append(cur)
    return out
