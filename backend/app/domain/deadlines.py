"""Deadlines with their stated precision (review of 26 Oct 2026, §1 "missing deadline precision").

A source deadline is stored exactly as precise as the source made it:

  precision "date"        "Proposals are due on 30 November 2026": a calendar date only.
  precision "local_time"  "... by 30 November 2026 at 17:00": a time but no stated zone
                          (or a zone abbreviation that is ambiguous, such as CST or IST).
  precision "instant"     "... at 17:00 EAT" / "17:00 UTC+3" / "17:00 London time": an exact moment.

Only an "instant" has `exact_utc`. Nothing else is ever turned into a precise timestamp. Two bounds are
derived for every precision and labelled as such:

  earliest_utc  the earliest moment the stated deadline could fall anywhere (date start, or the stated
                time, at UTC+14). Used ONLY as an internal planning cutoff and labelled that way.
  latest_utc    the latest moment it could fall (end of the date, or the stated time, at UTC-12).
                A tender is treated as expired only after this, so nothing expires early.

A zone the extractor or the source country suggests (e.g. Africa/Nairobi for a Kenyan notice) is kept
as an ASSUMPTION with the instant it would give, never as a source fact.

24:00 is read as the end of the stated day (00:00 the next day). Local times that do not exist or occur
twice in a named zone on that date (daylight-saving transitions) are reported, and the instant is not
claimed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Precision = Literal["date", "local_time", "instant"]
EARLIEST_OFFSET = timedelta(hours=14)    # UTC+14 (Kiribati): the first place a date begins
LATEST_OFFSET = timedelta(hours=-12)     # UTC-12: the last place a date ends


@dataclass(frozen=True)
class StatedDeadline:
    precision: Precision
    day: date                              # the stated calendar date (after 24:00 roll-over)
    local_time: str | None = None          # "HH:MM" as stated, if stated
    zone: str | None = None                # the stated zone as written/resolved: "EAT", "UTC+03:00", "Europe/London"
    offset_minutes: int | None = None      # offset of the stated zone on that date
    exact_utc: datetime | None = None      # only for precision "instant"
    earliest_utc: datetime | None = None
    latest_utc: datetime | None = None
    assumed_zone: str | None = None        # an assumption (extractor or source country), never a source fact
    assumed_utc: datetime | None = None    # the instant under that assumption, labelled as assumed
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("exact_utc", "earliest_utc", "latest_utc", "assumed_utc"):
            d[k] = d[k].astimezone(timezone.utc).isoformat() if d[k] else None
        d["day"] = self.day.isoformat()
        d["notes"] = list(self.notes)
        return d

    @staticmethod
    def from_json(d: dict[str, Any] | None) -> "StatedDeadline | None":
        if not d:
            return None
        ts = {k: datetime.fromisoformat(d[k]) if d.get(k) else None for k in ("exact_utc", "earliest_utc", "latest_utc", "assumed_utc")}
        return StatedDeadline(d["precision"], date.fromisoformat(d["day"]), d.get("local_time"), d.get("zone"), d.get("offset_minutes"),
                              ts["exact_utc"], ts["earliest_utc"], ts["latest_utc"], d.get("assumed_zone"), ts["assumed_utc"],
                              tuple(d.get("notes") or ()))

    def same_stated_value(self, other: "StatedDeadline") -> bool:
        """Same deadline as stated (precision-aware): two date-only notices for the same day agree;
        a date-only and a timed notice for the same day do not conflict, the timed one refines it."""
        if self.precision == "instant" and other.precision == "instant":
            return self.exact_utc == other.exact_utc
        return self.day == other.day and (self.local_time is None or other.local_time is None or self.local_time == other.local_time)

    def label(self) -> str:
        if self.precision == "instant":
            return f"{self.day.isoformat()} {self.local_time} {self.zone}"
        if self.precision == "local_time":
            return f"{self.day.isoformat()} {self.local_time} (time zone not stated)"
        return f"{self.day.isoformat()} (date only; time and zone not stated)"


def _bounds(day: date, hm: tuple[int, int] | None) -> tuple[datetime, datetime]:
    if hm is None:
        start, end = datetime.combine(day, time(0, 0)), datetime.combine(day + timedelta(days=1), time(0, 0))
    else:
        start = end = datetime.combine(day, time(*hm))
    return (start.replace(tzinfo=timezone(EARLIEST_OFFSET)).astimezone(timezone.utc),
            end.replace(tzinfo=timezone(LATEST_OFFSET)).astimezone(timezone.utc))


def _zone_instant(day: date, hm: tuple[int, int], zone_name: str) -> tuple[datetime | None, str | None]:
    """Instant for a local time in a named IANA zone, refusing times that do not exist or are ambiguous."""
    try:
        z = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return None, f"unknown time zone {zone_name}"
    naive = datetime.combine(day, time(*hm))
    a, b = naive.replace(tzinfo=z, fold=0), naive.replace(tzinfo=z, fold=1)
    # A local time in a spring-forward gap does not survive a round trip through UTC.
    if a.astimezone(timezone.utc).astimezone(z).replace(tzinfo=None) != naive:
        return None, f"{hm[0]:02d}:{hm[1]:02d} does not exist in {zone_name} on {day.isoformat()} (clocks go forward)"
    if a.utcoffset() != b.utcoffset():
        return None, f"{hm[0]:02d}:{hm[1]:02d} occurs twice in {zone_name} on {day.isoformat()} (clocks go back); the instant is ambiguous"
    return a.astimezone(timezone.utc), None


def build(day: date, hm: tuple[int, int] | None, *, offset_minutes: int | None = None, zone_label: str | None = None,
          iana_zone: str | None = None, ambiguous_zone: str | None = None, assumed_zone: str | None = None) -> StatedDeadline:
    """Assemble a StatedDeadline from what the source states. `hm` may be (24, 0): end of `day`."""
    notes: list[str] = []
    if hm is not None and hm[0] == 24:
        if hm[1] != 0:
            hm = None
            notes.append("invalid time after 24:00 ignored")
        else:
            day, hm = day + timedelta(days=1), (0, 0)
            notes.append("24:00 read as the end of the stated day (00:00 the next day)")
    local = f"{hm[0]:02d}:{hm[1]:02d}" if hm else None
    earliest, latest = _bounds(day, hm)
    if ambiguous_zone:
        notes.append(f"zone abbreviation {ambiguous_zone} is ambiguous; it is not used as a fact")
    exact = None
    zone = None
    if hm is not None and iana_zone:
        exact, problem = _zone_instant(day, hm, iana_zone)
        if problem:
            notes.append(problem)
        else:
            zone = iana_zone
            off = exact.astimezone(ZoneInfo(iana_zone)).utcoffset() if exact else None
            offset_minutes = int(off.total_seconds() // 60) if off is not None else None
    elif hm is not None and offset_minutes is not None:
        exact = datetime.combine(day, time(*hm), tzinfo=timezone(timedelta(minutes=offset_minutes))).astimezone(timezone.utc)
        zone = zone_label or f"UTC{'+' if offset_minutes >= 0 else '-'}{abs(offset_minutes) // 60:02d}:{abs(offset_minutes) % 60:02d}"
    elif hm is None and (offset_minutes is not None or iana_zone):
        notes.append("a zone is stated but no time; the deadline is the stated date")
    if exact is not None:
        return StatedDeadline("instant", day, local, zone, offset_minutes, exact, exact, exact, None, None, tuple(notes))
    assumed_utc = None
    if assumed_zone and hm is not None:
        assumed_utc, problem = _zone_instant(day, hm, assumed_zone)
        if problem:
            notes.append(f"assumption not applied: {problem}")
        else:
            notes.append(f"time zone not stated in the source; {assumed_zone} is an assumption, not a source fact")
    elif assumed_zone:
        notes.append(f"time not stated in the source; no time is assumed (zone hint {assumed_zone} not applied)")
    precision: Precision = "local_time" if hm is not None else "date"
    if precision == "date":
        notes.append("time and zone not stated in the source")
    elif not ambiguous_zone:
        notes.append("time zone not stated in the source")
    return StatedDeadline(precision, day, local, None, None, None, earliest, latest, assumed_zone if assumed_utc else None, assumed_utc,
                          tuple(notes))


def is_past(d: StatedDeadline, now: datetime) -> bool:
    """Passed for certain: even the latest reading of the stated deadline is before now."""
    return d.latest_utc is not None and d.latest_utc <= now


def may_be_past(d: StatedDeadline, now: datetime) -> bool:
    """Possibly passed: the earliest reading is before now but the latest is not."""
    return d.earliest_utc is not None and d.earliest_utc <= now < (d.latest_utc or now)
