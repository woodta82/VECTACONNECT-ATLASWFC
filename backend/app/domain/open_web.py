"""Open-web discovery rules (29 Oct 2026: open-web discovery as the default). Framework-free.

1. Queries. A search's geography, capability areas and optional keywords or organisation become web-search queries, built
   from what each of the nine WFC capability areas looks like in public information: formal notices (tenders, RFPs, RFQs,
   expressions of interest) AND commercial openings (mandates, route launches, capacity, gateways, outsourcing, technology,
   partnerships). Queries are named by purpose so a run can list what was searched.
2. Publisher. A page found on the open web is attributed to its own site: the host is its publisher family, and its authority is
   inferred conservatively (government portal, the organisation's own site, known trade press, otherwise unverified).
3. Access restrictions. A page that needs registration, login or payment is labelled, never read as if it had been, never
   bypassed; the run then looks for a public original or corroborating notice by searching for its title.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

# ------------------------------------------------------------------ 1. queries
@dataclass(frozen=True)
class WebQuery:
    purpose: str
    text: str
    module: str | None
    country: str | None            # ISO code of the country the query is for (None: worldwide)


# What each capability area looks like in public information: (purpose, search terms). The first entry of each area is the
# formal-notice query; the rest are commercial openings and signals, kept distinct from proven procurement.
AREA_TERMS: dict[str, list[tuple[str, str]]] = {
    "airline_representation": [
        ("GSSA and cargo representation tenders", '(tender OR RFP OR "request for proposal" OR "expression of interest") (GSSA OR "cargo sales agent" OR "general sales agent" OR "cargo representation")'),
        ("Representation mandates and appointments", '("appoints" OR "appointed" OR "new GSSA" OR "cargo GSA") airline cargo'),
        ("Total cargo management opportunities", '"total cargo management" OR "cargo outsourcing" airline'),
    ],
    "account_growth": [
        ("Airline cargo expansion and new services", 'airline cargo (expansion OR "new service" OR "additional frequencies" OR "freighter") announcement'),
        ("Airline partnerships and mandate changes", 'airline cargo (partnership OR "sales agreement" OR mandate OR "appoints") press release'),
    ],
    "forwarder_sales": [
        ("Freight forwarder expansion and appointments", '"freight forwarder" (expansion OR "opens office" OR appoints OR acquisition OR partnership)'),
        ("Air cargo demand and shipper news", '("air cargo" OR airfreight) (exports OR shippers OR "cargo volumes") news'),
    ],
    "capacity_lanes": [
        ("Route launches and capacity announcements", '("new route" OR "launches" OR "freighter service" OR "cargo capacity" OR "belly capacity") airline cargo'),
        ("Freighter and charter capacity", '(freighter OR "cargo charter") (capacity OR "weekly flights" OR "additional flights")'),
    ],
    "service_operations": [
        ("Ground handling and cargo service tenders", '(tender OR RFP OR RFQ) ("ground handling" OR "cargo handling" OR "flight supervision" OR "cargo terminal")'),
        ("Cargo handling and terminal developments", '("cargo terminal" OR "cargo handling" OR "ground handling") (opens OR expansion OR contract OR concession)'),
    ],
    "trucking_gateways": [
        ("Road feeder and trucking tenders", '(tender OR RFP OR RFQ) ("road feeder" OR trucking OR "bonded truck" OR "cargo trucking") airport'),
        ("Gateway and road-feeder developments", '("road feeder service" OR RFS OR "cargo gateway" OR "off-airport") (launch OR expansion OR partnership)'),
    ],
    "outsourcing_training": [
        ("Outsourcing and training tenders", '(tender OR RFP OR RFQ) (outsourcing OR "revenue accounting" OR "cargo training" OR "call centre" OR "data processing") airline OR cargo'),
        ("Training and outsourcing demand", '("cargo training" OR "revenue accounting" OR "back office" OR outsourcing) airline cargo'),
    ],
    "technology_solutions": [
        ("Cargo technology procurement", '(tender OR RFP OR RFQ) ("cargo management system" OR "booking platform" OR "cargo software" OR "track and trace")'),
        ("Digital adoption and platform changes", '("cargo booking platform" OR "digital booking" OR "e-AWB" OR "cargo system") airline (adopts OR launches OR selects)'),
    ],
    "network_development": [
        ("Network, partnership and acquisition signals", '("air cargo" OR GSSA OR "freight forwarder") (acquisition OR "joint venture" OR partnership OR "network expansion" OR "new station")'),
        ("Agency and representation gaps", '(airline OR "cargo carrier") ("seeks" OR "looking for" OR "invites") (agent OR GSSA OR representative OR partner) cargo'),
    ],
}
ALL_MODULES = tuple(AREA_TERMS)
GENERAL_TERMS = [("Public tender and procurement notices", '(tender OR "request for proposal" OR RFQ OR procurement) (cargo OR freight OR airline OR airport)'),
                 ("Airline and airport cargo announcements", '(airline OR airport) cargo (announces OR launches OR appoints OR tender)')]
# Public sources worth naming in queries when a country is given: portals, newsrooms, trade press, PDFs and feeds.
SOURCE_HINTS = ['site:gov OR site:go OR "procurement portal"', 'filetype:pdf', '"press release" OR newsroom', 'rss OR feed']


def build_queries(*, countries: Iterable[str | None], country_names: dict[str, str], modules: Iterable[str], keywords: str | None,
                  organisation: str | None, airline: str | None, max_per_country: int) -> list[WebQuery]:
    """Queries per country (or one worldwide set) for the selected areas; the named organisation or airline and keywords narrow
    every query. Formal-notice queries come first. Capped per country so a wide search stays within the per-run limits."""
    mods = [m for m in modules if m in AREA_TERMS] or list(ALL_MODULES)
    focus = " ".join(f'"{x.strip()}"' for x in (organisation, airline) if x and x.strip())
    kw = (keywords or "").strip()
    out: list[WebQuery] = []
    for c in list(countries) or [None]:
        where = f' "{country_names.get(c, c)}"' if c else ""
        per: list[WebQuery] = []
        for m in mods:
            for i, (purpose, terms) in enumerate(AREA_TERMS[m]):
                if len(mods) >= 5 and i > 0 and not (focus or kw):
                    break            # a wide search: one formal-notice query per area, the openings are reached by the general queries
                text = " ".join(x for x in (focus, kw, terms) if x) + where
                per.append(WebQuery(purpose + (f" in {country_names.get(c, c)}" if c else " (worldwide)"), text, m, c))
        if len(mods) >= 5:
            for purpose, terms in GENERAL_TERMS:
                per.append(WebQuery(purpose + (f" in {country_names.get(c, c)}" if c else " (worldwide)"),
                                    " ".join(x for x in (focus, kw, terms) if x) + where, None, c))
        if kw or focus:
            per.insert(0, WebQuery(("Named organisation or keywords" + (f" in {country_names.get(c, c)}" if c else "")),
                                   " ".join(x for x in (focus, kw) if x) + " cargo OR freight OR airline" + where, None, c))
        out.extend(per[:max_per_country])
    seen: set[str] = set()
    uniq = []
    for q in out:
        if q.text.lower() not in seen:
            seen.add(q.text.lower())
            uniq.append(q)
    return uniq


def corroboration_query(title: str | None, url: str) -> str | None:
    """A query for a public original or corroborating copy of a restricted item: its title, else the slug of its address."""
    t = " ".join((title or "").split())
    if len(t) >= 12:
        return f'"{t[:120]}"'
    slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    words = [w for w in re.split(r"[-_.]+", slug) if len(w) > 2 and not w.isdigit()]
    return " ".join(words[:8]) if len(words) >= 3 else None


# ------------------------------------------------------------------ 2. publisher
_GOV = re.compile(r"(^|\.)(gov|gouv|govt|go|gob|gc|mil)(\.[a-z]{2})?$|\.gov\.|\.gouv\.|(^|\.)tenders?\.|(^|\.)procurement\.|e-?procure|ppra\.|ppda\.|"
                  r"(^|\.)(un|undp|worldbank|afdb)\.org$", re.I)
_TRADE_PRESS = ("aircargonews.net", "aircargoweek.com", "theloadstar.com", "stattimes.com", "cargoforwarder.eu", "airfreightnews",
                "freightwaves.com", "aircargoworld.com", "logisticsupdateafrica.com", "africalogisticsnetwork", "payloadasia.com",
                "cargofacts.com", "ch-aviation.com", "simpleflying.com", "aviationweek.com", "flightglobal.com", "routesonline.com")
AUTHORITY_LABELS = {"official_portal": "Official or government portal", "company_release": "The organisation's own site", "trade_press": "Trade press",
                    "unverified": "Unverified publisher"}


def host_of(url: str) -> str:
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def infer_authority(url: str, organisation_hosts: Iterable[str] = ()) -> str:
    h = host_of(url)
    if not h:
        return "unverified"
    if any(h == o or h.endswith("." + o) for o in organisation_hosts if o):
        return "company_release"
    if _GOV.search(h):
        return "official_portal"
    if any(h == t or h.endswith("." + t) or t in h for t in _TRADE_PRESS):
        return "trade_press"
    return "unverified"


# ------------------------------------------------------------------ 3. access restrictions
_RESTRICT_WORDS = re.compile(r"\b(log ?in|sign ?in|register(?:ed)?|registration|subscribe|subscription|subscribers? only|members? only|"
                             r"paywall|purchase (?:the|this) document|buy (?:the|this) (?:document|tender)|access denied|premium content|"
                             r"create an account|password)\b", re.I)
RESTRICTION_LABELS = {"login_required": "Registration or login required", "payment_required": "Payment or subscription required",
                      "access_denied": "Access denied by the site"}


def restriction_from_status(status: int | None) -> str | None:
    if status in (401, 407):
        return "login_required"
    if status == 402:
        return "payment_required"
    if status == 403:
        return "access_denied"
    return None


def restriction_from_page(text: str, title: str | None = None) -> str | None:
    """A page that answered 200 but shows only a gate: little text, dominated by login, registration or subscription wording."""
    body = " ".join((text or "").split())
    hay = f"{title or ''} {body}"
    hits = _RESTRICT_WORDS.findall(hay)
    if not hits:
        return None
    words = len(body.split())
    if words > 350 and len(hits) < 4:
        return None                                   # a real article that mentions logging in somewhere
    if words <= 350 and len(hits) >= 1 and (words < 80 or len(hits) >= 2):
        lowered = " ".join(hits).lower()
        if "pay" in lowered or "subscri" in lowered or "purchase" in lowered or "buy" in lowered or "premium" in lowered:
            return "payment_required"
        return "login_required"
    return None
