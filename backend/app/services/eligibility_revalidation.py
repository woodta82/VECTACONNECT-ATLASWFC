"""Re-check field assessments made under earlier validation rules (26-27 Oct 2026, items 2 and 4).

Validation v6 (27 Oct 2026, fourth instruction, item 3) adds: stored publication dates re-read with the current date rules
(audited, previous value kept); every live tender signal re-evaluated with the status-freshness rule, so an open status that
only a newer status-less document kept fresh becomes 'unverified' and its opportunities are flagged; route launches without
road-feeder scope move to capacity and trade lanes.

Validation v7 (fifth instruction, item 3): every live tender signal is re-evaluated with the status chronology (publication dates
of status statements; retrieval never supersedes a dated status). An opportunity that was open or actionable only because an
undated notice had been retrieved after a terminal statement goes back to the terminal (or contradictory) status and is flagged
`status_chronology_revalidated`; a terminal-only tender that is not tracked is classified as a historical record.

Validation version 1 compared words, numbers, units and comparators; version 2 (26 Oct) bound each quantity, date,
condition and country to its requirement, subject and role; version 3 (27 Oct) closed the interpretation gaps (only-may-
apply wording, French/Spanish eligibility, eligibility dates vs deadlines, countries in table cells and parentheses,
cities through the register, context-dependent zone abbreviations, withdrawn/annulled status).

For every live MATERIAL field assessment below the current version (eligibility, deadline, status, country, issuer
country, contract territory, origin, destination):
- it is checked again with the current rules against the quote it was validated against, in its claim's context;
- when the verdict or reason changes, the original row is SUPERSEDED (kept, with the reason) and a new row records the
  re-check, linked to the original through `recheck_of`; an `*_revalidated` audit event keeps the previous verdict,
  reason and reviewer decision;
- when a 'supported' verdict is withdrawn, the claim goes back to `proposed` (its previous decision kept in the audit
  event and in the claim note), the claim's derived fact is cleared (a withdrawn deadline is no longer the claim's
  deadline; a withdrawn status is no longer its status), every opportunity built on it gets a review flag and a history
  row, and its signal is re-evaluated so gaps and qualification follow;
- when a deadline's precision changes while still supported (an abbreviation no longer taken as a fact), the claim's
  deadline record follows the re-check;
- when nothing changes, only the version number is updated.

Idempotent: a second run finds nothing below the current version. The job keeps its historical name
('eligibility_revalidation') so queued jobs and schedules stay valid.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..domain import eligibility, identity, relevance
from ..domain.deadlines import StatedDeadline
from ..domain.field_validation import FieldClaim, validate_claim
from ..repo.db import Database
from . import discovery as dsc
from . import ingestion as ing

MATERIAL_FIELDS = ("eligibility", "deadline", "status", "country", "issuer_country", "contract_territory", "origin", "destination")


def _recheck(row: dict[str, Any], now: datetime) -> Any:
    quote = row["quote"] or ""
    kwargs: dict[str, Any] = {}
    if row["field"] == "deadline" and row.get("deadline_source_tz"):
        kwargs["deadline_timezone"] = row["deadline_source_tz"]
    val = validate_claim(row["claim_type"], {row["field"]: FieldClaim(row["value"], quote)}, row.get("document_text") or quote,
                         claim_quote=row.get("claim_quote") or quote, reference_date=now.date(), document_title=row.get("document_title"), **kwargs)
    return next((f for f in val.fields if f.field == row["field"]), None)


def revalidate(db: Database, now: datetime | None = None, *, to_version: int | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    version = to_version or eligibility.VALIDATION_VERSION
    report: dict[str, Any] = {"version": version, "checked": 0, "unchanged": 0, "changed": 0, "withdrawn": 0, "claims_reopened": 0,
                              "opportunities_flagged": 0, "signals": 0, "by_field": {}, "freight_scope_added": 0, "excluded": 0,
                              "run_matches_changed": 0, "freight_scope_changed": 0, "candidates": 0, "announced": 0, "areas_changed": 0,
                              "publication_dates_changed": 0, "status_withdrawn": 0, "chronology_changed": 0,
                              "historical_records": 0}
    signals: set[str] = set()
    reopened: set[str] = set()
    flagged: set[str] = set()
    for fld in MATERIAL_FIELDS:
        for row in db.all("fields_to_recheck", field=fld, version=version):
            report["checked"] += 1
            bf = report["by_field"].setdefault(fld, {"checked": 0, "changed": 0, "withdrawn": 0})
            bf["checked"] += 1
            new = _recheck(row, now)
            same_precision = True
            if new is not None and fld == "deadline" and new.support == "supported" and row["support"] == "supported":
                old_info = StatedDeadline.from_json(row.get("deadline_info"))
                new_info = StatedDeadline.from_json(new.extra.get("deadline"))
                same_precision = (old_info.precision if old_info else None) == (new_info.precision if new_info else None)
            if new is None or (new.support == row["support"] and new.reason == row["reason"] and same_precision):
                db.run("claim_field_set_version", id=row["field_id"], version=version)
                report["unchanged"] += 1
                continue
            report["changed"] += 1
            bf["changed"] += 1
            reason = f"re-checked under validation rules v{version}: {row['support']} -> {new.support}"
            db.run("claim_field_supersede", id=row["field_id"], reason=reason)
            db.run("claim_field_add_recheck", claim=row["claim_id"], doc=row["document_id"], field=fld, value=row["value"][:2000],
                   normalised=(new.normalised if new.support == "supported" else row["normalised"])[:2000], quote=quote_of(row),
                   support=new.support, reason=new.reason[:500], version=version, recheck_of=row["field_id"])
            detail = {"field": fld, "field_id": row["field_id"], "from_support": row["support"], "to_support": new.support, "from_reason": row["reason"],
                      "to_reason": new.reason, "from_version": row["validation_version"], "to_version": version,
                      "previous_review_status": row["review_status"], "assessed_by": row["assessed_by"]}
            db.run("audit_system", event_type=f"{fld}_revalidated", entity_type="claim", entity_id=row["claim_id"], detail=json.dumps(detail))
            if fld == "deadline" and new.support == "supported":
                stated = StatedDeadline.from_json(new.extra.get("deadline"))
                if stated is not None:
                    info = stated.to_json() | {"revalidated": True, "verified": True}
                    info["notes"] = list(info.get("notes") or []) + [f"re-checked under validation rules v{version}"]
                    db.run("claim_set_deadline", id=row["claim_id"], deadline=stated.exact_utc,
                           tz=stated.zone if stated.precision == "instant" else None, info=info)
            if row["support"] == "supported" and new.support != "supported":
                report["withdrawn"] += 1
                bf["withdrawn"] += 1
                if fld == "deadline":
                    db.run("claim_set_deadline", id=row["claim_id"], deadline=None, tz=None, info=None)      # no longer a fact
                if fld == "status":
                    db.run("claim_clear_status", id=row["claim_id"])
                if row["review_status"] in ("proposed", "confirmed") and row["claim_id"] not in reopened:
                    note = (f"{fld} verdict withdrawn by re-check under validation rules v{version} "
                            f"(was '{row['support']}' under v{row['validation_version']}; now '{new.support}': {new.reason}). "
                            f"Previous decision: {row['review_status']}.")
                    db.run("claim_set_review", id=row["claim_id"], review="proposed", note=note[:1000])
                    reopened.add(row["claim_id"])
                for o in db.all("opportunities_of_claim", claim=row["claim_id"]):
                    flag = {"flag": f"{fld}_revalidated" if fld != "eligibility" else "eligibility_revalidated", "field": fld, "claim_id": row["claim_id"],
                            "field_id": row["field_id"], "from": row["support"], "to": new.support, "reason": new.reason, "version": version,
                            "at": now.isoformat(), "previous_review_status": row["review_status"]}
                    db.run("opportunity_add_review_flag", id=o["id"], flag=json.dumps([flag]))
                    db.run("opportunity_history_add", id=o["id"], field="eligibility_evidence" if fld == "eligibility" else "evidence",
                           **{"from": "supported"}, to=new.support, reason=f"{fld}: re-check under validation rules v{version}: {new.reason}", session_ref=None)
                    flagged.add(o["id"])
            signals |= {str(s) for s in (row["signal_ids"] or [])}
    if version >= 6:
        # Publication dates (v6): every stored date is re-read with the current rules. Retrieval time is never a publication date;
        # a date later than retrieval, or sources that disagree, are flagged and not used; the notice's own stated issue date is
        # read from the stored text. The previous value is kept in the audit event.
        from ..domain import publication
        for d in db.all("documents_publication_to_recheck", version=version):
            text = d.get("body_text") or d.get("excerpt") or ""
            cands: list[tuple[str, Any]] = []
            if d.get("published_at") is not None:
                cands.append((d.get("published_at_source") or "page", d["published_at"]))
            cands.append(("document_text", publication.stated_in_text(text)))
            res = publication.resolve(cands, d["retrieved_at"] or now)
            if (res.published_at, res.source, res.flag) == (d.get("published_at"), d.get("published_at_source") if d.get("published_at") else None,
                                                             d.get("publication_flag")):
                db.run("document_set_publication_version", id=d["id"], version=version)
                continue
            db.run("document_set_publication", id=d["id"], published=res.published_at, source=res.source, flag=res.flag, note=res.note, version=version)
            db.run("audit_system", event_type="publication_date_revalidated", entity_type="source_document", entity_id=d["id"],
                   detail=json.dumps({"from": d["published_at"].isoformat() if d.get("published_at") else None, "from_source": d.get("published_at_source"),
                                      "to": res.published_at.isoformat() if res.published_at else None, "to_source": res.source, "flag": res.flag,
                                      "note": res.note, "version": version}))
            report["publication_dates_changed"] += 1
            signals |= {str(r["signal_id"]) for r in db.all("signals_for_document", doc=d["id"])}
    if version >= 5:
        # Freight relevance at the meaning level (v5): every derived scope reading is re-read with the clause rules (exclusion,
        # history, subject, conflicts, no broad keyword shortcuts). A reviewer's own reading is never overwritten.
        for row in db.all("scope_fields_to_recheck", version=version):
            text = " ".join(x for x in (row.get("claim_quote") or row.get("quote") or "", row.get("service_quote") or "") if x)
            fs = relevance.freight_scope(row["claim_type"], row.get("service"), text, row.get("title"), document=row.get("document_text"),
                                         service_supported=row.get("service") is not None, reference_year=now.year)
            if fs.scope == row["normalised"] and fs.reason == row["reason"]:
                db.run("claim_field_set_version", id=row["field_id"], version=version)
                continue
            report["freight_scope_changed"] += 1
            db.run("claim_field_supersede", id=row["field_id"], reason=f"re-checked under validation rules v{version}: {row['normalised']} -> {fs.scope}")
            db.run("claim_field_add_recheck", claim=row["claim_id"], doc=row["document_id"], field="freight_scope", value=fs.scope, normalised=fs.scope,
                   quote=(row.get("quote") or "")[:2000] or None, support=fs.support, reason=fs.reason[:500], version=version, recheck_of=row["field_id"])
            db.run("audit_system", event_type="freight_scope_revalidated", entity_type="claim", entity_id=row["claim_id"],
                   detail=json.dumps({"from": row["normalised"], "to": fs.scope, "from_reason": row["reason"], "to_reason": fs.reason,
                                      "from_version": row["validation_version"], "to_version": version, "previous_review_status": row["review_status"]}))
            if row["normalised"] == "cargo" and fs.scope != "cargo" and row["review_status"] in ("proposed", "confirmed") and row["claim_id"] not in reopened:
                db.run("claim_set_review", id=row["claim_id"], review="proposed",
                       note=(f"freight scope re-checked under validation rules v{version}: was 'cargo', now '{fs.scope}' ({fs.reason}). "
                             f"Previous decision: {row['review_status']}.")[:1000])
                reopened.add(row["claim_id"])
            signals |= {str(x) for x in (row["signal_ids"] or [])}
        # Capability area of route and representation signals (v5): road-feeder launches and appointments belong to trucking/gateways.
        from .ingestion import _stated_trucking
        for sig in db.all("route_signals_live"):
            evidence = [(e.split("\x1f", 2) + ["", ""])[:3] for e in (sig["evidence"] or [])]
            trucking = any(_stated_trucking(ex, doc) for _ct, ex, doc in evidence)
            kinds = {ct for ct, _ex, _doc in evidence}
            ct = "representation_change" if "representation_change" in kinds else "route_launch"
            module, related = identity.module_for(ct, "TRUCKING" if trucking else None)
            if module != sig["module"] and db.one("signal_set_module", id=sig["id"], module=module, related=json.dumps(list(related))) is not None:
                report["areas_changed"] += 1
                db.run("audit_system", event_type="capability_area_revalidated", entity_type="signal", entity_id=sig["id"],
                       detail=json.dumps({"from": sig["module"], "to": module, "version": version,
                                          "reason": "road-feeder service stated" if trucking else
                                          ("no road-feeder service stated: a route launch belongs to capacity and trade lanes" if ct != "representation_change"
                                           else "no road-feeder service stated")}))
    if version >= 4:
        # Freight relevance (v4): every live anchor claim gets a reading from its own wording; passenger-only mandates leave the
        # pipeline when their signals are re-evaluated below. Every live tender signal is re-evaluated, because the effective
        # status now follows publication age and geography follows the live verdicts.
        for row in db.all("claims_without_scope"):
            fs = relevance.freight_scope(row["claim_type"], row.get("service"), row.get("claim_quote") or "", row.get("title"))
            db.run("claim_field_add", claim=row["claim_id"], doc=row["document_id"], field="freight_scope", value=fs.scope, normalised=fs.scope,
                   quote=(row.get("claim_quote") or "")[:2000] or None, support=fs.support, reason=fs.reason[:500], assessed_by="rule", version=version)
            db.run("audit_system", event_type="freight_scope_assessed", entity_type="claim", entity_id=row["claim_id"],
                   detail=json.dumps({"scope": fs.scope, "reason": fs.reason, "version": version}))
            report["freight_scope_added"] += 1
            signals |= {str(s) for s in (row["signal_ids"] or [])}
        signals |= {r["id"] for r in db.all("tender_signals_live")}
    for sid in sorted(signals):
        before = {str(o["id"]): o for o in db.all("opportunities_of_signal", signal=sid)}
        ing.evaluate_signal(db, sid, now)
        report["signals"] += 1
        for oid, prev in before.items():
            cur = db.one("opportunity_scope", id=oid)
            if cur and cur.get("freight_scope") in relevance.EXCLUDED_SCOPES and prev.get("freight_scope") not in relevance.EXCLUDED_SCOPES:
                flag = {"flag": "freight_scope_excluded", "from": prev.get("freight_scope"), "to": cur.get("freight_scope"), "version": version,
                        "at": now.isoformat(), "reason": "not a freight mandate: excluded from the freight pipeline by the re-check"}
                db.run("opportunity_add_review_flag", id=oid, flag=json.dumps([flag]))
                flagged.add(oid)
                report["excluded"] += 1
            elif cur and cur.get("freight_scope") in relevance.REVIEW_SCOPES and prev.get("freight_scope") not in relevance.REVIEW_SCOPES:
                flag = {"flag": "freight_scope_review", "from": prev.get("freight_scope"), "to": cur.get("freight_scope"), "version": version,
                        "at": now.isoformat(), "reason": "freight candidate: the freight scope must be reviewed before any work"}
                db.run("opportunity_add_review_flag", id=oid, flag=json.dumps([flag]))
                flagged.add(oid)
                report["candidates"] += 1
            if cur and (cur.get("tender_status") != prev.get("tender_status")) and cur.get("tender_status") in ("unverified", "historical", "announced"):
                if cur.get("tender_status") == "announced":
                    report["announced"] += 1
                if prev.get("tender_status") in ("open", "revised"):
                    report["status_withdrawn"] += 1     # an open classification the evidence no longer supports
                flag = {"flag": "status_revalidated", "from": prev.get("tender_status"), "to": cur.get("tender_status"), "version": version,
                        "at": now.isoformat(), "reason": cur.get("tender_status_basis")}
                db.run("opportunity_add_review_flag", id=oid, flag=json.dumps([flag]))
                flagged.add(oid)
            if cur and version >= 7 and prev.get("tender_status") in ("open", "revised") \
                    and cur.get("tender_status") in ("cancelled", "awarded", "closed", "contradictory"):
                # v7: an open/actionable status that only retrieval order had placed after a terminal statement is withdrawn
                report["status_withdrawn"] += 1
                report["chronology_changed"] += 1
                flag = {"flag": "status_chronology_revalidated", "from": prev.get("tender_status"), "to": cur.get("tender_status"),
                        "version": version, "at": now.isoformat(), "reason": cur.get("tender_status_basis")}
                db.run("opportunity_add_review_flag", id=oid, flag=json.dumps([flag]))
                flagged.add(oid)
        report["run_matches_changed"] += dsc.refresh_matches(db, sid, now, reason=f"re-check under validation rules v{version}")
        if not before and db.scalar("signal_classification", id=sid) == "historical_record":
            report["historical_records"] += 1
    report["claims_reopened"] = len(reopened)
    report["opportunities_flagged"] = len(flagged)
    return report


def quote_of(row: dict[str, Any]) -> str | None:
    q = (row["quote"] or "")[:2000]
    return q or None
