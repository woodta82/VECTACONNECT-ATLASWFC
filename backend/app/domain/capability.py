"""Capability and credential readiness (modules 2 and 7).

"Ready to deliver" requires verified capability that is valid on the
delivery date AND every required credential present with a recorded,
unexpired expiry date. Unknown validity is never treated as valid: it
produces `review_required`, not `ready`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Sequence

Readiness = Literal["ready", "blocked", "review_required"]


@dataclass(frozen=True)
class CapabilityRecord:
    operating_company: str
    service_code: str
    station: str | None
    status: Literal["verified", "unverified", "withdrawn"]
    valid_from: date | None
    valid_to: date | None


@dataclass(frozen=True)
class Credential:
    operating_company: str
    credential_type: str
    expires_on: date | None
    station: str | None = None         # None: held company-wide
    issued_on: date | None = None


@dataclass
class ReadinessResult:
    readiness: Readiness
    blockers: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    matched_record: CapabilityRecord | None = None


def capability_readiness(
    records: Sequence[CapabilityRecord],
    credentials: Sequence[Credential],
    *,
    operating_company: str,
    service_code: str,
    station: str | None,
    on: date,
    required_credentials: Sequence[str] = (),
) -> ReadinessResult:
    """Readiness of one company to deliver one service, at one station
    (or company-wide when the station is unknown), on one date.

    Station rules (directive §8):
    - a station-specific record applies ONLY to that station;
    - a company-wide record (no station) applies to every station;
    - when the delivery station is unknown, only company-wide records count:
      a company verified at LHR is not thereby ready at DXB or at an
      unspecified station.
    Credentials follow the same station rule and must be valid on the date.
    """
    blockers: list[str] = []
    unknowns: list[str] = []

    company_records = [r for r in records if r.operating_company == operating_company and r.service_code == service_code]
    if station is None:
        candidates = [r for r in company_records if r.station is None]
        station_only = sorted({r.station for r in company_records if r.station})
    else:
        candidates = [r for r in company_records if r.station in (None, station)]
        station_only = []

    def _valid_on(r: CapabilityRecord) -> bool:
        return (r.status == "verified" and (r.valid_from is None or r.valid_from <= on)
                and r.valid_to is not None and r.valid_to >= on)

    # Prefer: valid on the delivery date, then station-specific over company-wide,
    # then verified, then the latest recorded validity end (unknown last).
    candidates.sort(key=lambda r: (not _valid_on(r), r.station is None, r.status != "verified",
                                   -(r.valid_to.toordinal() if r.valid_to else 0)))
    match = candidates[0] if candidates else None

    if match is None:
        if station_only:
            unknowns.append(f"{service_code} capability is recorded only at {', '.join(station_only)}; that does not establish "
                            "general coverage. Set the delivery station.")
        else:
            blockers.append(f"no capability record for {service_code} at {station or 'company level'}")
    elif match.status == "withdrawn":
        blockers.append("capability withdrawn")
    elif match.status == "unverified":
        blockers.append("capability not verified")
    else:
        if match.valid_from is not None and match.valid_from > on:
            blockers.append(f"capability not valid until {match.valid_from.isoformat()}")
        if match.valid_to is None:
            unknowns.append("capability validity end date not recorded")
        elif match.valid_to < on:
            blockers.append(f"capability expired {match.valid_to.isoformat()}")

    for cred_type in required_credentials:
        held = [c for c in credentials if c.operating_company == operating_company and c.credential_type == cred_type
                and (c.station is None or (station is not None and c.station == station))]
        if not held:
            elsewhere = sorted({c.station for c in credentials if c.operating_company == operating_company
                                and c.credential_type == cred_type and c.station})
            where = f" (held only at {', '.join(elsewhere)})" if elsewhere else ""
            blockers.append(f"required credential {cred_type!r} not held{where}")
            continue
        usable = [c for c in held if c.issued_on is None or c.issued_on <= on]
        if not usable:
            blockers.append(f"credential {cred_type!r} not yet issued on {on.isoformat()}")
            continue
        dated = [c.expires_on for c in usable if c.expires_on is not None]
        if not dated:
            unknowns.append(f"credential {cred_type!r} has no recorded expiry date")
            continue
        latest = max(dated)
        if latest < on:
            blockers.append(f"credential {cred_type!r} expired {latest.isoformat()}")

    if blockers:
        return ReadinessResult("blocked", blockers, unknowns, match)
    if unknowns:
        return ReadinessResult("review_required", blockers, unknowns, match)
    return ReadinessResult("ready", blockers, unknowns, match)
