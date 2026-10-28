"""Commercial economics (build spec §7).

- Airline revenue, WFC remuneration, incremental costs, exposure and retained
  contribution are separate figures. Revenue is never reported as contribution.
- Unknown remuneration terms mean the value is UNQUALIFIED: no figure.
- A generic contribution estimate (remuneration minus incremental costs) is
  allowed only as a labelled scenario with dated assumptions.
- Pipeline totals never mix currencies, count only the largest of competing
  alternatives (same competition group), and count a referred opportunity
  once.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal, Sequence


@dataclass(frozen=True)
class Assumption:
    text: str
    source: str
    source_date: date


@dataclass(frozen=True)
class CommercialValue:
    opportunity_id: str
    currency: str | None
    airline_revenue: Decimal | None = None
    wfc_remuneration: Decimal | None = None
    incremental_costs: Decimal | None = None
    guarantee_exposure: Decimal | None = None
    basis: Literal["contract", "scenario", "unknown"] = "unknown"
    assumptions: tuple[Assumption, ...] = ()
    value_kind: Literal["potential", "won", "realised"] = "potential"
    competition_group: str | None = None
    referred_from: str | None = None  # operating company that referred it (attribution goes to the receiver)


@dataclass
class ContributionResult:
    status: Literal["contract", "scenario", "unqualified"]
    retained_contribution: Decimal | None
    currency: str | None
    reasons: list[str] = field(default_factory=list)


def retained_contribution(v: CommercialValue) -> ContributionResult:
    if v.basis == "unknown" or v.wfc_remuneration is None or v.currency is None:
        return ContributionResult("unqualified", None, v.currency,
                                  ["remuneration terms unknown: value unqualified (airline revenue is not contribution)"])
    if v.incremental_costs is None:
        return ContributionResult("unqualified", None, v.currency, ["incremental costs unknown"])
    if v.basis == "scenario":
        if not v.assumptions:
            return ContributionResult("unqualified", None, v.currency, ["scenario has no labelled, dated assumptions"])
        return ContributionResult("scenario", v.wfc_remuneration - v.incremental_costs, v.currency,
                                  [f"scenario: {a.text} ({a.source}, {a.source_date.isoformat()})" for a in v.assumptions])
    return ContributionResult("contract", v.wfc_remuneration - v.incremental_costs, v.currency, [])


@dataclass
class PipelineTotals:
    by_currency: dict[str, Decimal]
    counted: list[str]
    excluded: dict[str, str]  # opportunity_id -> reason
    unqualified: list[str]


def pipeline_totals(values: Sequence[CommercialValue], kind: Literal["potential", "won", "realised"] = "potential") -> PipelineTotals:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    excluded: dict[str, str] = {}
    unqualified: list[str] = []
    counted: list[str] = []
    seen: set[str] = set()

    # 1. One row per opportunity: a referral or duplicate subsidiary entry is counted once.
    rows: list[tuple[CommercialValue, ContributionResult]] = []
    for v in values:
        if v.value_kind != kind:
            continue
        if v.opportunity_id in seen:
            excluded[v.opportunity_id] = "duplicate entry for the same opportunity (counted once)"
            continue
        seen.add(v.opportunity_id)
        result = retained_contribution(v)
        if result.retained_contribution is None:
            unqualified.append(v.opportunity_id)
            continue
        rows.append((v, result))

    # 2. Competing alternatives: only the largest in each group counts. A group
    #    whose alternatives are in different currencies cannot be compared
    #    without dated FX, so none of its members is counted.
    groups: dict[str, list[tuple[CommercialValue, ContributionResult]]] = defaultdict(list)
    for v, r in rows:
        if v.competition_group is not None:
            groups[v.competition_group].append((v, r))
    winners: set[str] = set()
    mixed: set[str] = set()
    for g, members in groups.items():
        if len({r.currency for _v, r in members}) > 1:
            for v, _r in members:
                mixed.add(v.opportunity_id)
                excluded[v.opportunity_id] = f"competition group {g} mixes currencies; alternatives not comparable without dated FX"
            continue
        best = max(members, key=lambda m: (m[1].retained_contribution, m[0].opportunity_id))
        winners.add(best[0].opportunity_id)
    for v, r in rows:
        if v.opportunity_id in mixed:
            continue
        if v.competition_group is not None and v.opportunity_id not in winners:
            excluded[v.opportunity_id] = f"alternative in competition group {v.competition_group}; only the largest is counted"
            continue
        totals[r.currency] += r.retained_contribution  # type: ignore[index,operator]
        counted.append(v.opportunity_id)
    return PipelineTotals(dict(totals), counted, excluded, unqualified)
