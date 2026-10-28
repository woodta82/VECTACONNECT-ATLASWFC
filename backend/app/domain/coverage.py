"""Account growth: territory-by-service coverage and expansion candidates (module 2).

Contract territory and capability restrictions are BUSINESS rules on
recommendations. They are not user permissions: everything stays visible
to the shared login.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Sequence

from .capability import CapabilityRecord, Credential, capability_readiness

CellState = Literal["covered", "gap", "blocked", "unknown"]


@dataclass(frozen=True)
class Agreement:
    airline: str
    operating_company: str
    territories: frozenset[str]
    services: frozenset[str]
    effective_from: date | None
    effective_to: date | None
    exclusivity: Literal["exclusive", "non_exclusive", "unknown"]
    appointment_rights: Literal["may_extend", "requires_consent", "prohibited", "unknown"]
    status: Literal["draft", "active", "expired", "terminated"] = "active"

    def in_force(self, on: date) -> bool:
        if self.status != "active":
            return False
        if self.effective_from is not None and self.effective_from > on:
            return False
        if self.effective_to is not None and self.effective_to < on:
            return False
        return True


@dataclass(frozen=True)
class ThirdPartyAppointment:
    airline: str
    territory: str
    service: str | None  # None = all services
    holder: str
    exclusivity: Literal["exclusive", "non_exclusive", "unknown"]
    valid_to: date | None


@dataclass
class Cell:
    airline: str
    territory: str
    service: str
    state: CellState
    agreements: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def coverage_matrix(
    airline: str,
    territories: Sequence[str],
    services: Sequence[str],
    agreements: Sequence[Agreement],
    third_party: Sequence[ThirdPartyAppointment],
    on: date,
) -> list[Cell]:
    cells: list[Cell] = []
    for territory in territories:
        for service in services:
            covering = [
                a for a in agreements
                if a.airline == airline and territory in a.territories and service in a.services and a.in_force(on)
            ]
            if covering:
                cells.append(Cell(airline, territory, service, "covered", [a.operating_company for a in covering]))
                continue
            held = [
                t for t in third_party
                if t.airline == airline and t.territory == territory and (t.service is None or t.service == service)
                and (t.valid_to is None or t.valid_to >= on)
            ]
            exclusive = [t for t in held if t.exclusivity == "exclusive"]
            if exclusive:
                cells.append(Cell(airline, territory, service, "blocked",
                                  notes=[f"exclusive appointment held by {t.holder}" for t in exclusive]))
            elif any(t.exclusivity == "unknown" for t in held):
                cells.append(Cell(airline, territory, service, "unknown",
                                  notes=[f"appointment held by {t.holder}; exclusivity unknown" for t in held]))
            else:
                notes = [f"non-exclusive appointment held by {t.holder}" for t in held]
                cells.append(Cell(airline, territory, service, "gap", notes=notes))
    return cells


@dataclass
class ExpansionCandidate:
    airline: str
    territory: str
    service: str
    operating_company: str
    actionable: bool
    blockers: list[str]
    unknowns: list[str]


def expansion_candidates(
    cells: Sequence[Cell],
    agreements: Sequence[Agreement],
    capabilities: Sequence[CapabilityRecord],
    credentials: Sequence[Credential],
    *,
    operating_company: str,
    station_for_territory: dict[str, str | None],
    on: date,
    required_credentials: dict[str, Sequence[str]] | None = None,
) -> list[ExpansionCandidate]:
    """Every non-covered cell becomes a candidate; only those without
    blockers or unknowns are `actionable`."""
    out: list[ExpansionCandidate] = []
    required_credentials = required_credentials or {}
    for cell in cells:
        if cell.state == "covered":
            continue
        blockers: list[str] = []
        unknowns: list[str] = []
        if cell.state == "blocked":
            blockers.extend(cell.notes)
        elif cell.state == "unknown":
            unknowns.extend(cell.notes)

        existing = [a for a in agreements if a.airline == cell.airline and a.operating_company == operating_company and a.in_force(on)]
        if existing:
            rights = {a.appointment_rights for a in existing}
            if "prohibited" in rights:
                blockers.append("existing agreement prohibits extension to new territories")
            elif rights == {"unknown"}:
                unknowns.append("appointment rights under the existing agreement are unknown")
            elif "requires_consent" in rights and "may_extend" not in rights:
                unknowns.append("airline consent required before extension")

        readiness = capability_readiness(
            capabilities, credentials,
            operating_company=operating_company, service_code=cell.service,
            station=station_for_territory.get(cell.territory), on=on,
            required_credentials=required_credentials.get(cell.service, ()),
        )
        blockers.extend(readiness.blockers)
        unknowns.extend(readiness.unknowns)
        out.append(ExpansionCandidate(cell.airline, cell.territory, cell.service, operating_company,
                                      actionable=not blockers and not unknowns, blockers=blockers, unknowns=unknowns))
    return out
