"""Global Scanner / Regional Search core: Claude + live web search, briefed
against the named source categories in regions.py, returning structured
opportunity candidates already scored across the five VECTA Alignment
dimensions (see alignment_scoring.py for how those combine into the final
0-100 score).

This one function powers both Function One (Global Scanner, called once
per vertical every 7-day cycle) and Function Two (Regional Search, called
once per user query, scoped to a single region/market).
"""
import json

from anthropic import Anthropic

from ..config import settings
from ..regions import REGION_INFO, SOURCE_CATEGORIES, VERTICAL_INFO, Region, Vertical

SYSTEM_PROMPT = """You are ATLAS, VECTA Sports' commercial intelligence scanner. You research \
live, current information via web search and surface concrete, payable commercial \
opportunities in global sport — named tenders, RFPs, rights sales, hospitality \
packages, representation mandates and partnership openings — never vague trends or \
opinion pieces. After researching, your final message must be a single JSON array \
and nothing else — no preamble, no markdown fences, no commentary."""

REGION_ENUM_GUIDE = "\n".join(f"- {r.value}: {info['label']} ({', '.join(info['markets'])})" for r, info in REGION_INFO.items())

USER_TEMPLATE = """Search for current, live commercial opportunities in global sport matching this brief.

VECTA vertical in focus: {vertical_label} — {vertical_positioning}
Opportunity types to prioritise: {vertical_focus}

Scope: {scope_line}

Search these source categories specifically:
{sources}

Region enum — classify every result into exactly one of these seven values (use the value, e.g. "mena"):
{region_guide}

Find 5-10 specific, current, unclosed opportunities. For each, return an object with exactly these keys:

{{
  "title": "specific named opportunity",
  "organisation_name": "the buying/issuing organisation",
  "organisation_type": "federation|club|government|brand|venue|other",
  "summary": "2-3 sentences: what it is, who issued it, scope, and why it's live now",
  "region": "one of the seven enum values above",
  "market": "specific country/market within that region",
  "value_estimate": "your best-guess commercial value in USD as a number, or null if genuinely unknowable",
  "currency": "USD",
  "deadline": "YYYY-MM-DD submission/decision deadline if known, else null",
  "source_urls": ["most relevant URL(s), at least one"],
  "vertical_fit": "0-100: how directly this maps to the {vertical_label} vertical described above",
  "commercial_value": "0-100: estimated contract value, fee structure and margin potential, relative to VECTA's typical deal size",
  "regional_relevance": "0-100: MENA-anchored opportunities score highest; UK, Europe and global growth corridors follow; scored per the region assigned above",
  "deliverability": "0-100: how realistic a win is given VECTA's current capabilities, references and partner network — be candid, not optimistic",
  "loop_value": "0-100: whether winning this compounds — feeds audience, access, representation or experiences back into VECTA's other verticals"
}}

Rules:
- Only opportunities that are live, open or upcoming — nothing already closed, awarded or expired.
- Prefer a clear route to act: open tenders, expiring rights, new events seeking partners, expansion announcements, named procurement notices.
- Be candid across all five scores; do not cluster everything high. A generic or long-shot opportunity should score low on deliverability or commercial_value.
- Every numeric score field must be an integer 0-100.

Respond with the JSON array only."""

MAX_SEARCHES = 8


def scan_opportunities(vertical: Vertical, scope_line: str) -> list[dict]:
    """Run one AI + web-search pass for a single vertical, scoped by scope_line
    (e.g. "Global — all seven regions" for the scheduled Global Scanner, or
    "MENA — Saudi Arabia only, focused on: stadium hospitality tenders" for
    a Regional Search)."""
    client = Anthropic(api_key=settings.anthropic_api_key)
    info = VERTICAL_INFO[vertical]
    prompt = USER_TEMPLATE.format(
        vertical_label=info["label"],
        vertical_positioning=info["positioning"],
        vertical_focus=info["focus"],
        scope_line=scope_line,
        sources="\n".join(f"- {s}" for s in SOURCE_CATEGORIES),
        region_guide=REGION_ENUM_GUIDE,
    )
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text")
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("Scan returned no parseable results")
    items = json.loads(raw[start : end + 1])
    if not isinstance(items, list):
        raise ValueError("Scan returned unexpected structure")
    return items


def valid_region_value(value: str | None) -> bool:
    if not value:
        return False
    try:
        Region(value)
        return True
    except ValueError:
        return False
