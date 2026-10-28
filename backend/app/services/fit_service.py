"""Partner fit with invalidation and reassessment (review of 26 Oct 2026, §2 "fit assessments").

A fit assessment is only as good as what it was based on. Each assessment stores its basis:

  claims      every partnership claim about the partner with its status at the time
              (a claim later contradicted, newly supported or newly added changes the basis);
  covered     which of the requested coverage gaps WFC's own ACTIVE representation agreements already covered
              (a new, expired or terminated agreement changes which gaps are still open).

`current()` compares the stored basis with today's evidence and agreements. When they differ the
assessment is reported as invalidated, with each change listed, and is never shown as current.
`reassess()` runs the same rules again on the same partner and gaps and records a new assessment that
names what triggered it and which assessment it supersedes. `reassess_stale()` does this for every
invalidated assessment and is called from the worker's periodic tick, so fits do not silently go stale.

No valuation is ever produced (domain.channels.partner_fit).
"""
from __future__ import annotations

import logging
from typing import Any

from ..domain.channels import PartnerClaim, partner_fit
from ..repo.db import Database
from .audit import RequestMeta, audit


class FitRejected(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _norm_gaps(gaps: list[tuple[str, str]] | list[list[str]]) -> list[tuple[str, str]]:
    out = sorted({(str(t).strip().upper(), str(s).strip().upper()) for t, s in gaps if str(t).strip() and str(s).strip()})
    if len(out) > 200:
        raise FitRejected(422, "at most 200 coverage gaps per assessment")
    return out


log = logging.getLogger(__name__)


def _basis(db: Database, org_id: str, gaps: list[tuple[str, str]]) -> tuple[dict[str, Any], list[PartnerClaim]]:
    # An organisation merged since the assessment: its claims now live on the surviving record.
    org_id = str(db.scalar("organisation_canonical", id=org_id) or org_id)
    claims = [PartnerClaim(r["claim_kind"] or "", r["value"] or "", r["status"], r["claim_id"]) for r in db.all("partner_claims", org=org_id)]
    pairs = {(r["territory"].upper(), r["service"].upper()) for r in db.all("agreement_coverage_pairs")}
    basis = {"claims": sorted(f"{c.claim_id}:{c.status}" for c in claims),
             "covered_by_agreements": sorted(f"{t}/{s}" for t, s in gaps if (t, s) in pairs)}
    return basis, claims


def _changes(old: dict[str, Any], new: dict[str, Any]) -> tuple[list[str], str | None]:
    """Human-readable differences between two bases, and the trigger they imply."""
    out: list[str] = []
    trigger = None
    o_claims = dict(x.split(":", 1) for x in old.get("claims", []))
    n_claims = dict(x.split(":", 1) for x in new.get("claims", []))
    for cid in sorted(set(o_claims) | set(n_claims)):
        if cid not in n_claims:
            out.append(f"evidence claim {cid[:8]} no longer applies")
        elif cid not in o_claims:
            out.append(f"new evidence claim {cid[:8]} ({n_claims[cid]})")
        elif o_claims[cid] != n_claims[cid]:
            out.append(f"evidence claim {cid[:8]} is now {n_claims[cid]} (was {o_claims[cid]})")
    if out:
        trigger = "evidence_changed"
    o_cov, n_cov = set(old.get("covered_by_agreements", [])), set(new.get("covered_by_agreements", []))
    for g in sorted(n_cov - o_cov):
        out.append(f"gap {g} is now covered by an active WFC agreement")
    for g in sorted(o_cov - n_cov):
        out.append(f"gap {g} is no longer covered by an active WFC agreement")
    if (n_cov != o_cov) and trigger is None:
        trigger = "agreements_changed"
    return out, trigger


def assess(db: Database, candidate_id: str, organisation_id: str, gaps: list[tuple[str, str]] | list[list[str]],
           meta: RequestMeta | None, *, trigger: str = "manual", supersedes: str | None = None) -> dict[str, Any]:
    if db.one("network_candidate_get", id=candidate_id) is None:
        raise FitRejected(404, "network candidate not found")
    norm = _norm_gaps(gaps)
    basis, claims = _basis(db, organisation_id, norm)
    covered_by_wfc = set(basis["covered_by_agreements"])
    open_gaps = [(t, s) for t, s in norm if f"{t}/{s}" not in covered_by_wfc]
    fa = partner_fit(open_gaps, claims)
    notes = list(fa.rationale)
    if covered_by_wfc:
        notes.append(f"{len(covered_by_wfc)} requested gap(s) already covered by WFC's active agreements and not counted: "
                     + ", ".join(sorted(covered_by_wfc)))
    fid = db.scalar("fit_insert2", id=candidate_id, result=fa.result,
                    rationale={"covered": fa.covered_gaps, "unsupported": fa.unsupported, "notes": notes},
                    claims="{" + ",".join(fa.evidence_claim_ids) + "}", org=organisation_id,
                    gaps=[list(g) for g in norm], basis=basis, trigger=trigger, supersedes=supersedes)
    if meta is not None:
        audit(db, "fit_assessed", meta, entity_type="network_candidate", entity_id=candidate_id,
              detail={"result": fa.result, "trigger": trigger, "supersedes": supersedes})
    return {"id": str(fid), "result": fa.result, "covered_gaps": fa.covered_gaps, "unsupported": fa.unsupported,
            "evidence_claim_ids": fa.evidence_claim_ids, "rationale": notes, "open_gaps": [f"{t}/{s}" for t, s in open_gaps],
            "trigger": trigger, "supersedes": supersedes, "valuation": None}


def current(db: Database, candidate_id: str) -> dict[str, Any] | None:
    """The latest assessment with its validity against today's evidence and agreements."""
    row = db.one("fit_latest", id=candidate_id)
    if row is None:
        return None
    out = dict(row)
    if row["organisation_id"] is None:      # recorded before bases were kept: cannot be checked, so not trusted as current
        out |= {"valid": False, "changes": ["assessed before its basis was recorded; reassess to confirm"]}
        return out
    basis, _ = _basis(db, str(row["organisation_id"]), [tuple(g) for g in row["gaps"]])  # type: ignore[misc]
    changes, _trigger = _changes(row["basis"] or {}, basis)
    out |= {"valid": not changes, "changes": changes}
    return out


def reassess(db: Database, candidate_id: str, meta: RequestMeta | None, trigger: str | None = None) -> dict[str, Any]:
    row = db.one("fit_latest", id=candidate_id)
    if row is None or row["organisation_id"] is None:
        raise FitRejected(409, "no assessment with a recorded partner and gaps to reassess; run an assessment first")
    gaps = [tuple(g) for g in row["gaps"]]
    if trigger is None:
        basis, _ = _basis(db, str(row["organisation_id"]), gaps)  # type: ignore[arg-type]
        _c, trigger = _changes(row["basis"] or {}, basis)
    return assess(db, candidate_id, str(row["organisation_id"]), gaps, meta, trigger=trigger or "manual",  # type: ignore[arg-type]
                  supersedes=str(row["id"]))


def reassess_stale(db: Database) -> list[str]:
    """Reassess every assessment whose basis changed. Returns the candidate ids reassessed.

    One worker at a time (transaction-scoped advisory lock), so several workers on the same tick never record
    duplicate reassessments; one failing candidate is logged and does not stop the others."""
    done: list[str] = []
    with db.transaction() as tx:
        if not tx.scalar("fit_tick_lock"):
            return done
        for row in tx.all("fit_latest_all"):
            try:
                basis, _ = _basis(tx, str(row["organisation_id"]), [tuple(g) for g in row["gaps"]])  # type: ignore[misc]
                changes, trigger = _changes(row["basis"] or {}, basis)
                if changes:
                    reassess(tx, str(row["network_candidate_id"]), None, trigger=trigger)
                    done.append(str(row["network_candidate_id"]))
            except Exception:  # noqa: BLE001 - logged; the fit stays marked invalid and is retried next tick
                log.exception("reassessing partner fit for candidate %s failed", row["network_candidate_id"])
    return done
