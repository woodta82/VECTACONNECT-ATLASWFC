"""Truthful publication dates (27 Oct 2026, fourth instruction, item 2).

A document's PUBLICATION date says when its publisher issued it. Several things can state it, with different reliability:

- `document_text`: the notice's own words ("Date of issue: 5 October 2026", "Publié le …", "Fecha de publicación: …");
- `page`: the web page's own metadata (article:published_time, dc.date, <time datetime>);
- `pdf_metadata`: the PDF's document-information creation date;
- `feed`: the RSS/Atom item's date.

RETRIEVAL time is when this system fetched the document. It is never publication, and never proof of current status.

Rules:
- Missing dates stay unknown. Nothing is substituted.
- A PDF metadata date within `GENERATED_WINDOW` of retrieval is not used. A portal that builds the PDF on download stamps
  it with the download time, which says nothing about publication.
- A date later than retrieval (plus a day's tolerance for zones) is flagged `future` and not used.
- Usable dates that disagree by more than `CONSISTENT_DAYS` are flagged `inconsistent`. The date is then left unknown, so
  no age is computed from either value.
- Otherwise the most direct statement is used: document text, then page metadata, then PDF metadata, then the feed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

PRIORITY = ("document_text", "page", "pdf_metadata", "feed")
SOURCES = PRIORITY
GENERATED_WINDOW = timedelta(hours=36)
FUTURE_TOLERANCE = timedelta(days=1)
CONSISTENT_DAYS = 7

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_MONTHS.update({"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
                "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
                "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
                "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
                "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "maio": 5, "junho": 6, "julho": 7, "setembro": 9, "outubro": 10,
                "dezembro": 12, "januar": 1, "februar": 2, "märz": 3, "marz": 3, "juni": 6, "juli": 7, "oktober": 10, "dezember": 12})
_MON = r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")"
_LABEL = (r"(?:date\s+of\s+(?:issue|publication)|issue\s+date|publication\s+date|date\s+issued|issued(?:\s+on)?|published(?:\s+on)?|posted(?:\s+on)?|"
          r"date\s+de\s+publication|publi[ée]e?\s+le|date\s+d'[ée]mission|fecha\s+de\s+(?:publicaci[oó]n|emisi[oó]n)|publicad[oa]\s+el|"
          r"data\s+de\s+publica[cç][aã]o|publicad[oa]\s+em|ver[öo]ffentlicht\s+am|datum\s+der\s+ver[öo]ffentlichung)")
_SEP = r"\s*[:\-–—]?\s*"
_D_MON_Y = re.compile(_LABEL + _SEP + r"(\d{1,2})(?:st|nd|rd|th|er|\.)?(?:\s+(?:of\s+|de\s+)?|-)" + _MON + r"\.?,?(?:\s+(?:de\s+)?|-)(\d{4})", re.I)
_MON_D_Y = re.compile(_LABEL + _SEP + _MON + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)
_ISO = re.compile(_LABEL + _SEP + r"(\d{4})-(\d{2})-(\d{2})\b", re.I)
_NUM = re.compile(_LABEL + _SEP + r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", re.I)
TEXT_WINDOW = 1500        # the issue date of a notice is stated at its head


def _utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def stated_in_text(text: str) -> datetime | None:
    """The publication/issue date the notice itself states near its head, or None. A numeric date whose day and month
    could be swapped (05/04/2026) is not read: the convention is unknown."""
    head = (text or "")[:TEXT_WINDOW]
    found: list[tuple[int, date]] = []
    for m in _D_MON_Y.finditer(head):
        try:
            found.append((m.start(), date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))))
        except (ValueError, KeyError):
            continue
    for m in _MON_D_Y.finditer(head):
        try:
            found.append((m.start(), date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))))
        except (ValueError, KeyError):
            continue
    for m in _ISO.finditer(head):
        try:
            found.append((m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
        except ValueError:
            continue
    for m in _NUM.finditer(head):
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 >= b:
            dd, mm = a, b
        elif b > 12 >= a:
            dd, mm = b, a
        elif a == b:
            dd, mm = a, b
        else:
            continue
        try:
            found.append((m.start(), date(y, mm, dd)))
        except ValueError:
            continue
    if not found:
        return None
    return _utc(sorted(found)[0][1])


def pdf_date(value: object) -> datetime | None:
    """A PDF date string ("D:20220314090000Z", "D:20220314090000+02'00'", "D:20220314")."""
    if value is None:
        return None
    m = re.match(r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(Z|[+\-]\d{2}'?\d{2}'?)?", str(value).strip())
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
        hh, mi, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
        tz = timezone.utc
        off = m.group(7)
        if off and off != "Z":
            sign = 1 if off[0] == "+" else -1
            digits = re.sub(r"\D", "", off[1:])
            tz = timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0)))
        return datetime(y, mo, d, hh, mi, ss, tzinfo=tz).astimezone(timezone.utc)
    except ValueError:
        return None


@dataclass(frozen=True)
class PublicationDate:
    published_at: datetime | None
    source: str | None                      # one of SOURCES, or None when unknown
    flag: str | None = None                 # 'future' | 'inconsistent' | None
    note: str | None = None                 # one sentence for the reviewer: what was found and why it was (not) used
    candidates: tuple[tuple[str, str], ...] = ()


def resolve(candidates: Iterable[tuple[str, datetime | None]], retrieved: datetime) -> PublicationDate:
    stated = [(s, d) for s, d in candidates if d is not None]
    listed = tuple((s, d.date().isoformat()) for s, d in stated)
    notes: list[str] = []
    usable: list[tuple[str, datetime]] = []
    future: list[tuple[str, datetime]] = []
    for s, d in stated:
        if s == "pdf_metadata" and abs(d - retrieved) <= GENERATED_WINDOW:
            notes.append(f"the PDF's metadata date ({d.date().isoformat()}) is the retrieval time, so it was generated on download and is "
                         "not a publication date")
            continue
        if d > retrieved + FUTURE_TOLERANCE:
            future.append((s, d))
            continue
        usable.append((s, d))
    flag: str | None = None
    if future:
        flag = "future"
        notes.append("a publication date later than retrieval was stated (" + ", ".join(f"{s}: {d.date().isoformat()}" for s, d in future)
                     + ") and is not used")
    if usable:
        days = [d for _s, d in usable]
        if (max(days) - min(days)).days > CONSISTENT_DAYS:
            notes.append("the publication dates disagree (" + ", ".join(f"{s}: {d.date().isoformat()}" for s, d in usable)
                         + "); the date is left unknown until a person confirms it")
            return PublicationDate(None, None, "inconsistent", "; ".join(notes), listed)
        best = sorted(usable, key=lambda x: PRIORITY.index(x[0]))[0]
        return PublicationDate(best[1], best[0], flag, "; ".join(notes) or None, listed)
    if not notes:
        notes.append("no publication date is stated")
    return PublicationDate(None, None, flag, "; ".join(notes), listed)
