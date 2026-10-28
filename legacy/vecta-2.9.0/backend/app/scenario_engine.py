"""Scenario Engine — Sprint 4.

Models four commercial postures for an opportunity and estimates the
consequences of each.

THE DESIGN RISK, STATED PLAINLY
================================
Scenario analysis is theatre if one option always wins. A system that
models four choices and recommends "pursue immediately" every time has
not supported a judgement — it has decorated a foregone conclusion, and
an executive will work that out within a fortnight.

So the engine is built to be genuinely capable of recommending
withdrawal. The tests assert that: given thin coverage, a passed
deadline, or capacity conflict, `withdraw` or `delay` must win. If they
never do, the model is broken regardless of how reasonable its output
looks.

The philosophy the sprint sets out — *reduce uncertainty, do not replace
judgement* — has a concrete implication here. The engine does not return
"the answer". It returns four futures with their costs, ranked, with the
reasoning exposed. The executive decides.
"""
from __future__ import annotations

from datetime import date

SCENARIO_MODEL_VERSION = "1.0"

SCENARIOS = {
    "pursue_now": {
        "label": "Pursue immediately",
        "description": "Commit bid resources now and work the opportunity at full effort.",
    },
    "delay_engagement": {
        "label": "Delay engagement",
        "description": "Hold position, monitor, and revisit when conditions improve.",
    },
    "strengthen_first": {
        "label": "Strengthen relationships first",
        "description": "Invest in coverage and access before committing bid resources.",
    },
    "partner": {
        "label": "Partner with another organisation",
        "description": "Bid jointly, trading margin for capability, coverage or local presence.",
    },
    "withdraw": {
        "label": "Withdraw",
        "description": "Stop investing. Record the reasoning and release the capacity.",
    },
}

IMPACT_SCALE = {
    2: "Strongly positive",
    1: "Positive",
    0: "Neutral",
    -1: "Negative",
    -2: "Strongly negative",
}


def _label(value: int) -> str:
    return IMPACT_SCALE.get(max(-2, min(2, value)), "Neutral")


def _expected_value(contract_value: float | None, win_probability: int | None,
                    modifier: float = 1.0) -> float | None:
    """Contract value × win probability × scenario modifier.

    Returns None rather than zero when inputs are missing — an unknown
    expected value and a zero expected value are different claims, and
    conflating them would make an unquantified opportunity look worthless.
    """
    if contract_value is None or win_probability is None:
        return None
    return round(contract_value * (win_probability / 100) * modifier)


