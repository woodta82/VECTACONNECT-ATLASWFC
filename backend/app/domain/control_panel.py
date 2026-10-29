"""Control panel aggregates (29 Oct 2026): opportunities per market and the opportunity score. Framework-free.

Markets are the UN M49 regions and sub-regions of the countries a record names (ISO 3166-1). A record naming several countries
counts once in each market it names, so market counts can add up to more than the number of records; a record naming no
country is counted under "Country not stated". Scores come from app.domain.opportunity_score and cover live records only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from app.domain import overview as ov
from app.domain import opportunity_score as sc

NOT_STATED = "Country not stated"
MARKET_RULE = ("Markets are the UN M49 regions and sub-regions of the countries each record names. A record naming several countries "
               "counts once in each market it names, so market totals can exceed the number of records; a record naming no country "
               "is counted under \"Country not stated\". Only live records are counted and scored.")
REGION_ORDER = ["Africa", "Asia", "Europe", "Americas", "Oceania", NOT_STATED]


def _avg(xs: list[int]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def build(records: list[dict[str, Any]], country_info: Callable[[str], tuple[str, str, str] | None],
          now: datetime | None = None) -> dict[str, Any]:
    """country_info(code) -> (name, region, sub-region) or None."""
    now = now or datetime.now(timezone.utc)
    rows = [r for r in records if r.get("record_type") != "excluded"]
    live = [r for r in rows if sc.scorable(r)]
    for r in live:
        r["score"] = sc.score(r, now)

    def markets(r: dict[str, Any]) -> list[tuple[str, str, str, str]]:
        out = []
        for c in r.get("countries") or []:
            info = country_info(c)
            if info:
                out.append((c, info[0], info[1], info[2]))
        return out or [("", NOT_STATED, NOT_STATED, NOT_STATED)]

    def bucket() -> dict[str, Any]:
        return {"live": 0, "tenders_open": 0, "commercial": 0, "signals": 0, "with_relationships": 0, "scores": []}

    by_region: dict[str, dict[str, Any]] = defaultdict(bucket)
    by_sub: dict[tuple[str, str], dict[str, Any]] = defaultdict(bucket)
    by_country: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(bucket)
    by_area: dict[str, dict[str, Any]] = defaultdict(bucket)

    def tally(b: dict[str, Any], r: dict[str, Any]) -> None:
        b["live"] += 1
        b["tenders_open"] += int(r["record_type"] == "tender" and (r.get("tender_status") or "") in ov.LIVE)
        b["commercial"] += int(r["record_type"] == "commercial")
        b["signals"] += int(r["record_type"] == "market_signal")
        b["with_relationships"] += int(r.get("coverage") in ("existing_relationship", "introduction_available"))
        b["scores"].append(r["score"]["score"])

    for r in live:
        regions, subs = set(), set()
        for code, name, region, sub in markets(r):
            tally(by_country[(code, name, region)], r)
            if region not in regions:
                regions.add(region)
                tally(by_region[region], r)
            if (region, sub) not in subs:
                subs.add((region, sub))
                tally(by_sub[(region, sub)], r)
        tally(by_area[r["module"]], r)

    def finish(b: dict[str, Any]) -> dict[str, Any]:
        scores = b.pop("scores")
        return b | {"avg_score": _avg(scores), "top_score": max(scores) if scores else None}

    total_live = len(live)
    region_list = [{"region": k, "share": round(v["live"] / total_live, 4) if total_live else 0, **finish(v)}
                   for k, v in by_region.items()]
    region_list.sort(key=lambda x: (REGION_ORDER.index(x["region"]) if x["region"] in REGION_ORDER else 99))
    sub_list = sorted(({"region": k[0], "market": k[1], **finish(v)} for k, v in by_sub.items()),
                      key=lambda x: (-x["live"], -(x["avg_score"] or 0), x["market"]))
    country_list = sorted(({"code": k[0] or None, "country": k[1], "region": k[2], **finish(v)} for k, v in by_country.items()),
                          key=lambda x: (-x["live"], -(x["avg_score"] or 0), x["country"]))
    area_list = sorted(({"module": k, "category": ov.CATEGORY_LABELS.get(k, k), **finish(v)} for k, v in by_area.items()),
                       key=lambda x: (-x["live"], x["category"]))

    all_scores = [r["score"]["score"] for r in live]
    dist = []
    for key, label, floor in sc.BANDS:
        ceiling = {"strong": 100, "promising": 74, "developing": 54, "early": 34}[key]
        dist.append({"band": key, "label": label, "range": f"{floor}–{ceiling}",
                     "count": sum(1 for s in all_scores if floor <= s <= ceiling)})
    deciles = [{"range": f"{lo}–{lo + 9 if lo < 90 else 100}", "count": sum(1 for s in all_scores if lo <= s <= (lo + 9 if lo < 90 else 100))}
               for lo in range(0, 100, 10)]
    comp_avgs = []
    for key, mx in sc.WEIGHTS.items():
        pts = [next(c["points"] for c in r["score"]["components"] if c["key"] == key) for r in live]
        label = live[0]["score"]["components"][list(sc.WEIGHTS).index(key)]["label"] if live else key
        comp_avgs.append({"key": key, "label": label, "max": mx, "avg": _avg(pts)})

    scored = sorted(live, key=lambda r: (-r["score"]["score"], r.get("priority_rank") or 10**6))
    soon = [r for r in live if (d := ov._as_dt(r.get("deadline_at"))) and 0 <= (d - now).total_seconds() / 86400 <= 30]
    return {
        "totals": {"live": total_live, "tenders_open": sum(1 for r in live if r["record_type"] == "tender" and (r.get("tender_status") or "") in ov.LIVE),
                   "commercial": sum(1 for r in live if r["record_type"] == "commercial"),
                   "signals": sum(1 for r in live if r["record_type"] == "market_signal"),
                   "deadline_30_days": len(soon), "avg_score": _avg(all_scores),
                   "strong": sum(1 for s in all_scores if s >= 75),
                   "with_relationships": sum(1 for r in live if r.get("coverage") in ("existing_relationship", "introduction_available")),
                   "markets": len([s for s in sub_list if s["market"] != NOT_STATED]),
                   "not_scored": len(rows) - total_live},
        "by_region": region_list, "by_market": sub_list, "by_country": country_list, "by_category": area_list,
        "score_bands": dist, "score_deciles": deciles, "score_components": comp_avgs,
        "scored": [{"id": r["id"], "kind": r["kind"], "title": r["title"], "organisation": r.get("organisation"),
                    "record_type": r["record_type"], "record_type_label": r.get("record_type_label"), "category": r.get("category"),
                    "countries": r.get("countries") or [], "countries_named": r.get("countries_named") or [],
                    "tender_status_label": r.get("tender_status_label"), "deadline_utc": r.get("deadline_utc"),
                    "coverage_label": r.get("coverage_label"), "priority_rank": r.get("priority_rank"), **r["score"]} for r in scored],
        "rule": sc.RULE, "market_rule": MARKET_RULE,
    }
