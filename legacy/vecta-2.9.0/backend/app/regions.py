"""Static reference data taken directly from the specification (Sections 02 and 05).

These are constants, not database tables — the region/market structure and
the five verticals are fixed parts of the VECTA vision, not user-editable
data. Keeping them as code (rather than seeded rows) means they can never
drift from the specification and need no migration to update copy.
"""
import enum


class Vertical(str, enum.Enum):
    MEDIA = "media"
    TALENT = "talent"
    CONNECT = "connect"
    EXPERIENCES = "experiences"
    PATHWAYS = "pathways"


def parse_verticals(values: list) -> list["Vertical"]:
    """Safely parses a list of raw strings (e.g. from an AI response) into
    valid Vertical members, silently dropping anything unrecognised."""
    result = []
    for v in values or []:
        try:
            result.append(Vertical(str(v).strip().lower()))
        except ValueError:
            continue
    return result


VERTICAL_INFO: dict[Vertical, dict] = {
    Vertical.MEDIA: {
        "label": "VECTA Media",
        "positioning": "Visibility infrastructure",
        "focus": "Media rights tenders, content production briefs, sponsorship media inventory, broadcast and digital "
        "distribution RFPs, and esports/digital-sport media rights",
    },
    Vertical.TALENT: {
        "label": "VECTA Talent",
        "positioning": "Long term representation",
        "focus": "Representation mandates, ambassador programmes, endorsement briefs, federation talent-development "
        "contracts, and talent pipelines surfaced through university athletics programmes and elite academies",
    },
    Vertical.CONNECT: {
        "label": "VECTA Connect",
        "positioning": "Relationship capital",
        "focus": "Partnership brokerage, B2B introductions, government and federation relationship programmes, "
        "sports technology and performance-data partnerships, and ESG/sustainability-in-sport initiatives — "
        "with intent, not volume",
    },
    Vertical.EXPERIENCES: {
        "label": "VECTA Experiences",
        "positioning": "Environments for alignment",
        "focus": "Hospitality tenders (e.g. F1 Abu Dhabi), event delivery RFPs, premium activations with real commercial outcomes",
    },
    Vertical.PATHWAYS: {
        "label": "VECTA Pathways",
        "positioning": "Future pipeline infrastructure",
        "focus": "Academy and grassroots tenders, education partnerships, emerging-market infrastructure programmes, "
        "school and dual-career academy partnerships, and scholarship/athlete-funding programmes (Olympic Solidarity, "
        "government athlete-support schemes, corporate and Paralympic scholarship funds)",
    },
}


class Region(str, enum.Enum):
    MENA = "mena"
    UK_IRELAND = "uk_ireland"
    EUROPE = "europe"
    AFRICA = "africa"
    ASIA_INDIA = "asia_india"
    AMERICAS = "americas"
    OCEANIA = "oceania"


REGION_INFO: dict[Region, dict] = {
    Region.MENA: {
        "label": "MENA (anchor)",
        "markets": ["UAE", "Saudi Arabia", "Qatar", "Bahrain", "Kuwait", "Oman", "Egypt", "Morocco", "Jordan"],
    },
    Region.UK_IRELAND: {
        "label": "UK & Ireland",
        "markets": ["England", "Scotland", "Wales", "Northern Ireland", "Republic of Ireland"],
    },
    Region.EUROPE: {
        "label": "Europe",
        "markets": ["Spain", "Germany", "France", "Italy", "Netherlands", "Portugal", "Scandinavia", "CEE"],
    },
    Region.AFRICA: {
        "label": "Africa",
        "markets": ["Nigeria", "South Africa", "Ghana", "Kenya", "Senegal", "North Africa corridor"],
    },
    Region.ASIA_INDIA: {
        "label": "Asia & India",
        "markets": ["India", "Japan", "South Korea", "China", "Southeast Asia"],
    },
    Region.AMERICAS: {
        "label": "Americas",
        "markets": ["USA", "Canada", "Brazil", "Mexico", "Argentina"],
    },
    Region.OCEANIA: {
        "label": "Oceania",
        "markets": ["Australia", "New Zealand"],
    },
}

# Named sources the scanner is briefed to search against (Section 04).
# These aren't literal API connectors — most governing bodies and tender
# portals have no public API — the AI + web-search layer is instructed to
# search these named sources directly, which is the honest and durable way
# to cover them without brittle scrapers.
SOURCE_CATEGORIES: list[str] = [
    "Governing bodies and federations (FIFA, UEFA, AFC, IOC, F1, World Athletics, ICC, national federations) — "
    "procurement notices, commercial partner searches, programme tenders",
    "Government and public procurement portals (UAE/GCC portals, UK Contracts Finder, Find a Tender, EU TED, "
    "and equivalents in priority markets)",
    "Clubs, leagues and venues — commercial rights sales, hospitality tenders, sponsorship inventory, "
    "stadium-development briefs",
    "Sports business media — signalled opportunities before they reach formal tender",
    "Major-event ecosystems, host-city organising committees and tourism boards — supplier registers, "
    "hospitality tenders and activation briefs (e.g. F1 Abu Dhabi Grand Prix, World Cup cycles, regional games)",
    "Schools, academies and dual-career pathways — elite sports academies, international schools with sport "
    "specialisation tracks, and national federation youth academy networks — partnership, sponsorship and "
    "infrastructure briefs",
    "University and higher-education athletics — NCAA Division I athletics departments, UK BUCS-affiliated "
    "universities, and Gulf/international university sport bursary schemes — representation, sponsorship "
    "and facility opportunities",
    "Scholarship and athlete-funding programmes — National Olympic Committee and Olympic Solidarity "
    "scholarships, government sport-investment schemes (e.g. Saudi Vision 2030, UAE athlete support "
    "programmes), corporate-funded athlete development scholarships, and Paralympic/adaptive sport "
    "scholarship programmes",
    "Sports technology and performance data/analytics companies — commercial partnership, sponsorship and "
    "data-rights opportunities",
    "Broadcast and streaming rights holders, plus sports journalism and media-production programmes — "
    "distribution, production and talent-pipeline opportunities",
    "Esports and digital-sport organisations — sponsorship, media rights and talent representation "
    "opportunities",
    "ESG and sustainability-in-sport initiatives — increasingly tied to sponsorship and partnership "
    "decision-making",
]