def model_scenarios(
    *,
    contract_value: float | None,
    win_probability: int | None,
    coverage_score: int,
    readiness_score: int,
    days_to_deadline: int | None,
    missing_critical_roles: int,
    capacity_strained: bool,
    competing_pursuits: int = 0,
    is_strategic_account: bool = False,
    relationship_momentum: str = "stable",
    min_viable_value: float | None = None,
) -> dict:
    """Four scenarios with modelled consequences, ranked.

    Modifiers are estimates, and are labelled as such throughout. The
    value is in the *comparison* — whether delaying costs more than it
    saves — not in the precision of any single figure.
    """
    scenarios = []

    # ── 1. Pursue immediately ───────────────────────────────────────────
    # Bidding without coverage means writing to a brief you cannot verify.
    pursue_penalty = 1.0
    pursue_risks = []

    # Below the commercial floor, pursuing is not a viable posture at all.
    # An earlier version applied the threshold only to `withdraw`'s
    # scoring, so a £1.2m opportunity against a £2m floor still returned
    # "pursue immediately" — the model knew the rule and did not apply it
    # where it mattered.
    below_viable = (
        min_viable_value is not None
        and contract_value is not None
        and contract_value < min_viable_value
    )
    if below_viable:
        pursue_penalty *= 0.35
        pursue_risks.append(
            {
                "severity": "high",
                "summary": (
                    f"Contract value {contract_value:,.0f} is below the "
                    f"{min_viable_value:,.0f} minimum viable threshold — bid cost is "
                    "disproportionate to the return."
                ),
            }
        )
    if missing_critical_roles:
        pursue_penalty *= max(0.4, 1 - missing_critical_roles * 0.25)
        pursue_risks.append(
            {
                "severity": "high",
                "summary": f"{missing_critical_roles} critical stakeholder role(s) unmapped — "
                           "bidding without access risks addressing the wrong requirements.",
            }
        )
    if readiness_score < 50:
        pursue_penalty *= 0.8
        pursue_risks.append(
            {"severity": "high", "summary": f"Readiness {readiness_score} — material gaps remain."}
        )
    if capacity_strained:
        pursue_risks.append(
            {
                "severity": "medium",
                "summary": "Delivery capacity strained — winning may create a resourcing problem.",
            }
        )
    if competing_pursuits:
        pursue_risks.append(
            {
                "severity": "medium",
                "summary": f"Competes with {competing_pursuits} other pursuit(s) for the same people.",
            }
        )

    scenarios.append(
        {
            "key": "pursue_now",
            "expected_value": _expected_value(contract_value, win_probability, pursue_penalty),
            "commercial_impact": (
                -2 if below_viable
                else 2 if pursue_penalty > 0.85 else 1 if pursue_penalty > 0.6 else 0
            ),
            "resource_impact": -2 if capacity_strained else -1,
            "strategic_impact": 1 if is_strategic_account else 0,
            "confidence": _scenario_confidence(coverage_score, readiness_score, "pursue_now"),
            "risks": pursue_risks,
            "rationale": (
                "Below the minimum viable contract value — committing a bid team "
                "here consumes capacity that a larger pursuit needs."
                if below_viable
                else "Full commitment now. Highest upside if coverage and readiness hold."
                if pursue_penalty > 0.85
                else "Committing now accepts material execution risk."
            ),
        }
    )

    # ── 2. Delay engagement ─────────────────────────────────────────────
    # Delay is not free — the window closes whether or not VECTA acts.
    delay_risks = []
    delay_modifier = 0.85
    if days_to_deadline is not None:
        if days_to_deadline < 30:
            delay_modifier = 0.3
            delay_risks.append(
                {
                    "severity": "high",
                    "summary": f"Only {days_to_deadline} days remain — delay likely forfeits the opportunity.",
                }
            )
        elif days_to_deadline < 60:
            delay_modifier = 0.6
            delay_risks.append(
                {"severity": "medium", "summary": f"{days_to_deadline} days remain — the window is narrowing."}
            )
    if relationship_momentum in ("declining", "critical"):
        delay_modifier *= 0.8
        delay_risks.append(
            {
                "severity": "high",
                "summary": "Relationships are already deteriorating — delay compounds the decline.",
            }
        )

    scenarios.append(
        {
            "key": "delay_engagement",
            "expected_value": _expected_value(contract_value, win_probability, delay_modifier),
            "commercial_impact": 0 if delay_modifier > 0.7 else -1 if delay_modifier > 0.4 else -2,
            "resource_impact": 1,          # capacity preserved
            "strategic_impact": -1 if is_strategic_account else 0,
            "confidence": _scenario_confidence(coverage_score, readiness_score, "delay_engagement"),
            "risks": delay_risks,
            "rationale": (
                "Preserves capacity at modest cost while conditions are unclear."
                if delay_modifier > 0.7
                else "Delay carries a real cost here — the window is closing."
            ),
        }
    )

    # ── 3. Strengthen relationships first ───────────────────────────────
    # Coverage work raises win probability, but consumes the calendar.
    coverage_headroom = max(0, 85 - coverage_score)
    uplift = min(0.35, coverage_headroom / 100 * 0.5)
    strengthen_risks = []
    strengthen_modifier = 1 + uplift
    if below_viable:
        uplift = 0.0
        strengthen_risks.append(
            {"severity": "high", "summary": "Below minimum viable value — no gain justifies the effort."}
        )

    # Time gates feasibility, not merely value. An earlier version reduced
    # this scenario's expected value when the deadline was close but left
    # its impact score intact, so it kept winning with 18 days remaining —
    # recommending a course of action that could not physically be executed.
    # Days genuinely required, scaled to the gap. Identifying and building
    # a relationship with an unmapped economic buyer is roughly 45 days of
    # elapsed time, not effort — meetings are scheduled at the
    # counterparty's convenience. A flat threshold treated closing a
    # 5-point gap and a 50-point gap as equally achievable.
    days_needed = 30 + coverage_headroom * 0.6 + missing_critical_roles * 30
    time_infeasible = False

    if days_to_deadline is not None and days_to_deadline < days_needed:
        shortfall = days_needed - days_to_deadline
        strengthen_modifier *= max(0.3, 1 - shortfall / days_needed)
        strengthen_risks.append(
            {
                "severity": "high",
                "summary": (
                    f"Roughly {round(days_needed)} days needed to close this coverage gap; "
                    f"{days_to_deadline} remain."
                ),
            }
        )
        # Materially short — the plan cannot land before the decision.
        if days_to_deadline < days_needed * 0.7:
            time_infeasible = True
            uplift = 0.0
            strengthen_risks.append(
                {
                    "severity": "high",
                    "summary": "Relationship work cannot affect this pursuit in the time available.",
                }
            )
    if coverage_score >= 80:
        strengthen_risks.append(
            {
                "severity": "low",
                "summary": "Coverage is already strong — limited further gain available.",
            }
        )

    scenarios.append(
        {
            "key": "strengthen_first",
            "expected_value": _expected_value(contract_value, win_probability, strengthen_modifier),
            "commercial_impact": (
                -1 if time_infeasible
                else 2 if uplift > 0.2 else 1 if uplift > 0.08 else 0
            ),
            "resource_impact": -1 if time_infeasible else 0,
            "strategic_impact": 0 if time_infeasible else (2 if is_strategic_account else 1),
            "confidence": _scenario_confidence(coverage_score, readiness_score, "strengthen_first"),
            "risks": strengthen_risks,
            "rationale": (
                f"Only {days_to_deadline} days remain — relationship work cannot land in time."
                if time_infeasible
                else f"Coverage {coverage_score} leaves {coverage_headroom} points of headroom; "
                     "closing it materially improves win probability."
                if uplift > 0.08
                else "Limited coverage gain available — the case for this is weak."
            ),
        }
    )

    # ── 4. Partner ──────────────────────────────────────────────────────
    # Partnering trades margin for capability. It is the right answer more
    # often than organisations admit — a smaller share of a won bid beats
    # a full share of a lost one — but it is not free, and the model
    # should not treat it as a costless way to fix every gap.
    partner_risks = []
    partner_modifier = 1.0
    partner_rationale = []

    borrows_access = bool(missing_critical_roles or coverage_score < 50)
    if borrows_access:
        # A partner with existing access closes coverage immediately, where
        # relationship-building takes months. Under time pressure this is
        # the whole argument for partnering.
        partner_modifier *= 1.25
        partner_rationale.append("a partner could supply the access VECTA lacks")
    if capacity_strained or competing_pursuits:
        partner_modifier *= 1.15
        partner_rationale.append("shared delivery eases the capacity conflict")
    if readiness_score < 50:
        partner_modifier *= 1.10
        partner_rationale.append("partner capability offsets readiness gaps")

    # Margin dilution is the standing cost. Roughly a third of contract
    # value on a typical joint bid.
    margin_share = 0.65
    partner_risks.append(
        {
            "severity": "medium",
            "summary": "Margin dilution — a joint bid typically returns 60–70% of contract value.",
        }
    )
    if days_to_deadline is not None and days_to_deadline < 30:
        partner_modifier *= 0.6
        partner_risks.append(
            {
                "severity": "high",
                "summary": f"{days_to_deadline} days is tight to agree terms and mobilise a partner.",
            }
        )
    if not partner_rationale:
        partner_risks.append(
            {
                "severity": "medium",
                "summary": "No capability or coverage gap a partner would close — dilution for no gain.",
            }
        )

    partner_gain = partner_modifier > 1.05
    # Borrowed access is worth more when there is no time to build it.
    time_pressured = (
        days_to_deadline is not None and days_to_deadline < 60 and borrows_access
    )
    scenarios.append(
        {
            "key": "partner",
            "expected_value": _expected_value(
                contract_value, win_probability, partner_modifier * margin_share
            ),
            "commercial_impact": 2 if (partner_gain and time_pressured) else 1 if partner_gain else -1,
            "resource_impact": 1,          # shared delivery load
            "strategic_impact": 1 if (partner_gain and not is_strategic_account) else 0,
            "confidence": _scenario_confidence(coverage_score, readiness_score, "partner"),
            "risks": partner_risks,
            "rationale": (
                "Partnering is worth the margin trade here — "
                + "; ".join(partner_rationale) + "."
                if partner_gain
                else "No gap a partner would close — dilution without offsetting benefit."
            ),
        }
    )

    # ── 5. Withdraw ─────────────────────────────────────────────────────
    # A genuine option, not a formality. Withdrawing releases capacity to
    # opportunities VECTA can actually win.
    withdraw_risks = []
    if is_strategic_account:
        withdraw_risks.append(
            {
                "severity": "medium",
                "summary": "Strategic account — withdrawing may affect future positioning.",
            }
        )
    below_threshold = (
        min_viable_value is not None
        and contract_value is not None
        and contract_value < min_viable_value
    )
    if below_threshold:
        withdraw_risks.append(
            {"severity": "low", "summary": "Below minimum viable value — little is being given up."}
        )

    # Withdrawing from an unwinnable pursuit is not a loss — it converts
    # sunk effort into capacity for opportunities VECTA can actually win.
    # Scoring it permanently negative would make withdrawal unreachable,
    # which is how organisations end up bidding everything badly.
    unwinnable = (
        readiness_score < 40
        or below_threshold
        or (missing_critical_roles >= 2 and (days_to_deadline or 999) < 30)
    )

    scenarios.append(
        {
            "key": "withdraw",
            "expected_value": 0,
            "commercial_impact": 1 if unwinnable else (0 if below_threshold else -1),
            "resource_impact": 2,          # full capacity released
            "strategic_impact": (
                0 if unwinnable and not is_strategic_account
                else -2 if is_strategic_account else 0
            ),
            "confidence": _scenario_confidence(coverage_score, readiness_score, "withdraw"),
            "risks": withdraw_risks,
            "rationale": (
                "This pursuit is not winnable in its current state. Withdrawing converts "
                "sunk effort into capacity for opportunities VECTA can win."
                if unwinnable
                else "Forgoes a viable opportunity — only justified if capacity is the binding constraint."
            ),
        }
    )

    # ── enrich and rank ─────────────────────────────────────────────────
    for s in scenarios:
        meta = SCENARIOS[s["key"]]
        s["label"] = meta["label"]
        s["description"] = meta["description"]
        s["commercial_impact_label"] = _label(s["commercial_impact"])
        s["resource_impact_label"] = _label(s["resource_impact"])
        s["strategic_impact_label"] = _label(s["strategic_impact"])
        s["risk_count"] = len(s["risks"])
        s["high_risks"] = sum(1 for r in s["risks"] if r["severity"] == "high")
        s["composite"] = _composite(s)
        s["model_version"] = SCENARIO_MODEL_VERSION

    scenarios.sort(key=lambda s: -s["composite"])
    recommended = scenarios[0]
    runner_up = scenarios[1] if len(scenarios) > 1 else None

    return {
        "scenarios": scenarios,
        "recommended": recommended["key"],
        "recommended_label": recommended["label"],
        "margin": (
            round(recommended["composite"] - runner_up["composite"], 1) if runner_up else None
        ),
        # A close call is itself information — it tells the executive their
        # judgement matters more than usual here.
        "is_close_call": bool(runner_up and abs(recommended["composite"] - runner_up["composite"]) < 8),
        "opportunity_cost": _opportunity_cost(recommended, scenarios),
        "explanation": _explain(recommended, runner_up),
        "model_version": SCENARIO_MODEL_VERSION,
    }


