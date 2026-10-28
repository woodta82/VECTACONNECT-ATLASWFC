"""Phase 2 opportunity scan prompt.

Replaces the legacy prompt entirely. Two things make this different from
the old one beyond the larger output shape:

1. **The prompt is generated from the engines.** Factor keys, their 0/50/100
   anchors and the qualification checklist are injected from
   `scoring_v2.py` and `taxonomy.py` rather than written out by hand. A
   hand-maintained prompt drifts from the validator the first time a
   factor is renamed, and the failure mode is silent — the model returns
   the old key, validation drops it, and the score quietly loses a factor.

2. **The output is validated strictly, not slurped.** There is no
   bracket-slicing here. The raw text goes to `ai_schema.validate_ai_response`
   and either satisfies the contract or becomes a parse-failure record.
"""
from __future__ import annotations

import json

from ..config import settings
from ..scoring_v2 import (
    COMMERCIAL_FACTORS,
    RISK_FACTORS,
    STRATEGIC_FACTORS,
    WIN_PROBABILITY_FACTORS,
)
from ..taxonomy import (
    CLASSIFICATION_INFO,
    COMMERCIAL_TYPE_LABELS,
    QUALIFICATION_ITEMS,
    ROUTE_TO_MARKET_LABELS,
    SOURCE_TIER_INFO,
    VERTICAL_V2_INFO,
)

MAX_SEARCHES = 8


def _factor_block(name: str, factors: list[dict]) -> str:
    lines = [f"{name}:"]
    for f in factors:
        a = f["anchors"]
        lines.append(
            f"  - {f['key']} ({f['label']}): 0 = {a['0']} | 50 = {a['50']} | 100 = {a['100']}"
        )
    return "\n".join(lines)


def build_system_prompt() -> str:
    verticals = "\n".join(
        f"  - {k}: {v['definition']}" for k, v in VERTICAL_V2_INFO.items()
    )
    classifications = "\n".join(
        f"  - {k}: {v['definition']} RULE: {v['rule']}" for k, v in CLASSIFICATION_INFO.items()
    )
    tiers = "\n".join(f"  - {k}: {v['definition']}" for k, v in SOURCE_TIER_INFO.items())
    ctypes = ", ".join(COMMERCIAL_TYPE_LABELS.keys())
    routes = ", ".join(ROUTE_TO_MARKET_LABELS.keys())
    qual = "\n".join(
        f"  - {i['key']} ({i['label']}){' [MANDATORY]' if i['mandatory'] else ''}"
        for i in QUALIFICATION_ITEMS
    )

    return f"""You are ATLAS, VECTA Sports' commercial intelligence analyst.

You find real, checkable commercial opportunities in global sport and
return them as strictly structured JSON. You are not a news summariser.

ABSOLUTE RULES — these are the difference between useful intelligence and
a liability:

1. NEVER invent a tender value, a deadline, or an eligibility requirement.
   If a figure is not published, say so via value_status rather than
   estimating silently.
2. NEVER present a wider programme or national strategy figure as the
   contract value available. Those are different fields
   (published_programme_value vs published_contract_value) precisely
   because conflating them produces a wildly inflated pipeline.
3. SEPARATE fact from interpretation from assumption. A verified fact must
   cite an evidence record that actually supports that specific claim. An
   official source proving a tender exists does NOT validate your guess at
   its value.
4. Every evidence record must declare which claims it supports.
5. Distinguish an OPPORTUNITY from a MARKET SIGNAL. Evidence of investment
   or policy intent is a signal, not an opportunity.
6. If evidence is insufficient, say so — classification unverified_lead,
   and list what is missing. An honest gap is more useful than a confident
   guess.
7. Every factor score needs a rationale. A score without a reason is
   unusable.

VECTA VERTICALS (six — choose ONE primary, plus any contributing):
{verticals}

CLASSIFICATIONS:
{classifications}

SOURCE TIERS:
{tiers}

COMMERCIAL TYPES: {ctypes}

ROUTES TO MARKET (these COEXIST — return every one that applies): {routes}

SCORING — score each factor 0-100 with a rationale. Note the direction
carefully: for Strategic, Commercial and Win Probability, 100 is always
better. For RISK, 100 means MOST risk.

{_factor_block("STRATEGIC ALIGNMENT", STRATEGIC_FACTORS)}

{_factor_block("COMMERCIAL ATTRACTIVENESS", COMMERCIAL_FACTORS)}

{_factor_block("WIN PROBABILITY", WIN_PROBABILITY_FACTORS)}

{_factor_block("RISK (100 = most risk)", RISK_FACTORS)}

Only score a factor you have a basis for. Omitting a factor is correct
when you lack evidence; guessing is not. Coverage is tracked, and a
partially-assessed opportunity is treated as provisional rather than
being presented as fully assessed.

QUALIFICATION CHECKLIST — answer every item yes/no/unknown/not_applicable:
{qual}

OUTPUT: a single JSON object matching the schema exactly. No prose before
or after, no markdown fence. Unknown fields are rejected.
"""


def build_user_prompt(scope_line: str) -> str:
    return f"""Search for live commercial opportunities matching this scope:

{scope_line}

Use web search to find real, current sources. Prefer official procurement
portals, government and federation sites, and issuing-organisation pages
(Tier 1) over news coverage (Tier 3).

For each genuine opportunity, return a complete record. If you find
nothing that meets the evidence bar, return an empty records array — that
is a valid and useful answer, and far better than padding with
speculation.

Return JSON only:
{{
  "schema_version": "2.0",
  "records": [ ...opportunity records... ],
  "raw_source_references": ["urls you consulted"]
}}
"""


def run_phase2_scan(scope_line: str) -> str:
    """Executes the scan and returns the RAW response text.

    Returning raw text rather than parsed objects is deliberate: the
    caller validates it, and if validation fails the untouched original
    is what gets stored for diagnosis and retry.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=16000,  # the Phase 2 record is substantially larger than v1
        system=build_system_prompt(),
        messages=[{"role": "user", "content": build_user_prompt(scope_line)}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def estimated_prompt_tokens() -> int:
    """Rough size of the generated system prompt, for the cost estimate
    shown before a manual scan."""
    return len(build_system_prompt()) // 4
