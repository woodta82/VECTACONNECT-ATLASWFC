"""Function Three — Relationship Intelligence: discovery half.

Finds named, publicly-identifiable people behind an opportunity or a
standalone influence-graph query. This deliberately researches only public
sources (official sites, press releases, news, published bios) via Claude's
web search — it does not scrape LinkedIn profiles or automate connection
requests, per the specification's own compliance note (Section 06): full
LinkedIn network data (degrees of separation from VECTA's actual team
connections) requires the official LinkedIn API / Sales Navigator, which
needs a licensed integration and real OAuth credentials VECTA has to obtain
directly from LinkedIn. Until that's wired up (see config.linkedin_client_id),
every contact gets a LinkedIn *search* deep-link — a normal, permitted,
human-clicked search URL — rather than a fetched profile, so the workflow
is fully usable today without breaching LinkedIn's terms.
"""
import json
import urllib.parse

from anthropic import Anthropic

from ..config import settings

SYSTEM_PROMPT = """You are ATLAS's relationship-intelligence researcher. Using web search over \
public sources only (official organisation sites, press releases, published bios, news \
coverage) — never social media scraping — identify named individuals who plausibly hold \
buying, commercial or decision-making authority relevant to the brief. Respond with a \
single JSON array and nothing else."""

USER_TEMPLATE = """Research brief:
{brief}

Find up to 6 named, real individuals matching this brief from public sources. For each, return:

{{
  "name": "full name",
  "role": "their job title / role, as published",
  "organisation_name": "the organisation they belong to",
  "seniority_and_authority": "one sentence on why they likely hold deal-making authority here",
  "relevance_score": "0-100: combined seniority, deal-making authority, regional weight and fit to VECTA's verticals — be candid",
  "connection_path": "one sentence: a plausible approach angle based on public information only (e.g. shared industry events, published initiatives) — if none, say 'No public connection signal — approach directly'",
  "source_url": "the public source this was drawn from, or null"
}}

Rules:
- Only named individuals with a plausible public basis — never invent names.
- If fewer than 6 credible individuals can be found, return fewer. Do not pad with guesses.
- relevance_score must be an integer 0-100.

Respond with the JSON array only."""


def _build_brief(
    organisation_name: str | None,
    region_label: str | None,
    vertical_label: str | None,
    role_focus: str | None,
) -> str:
    parts = []
    if organisation_name:
        parts.append(f"Organisation: {organisation_name}")
    if region_label:
        parts.append(f"Region: {region_label}")
    if vertical_label:
        parts.append(f"VECTA vertical relevance: {vertical_label}")
    if role_focus:
        parts.append(f"Role focus: {role_focus}")
    if not parts:
        parts.append("General influence-graph scan of senior commercial decision-makers in global sport")
    return "\n".join(parts)


def discover_contacts(
    organisation_name: str | None = None,
    region_label: str | None = None,
    vertical_label: str | None = None,
    role_focus: str | None = None,
) -> list[dict]:
    client = Anthropic(api_key=settings.anthropic_api_key)
    brief = _build_brief(organisation_name, region_label, vertical_label, role_focus)
    prompt = USER_TEMPLATE.format(brief=brief)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text")
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        items = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return items if isinstance(items, list) else []


def linkedin_search_url(name: str, organisation_name: str | None = None) -> str:
    """A normal, permitted LinkedIn people-search deep-link — not a scrape,
    not an API call. Opens LinkedIn's own search results for a human to
    review and connect with directly."""
    keywords = f"{name} {organisation_name}" if organisation_name else name
    return "https://www.linkedin.com/search/results/people/?keywords=" + urllib.parse.quote(keywords)