def _scenario_confidence(coverage: int, readiness: int, scenario: str) -> str:
    """How reliable this scenario's estimate is.

    Confidence in a *pursue* estimate depends on coverage — you cannot
    forecast a bid you have no visibility into. Confidence in *withdraw*
    is always high, because doing nothing has predictable consequences.
    """
    if scenario == "withdraw":
        return "high"
    if scenario == "partner":
        # Depends on a counterparty whose willingness ATLAS cannot observe.
        basis = (coverage + readiness) / 2
        return "medium" if basis >= 50 else "low"
    basis = (coverage + readiness) / 2
    if basis >= 70:
        return "high"
    if basis >= 45:
        return "medium"
    return "low"


def _composite(scenario: dict) -> float:
    """Ranks scenarios on impact, risk and expected value.

    Weighted toward commercial impact, but high risks carry a real
    penalty — a scenario with strong upside and three high risks should
    not automatically beat a modest, safe one.
    """
    score = (
        scenario["commercial_impact"] * 22
        + scenario["strategic_impact"] * 10
        + scenario["resource_impact"] * 8
    )
    score -= scenario["high_risks"] * 12
    score -= (scenario["risk_count"] - scenario["high_risks"]) * 4
    confidence_factor = {"high": 1.0, "medium": 0.85, "low": 0.65}[scenario["confidence"]]
    return round(score * confidence_factor, 1)


