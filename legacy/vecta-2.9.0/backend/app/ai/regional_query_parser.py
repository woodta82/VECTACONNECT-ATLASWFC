"""Function Two — Regional Search: parses a natural-language query like
'stadium hospitality tenders in Saudi Arabia closing in Q4' into structured
filters the scanner can act on. A lightweight, cheap Claude call (no web
search) — the actual research happens in opportunity_scan.py afterwards.
"""
import json

from anthropic import Anthropic

from ..config import settings
from ..regions import VERTICAL_INFO

SYSTEM_PROMPT = """You convert a commercial-sport search query into structured filters. \
Respond with a single JSON object and nothing else."""

VERTICAL_GUIDE = "\n".join(f"- {v.value}: {info['label']} — {info['focus']}" for v, info in VERTICAL_INFO.items())

USER_TEMPLATE = """Query: "{query}"

Return JSON:
{{
  "verticals": ["zero or more of: media, talent, connect, experiences, pathways — best matches only"],
  "opportunity_types": ["short phrases describing the opportunity type(s) implied, e.g. 'hospitality tender', 'media rights'"],
  "deadline_hint": "a plain-language deadline window if implied (e.g. 'Q4 2026', 'next 60 days'), else null",
  "keywords": ["key distinguishing terms from the query worth searching on"],
  "scope_summary": "one sentence restating the search intent clearly, to brief a researcher"
}}

Vertical reference:
{vertical_guide}
"""


def parse_regional_query(query: str) -> dict:
    client = Anthropic(api_key=settings.anthropic_api_key)
    prompt = USER_TEMPLATE.format(query=query, vertical_guide=VERTICAL_GUIDE)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "verticals": [],
            "opportunity_types": [],
            "deadline_hint": None,
            "keywords": [query],
            "scope_summary": query,
        }