def _opportunity_cost(recommended: dict, scenarios: list[dict]) -> dict:
    """What the recommended course gives up.

    Naming this is what turns a recommendation into a decision — the
    executive can see the road not taken and its cost.
    """
    alternatives = [s for s in scenarios if s["key"] != recommended["key"]]
    best_alternative = max(alternatives, key=lambda s: s["composite"])

    ev_gap = None
    if (
        recommended["expected_value"] is not None
        and best_alternative["expected_value"] is not None
    ):
        ev_gap = best_alternative["expected_value"] - recommended["expected_value"]

    return {
        "foregone_option": best_alternative["key"],
        "foregone_label": best_alternative["label"],
        "expected_value_difference": ev_gap,
        "what_is_given_up": (
            f"{best_alternative['label']} would preserve "
            f"{best_alternative['resource_impact_label'].lower()} resource impact"
            if best_alternative["resource_impact"] > recommended["resource_impact"]
            else f"{best_alternative['label']} scores {best_alternative['composite']} "
                 f"against {recommended['composite']}"
        ),
    }


def _explain(recommended: dict, runner_up: dict | None) -> str:
    base = f"{recommended['label']} — {recommended['rationale']}"
    if runner_up and abs(recommended["composite"] - runner_up["composite"]) < 8:
        base += (
            f" This is a close call against {runner_up['label'].lower()}; "
            "executive judgement matters more than usual here."
        )
    return base
