"""Evidence, deduplication and claim substantiation (build spec §6).

Separations this module enforces:
- A document's reachability, authenticity, relevance and current status are
  separate checks (see `DocumentChecks`); none of them implies claim support.
- Claim support is counted per ANNOUNCEMENT FAMILY, not per document, so
  syndicated copies of one press release add no extra confidence.
- Contradicting evidence is kept and makes the claim `contradicted` (review
  required). It is never silently outvoted.
- Conflicting deadlines are never merged; a deadline replaces an earlier
  one only when it is an explicit revision or comes from the same source
  family.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import deadlines as deadline_mod
from .deadlines import StatedDeadline

AUTHORITY_RANK = {
    "unverified": 0,
    "trade_press": 1,
    "company_release": 2,
    "official_portal": 3,
    "internal_record": 3,
}
AUTHORITATIVE_MIN = AUTHORITY_RANK["company_release"]

_TRACKING_PARAMS = re.compile(r"^(utm_[a-z]+|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|igshid|_hs(enc|mi))$", re.I)


# --------------------------------------------------------------------- URLs and content


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host if port is None or (scheme, port) in {("http", 80), ("https", 443)} else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_PARAMS.match(k)))
    return urlunsplit((scheme, netloc, path, query, ""))


def normalise_text(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    return re.findall(r"[a-z0-9]+", text)


def content_hash(text: str) -> str:
    return hashlib.sha256(" ".join(normalise_text(text)).encode("utf-8")).hexdigest()


def shingles(tokens: Sequence[str], k: int = 3) -> frozenset[str]:
    if len(tokens) < k:
        return frozenset([" ".join(tokens)]) if tokens else frozenset()
    return frozenset(" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class FamilyCandidate:
    family_key: str
    signature: frozenset[str]


FAMILY_THRESHOLD = 0.55


def assign_family(text: str, existing: Iterable[FamilyCandidate], threshold: float = FAMILY_THRESHOLD) -> tuple[str, bool, float]:
    """Return (family_key, is_new, best_similarity).

    Syndicated copies of one announcement share most 3-word shingles even
    when headlines, boilerplate and URLs differ, so they land in the same
    family. Deterministic: same inputs, same answer.
    """
    sig = shingles(normalise_text(text))
    best_key, best = None, 0.0
    for cand in existing:
        sim = jaccard(sig, cand.signature)
        if sim > best or (sim == best and best_key is not None and cand.family_key < best_key):
            best_key, best = cand.family_key, sim
    if best_key is not None and best >= threshold:
        return best_key, False, best
    return content_hash(text)[:32], True, best


# --------------------------------------------------------------------- document checks


CheckResult = Literal["pass", "fail", "unknown"]


@dataclass
class DocumentChecks:
    reachability: CheckResult = "unknown"
    authenticity: CheckResult = "unknown"
    relevance: CheckResult = "unknown"
    current_status: CheckResult = "unknown"


def authenticity_check(final_url: str, source_base_url: str | None) -> CheckResult:
    """A document is authentic for a source only if it was served from that
    source's own host (or a subdomain). Reachability alone proves nothing."""
    if not source_base_url:
        return "unknown"
    final_host = (urlsplit(final_url).hostname or "").lower()
    base_host = (urlsplit(source_base_url).hostname or "").lower()
    if base_host.startswith("www."):
        base_host = base_host[4:]
    if final_host == base_host or final_host.endswith("." + base_host) or final_host == "www." + base_host:
        return "pass"
    return "fail"


# --------------------------------------------------------------------- claims


Stance = Literal["supports", "contradicts", "mentions"]


@dataclass(frozen=True)
class EvidenceLink:
    document_id: str
    family_key: str
    authority: str
    stance: Stance
    published_at: datetime | None = None
    authentic: CheckResult = "unknown"


@dataclass
class ClaimAssessment:
    status: Literal["unverified", "supported", "contradicted"]
    supporting_families: int
    contradicting_families: int
    supporting_documents: int
    best_supporting_authority: str | None
    needs_review: bool
    reasons: list[str] = field(default_factory=list)


def assess_claim(links: Sequence[EvidenceLink]) -> ClaimAssessment:
    supports = [lk for lk in links if lk.stance == "supports" and lk.authentic != "fail"]
    contradicts = [lk for lk in links if lk.stance == "contradicts" and lk.authentic != "fail"]
    support_families = {lk.family_key for lk in supports}
    contra_families = {lk.family_key for lk in contradicts}
    best = max((lk.authority for lk in supports), key=lambda a: AUTHORITY_RANK.get(a, 0), default=None)
    reasons: list[str] = []
    rejected = [lk for lk in links if lk.authentic == "fail"]
    if rejected:
        reasons.append(f"{len(rejected)} document(s) excluded: not served by the claimed source")
    status: Literal["unverified", "supported", "contradicted"]
    if contradicts:
        reasons.append(f"contradicted by {len(contra_families)} independent family(ies); human review required")
        status = "contradicted"
    elif support_families:
        status = "supported"
        if len(supports) > len(support_families):
            reasons.append(
                f"{len(supports)} supporting documents collapse to {len(support_families)} announcement family(ies)"
            )
    else:
        status = "unverified"
        reasons.append("no supporting evidence")
    return ClaimAssessment(
        status=status,
        supporting_families=len(support_families),
        contradicting_families=len(contra_families),
        supporting_documents=len(supports),
        best_supporting_authority=best,
        needs_review=bool(contradicts),
        reasons=reasons,
    )


# --------------------------------------------------------------------- tenders


TenderStatus = Literal["open", "revised", "cancelled", "awarded", "closed", "contradictory"]


@dataclass(frozen=True)
class TenderObservation:
    """One document's statement about a tender. `published_at` is the document's PUBLICATION date (None when unknown or not
    usable, see domain.publication); `retrieved_at` is when it was fetched. Retrieval orders observations whose publication is
    unknown, and is never used as the date of a status."""
    document_id: str
    family_key: str
    source_family: str
    authority: str
    published_at: datetime | None
    status: TenderStatus | None = None
    deadline_utc: datetime | None = None          # exact instant, when the source stated one
    deadline_source_tz: str | None = None
    deadline: StatedDeadline | None = None        # the deadline as stated (any precision); preferred when present
    contradiction: str | None = None              # the document announces it AND says the process has ended
    retrieved_at: datetime | None = None
    reopening: bool = False                       # the statement says the tender was reopened / re-issued / invited again

    def order_key(self) -> tuple[datetime, str]:
        return (self.published_at or self.retrieved_at or datetime.min.replace(tzinfo=timezone.utc), self.document_id)

    def stated(self) -> StatedDeadline | None:
        if self.deadline is not None:
            return self.deadline
        if self.deadline_utc is None:
            return None
        u = self.deadline_utc.astimezone(timezone.utc)
        return StatedDeadline("instant", u.date(), u.strftime("%H:%M"), self.deadline_source_tz or "UTC", 0, u, u, u)


EffectiveStatus = Literal["open", "revised", "cancelled", "awarded", "closed", "contradictory", "expired", "unknown", "unverified", "historical",
                          "announced"]

# Publication age, deadline and verified live status are three different things (27 Oct 2026, second instruction, item 3).
# A notice older than this many days whose open status is not confirmed by a closing date is 'unverified'; one with no
# supported status at all is 'historical'. Configurable (NOTICE_AGE_REVIEW_DAYS); it never invents a closing date.
DEFAULT_AGE_REVIEW_DAYS = 90


def age_review_days() -> int:
    try:
        return max(1, int(os.environ.get("NOTICE_AGE_REVIEW_DAYS", DEFAULT_AGE_REVIEW_DAYS)))
    except ValueError:
        return DEFAULT_AGE_REVIEW_DAYS


@dataclass
class TenderState:
    status: EffectiveStatus
    deadline: StatedDeadline | None
    deadline_conflict: bool
    actionable: bool
    history: list[dict]
    reasons: list[str]
    stated_status: str = "unknown"            # what the sources state (open/revised/cancelled/awarded/closed/contradictory/unknown)
    published_at: datetime | None = None      # newest known publication date among the observations used (any document)
    basis: str = ""                           # one sentence: why the effective status is what it is
    # Freshness of the STATUS (fourth instruction of 27 Oct, item 1), kept apart from the newest document:
    # - status_asserted_at: publication date of the document that first stated the current status;
    # - status_verified_at: publication date of the latest document that stated it again (an explicit reconfirmation);
    # - status_document_id: that latest document;
    # - status_date_known: False when the stating document's publication date is unknown (then no age is claimed);
    # - retrieved_at: the latest retrieval of any observation (when this system last looked; never a status date).
    status_asserted_at: datetime | None = None
    status_verified_at: datetime | None = None
    status_document_id: str | None = None
    status_date_known: bool = False
    retrieved_at: datetime | None = None
    # A status statement that could not be placed in time against another (an undated 'open' after a dated cancellation; a
    # later notice that states 'open' without saying the tender was reopened): kept for a person, never resolved by the
    # order in which documents happened to be retrieved.
    status_conflict: str | None = None

    @property
    def deadline_utc(self) -> datetime | None:
        """The exact instant, only when the source stated one."""
        return self.deadline.exact_utc if self.deadline else None

    @property
    def deadline_source_tz(self) -> str | None:
        return self.deadline.zone if self.deadline and self.deadline.precision == "instant" else None


def _refines(new: StatedDeadline, old: StatedDeadline) -> bool:
    """A more precise statement of the same deadline (date-only -> same day with a time/zone)."""
    order = {"date": 0, "local_time": 1, "instant": 2}
    return new.same_stated_value(old) and order[new.precision] > order[old.precision]


# An explicit reopening of the same tender (fifth instruction of 27 Oct 2026, item 1). Negated or planned wording does not count.
_REOPENING = (r"\bre-?open(?:ed|s|ing)?\b", r"\bre-?(?:issued|launched|advertised|tendered|invited)\b", r"\binvit\w*\b[^.;]{0,80}\bagain\b",
              r"\bonce again\b", r"\brelanc[ée]", r"\br[ée]ouvert", r"\breabiert", r"\brelanzad", r"\bse reabre\b", r"\bwieder er[öo]ffnet")


def reopening_stated(*texts: str | None) -> bool:
    """Whether a status statement says the tender was reopened / re-issued / invited again (affirmed, not negated or planned)."""
    from . import meaning
    for t in texts:
        if not t:
            continue
        m = meaning.first_match(_REOPENING, t)
        if m is not None and meaning.polarity_in_context(t, m.start(), t, length=m.end() - m.start()) == "affirmed":
            return True
    return False


TERMINAL = ("cancelled", "awarded", "closed")
LIVE = ("open", "revised")


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _status_chronology(observations: Sequence[TenderObservation]) -> tuple[str, TenderObservation | None, TenderObservation | None,
                                                                           list[dict], list[str], str | None]:
    """The current status from the STATUS STATEMENTS, by publication date, never by retrieval.

    - Dated statements apply in publication order. Statements of different documents published the same day that disagree
      (open vs cancelled, two different terminal outcomes) are 'contradictory': a person decides.
    - After a dated terminal status (cancelled, awarded, closed) a later dated 'open'/'revised' applies only when it says the
      tender was REOPENED (re-issued, re-launched, invited again); otherwise it may be a copy of the original announcement and
      the record becomes 'contradictory' for review. An older notice rediscovered later is placed by its own date.
    - Undated statements cannot be placed in time. They never override a dated statement: after a dated terminal status an
      undated 'open' (with or without a future closing date) leaves the terminal status in place and is recorded as a
      conflict; an undated terminal statement against a dated live one makes the record 'contradictory'. With no dated
      statement at all, undated statements apply only when they agree.
    Returns (status, latest stating document, first stating document, history entries, reasons, conflict text)."""
    reasons: list[str] = []
    history: list[dict] = []
    status = "unknown"
    doc: TenderObservation | None = None
    first: TenderObservation | None = None
    conflict: str | None = None

    def move(obs: TenderObservation, to: str, basis: str) -> None:
        nonlocal status, doc, first
        history.append({"at": _iso(obs.published_at or obs.retrieved_at), "field": "status", "from": status, "to": to,
                        "document_id": obs.document_id, "date_basis": basis})
        status, doc, first = to, obs, obs

    stated = [o for o in observations if o.status is not None]
    dated = sorted((o for o in stated if o.published_at is not None), key=lambda o: (o.published_at, o.document_id))
    undated = [o for o in stated if o.published_at is None]
    by_day: dict[Any, list[TenderObservation]] = {}
    for o in dated:
        by_day.setdefault(o.published_at.date(), []).append(o)          # type: ignore[union-attr]
    for day in sorted(by_day):
        group = by_day[day]
        docs = {o.document_id for o in group}
        kinds = {("terminal:" + o.status) if o.status in TERMINAL else ("live" if o.status in LIVE else o.status) for o in group}
        if len(docs) > 1 and len(kinds) > 1:
            text = (f"documents published the same day ({day.isoformat()}) state different statuses "
                    f"({', '.join(sorted({o.status or '' for o in group}))}); a person must decide which is current")
            reasons.append("status conflict: " + text)
            conflict = conflict or text
            if status != "contradictory":
                move(group[-1], "contradictory", "published (same day, conflicting)")
            continue
        for o in group:                                                    # one document, or several that agree
            if o.status == status:
                doc = o                                                    # an explicit reconfirmation
                continue
            if status in TERMINAL and o.status in LIVE and not o.reopening:
                text = (f"a notice published {o.published_at.date().isoformat()} states '{o.status}' after the tender was "      # type: ignore[union-attr]
                        f"{status}, without saying it was reopened; it may repeat the original announcement")
                reasons.append("status conflict: " + text)
                conflict = conflict or text
                move(o, "contradictory", "published (after a terminal status, no reopening stated)")
                continue
            move(o, o.status, "published" + (" (reopening stated)" if status in TERMINAL and o.reopening else ""))  # type: ignore[arg-type]
    if undated:
        u_terminal = [o for o in undated if o.status in TERMINAL]
        u_live = [o for o in undated if o.status in LIVE]
        if status in TERMINAL:
            for o in u_live:
                text = (f"a notice with no usable publication date states '{o.status}'"
                        + (" with a closing date" if o.stated() is not None else "")
                        + f"; it does not establish that the {status} status was superseded, so the tender stays {status}")
                reasons.append("status conflict: " + text)
                conflict = conflict or text
        elif status in LIVE and u_terminal:
            o = u_terminal[0]
            text = (f"a notice with no usable publication date states '{o.status}' while the dated evidence states '{status}'; "
                    "which is current cannot be established from the dates")
            reasons.append("status conflict: " + text)
            conflict = conflict or text
            move(o, "contradictory", "retrieved (publication date unknown)")
        elif status in ("unknown",):
            kinds = {("terminal:" + o.status) if o.status in TERMINAL else ("live" if o.status in LIVE else o.status) for o in undated}
            if len(kinds) > 1:
                text = "undated notices state different statuses (" + ", ".join(sorted({o.status or "" for o in undated})) + ")"
                reasons.append("status conflict: " + text)
                conflict = conflict or text
                move(undated[-1], "contradictory", "retrieved (publication date unknown)")
            else:
                for o in sorted(undated, key=lambda o: o.order_key()):
                    if o.status == status:
                        doc = o
                    else:
                        move(o, o.status, "retrieved (publication date unknown)")       # type: ignore[arg-type]
        # status 'contradictory' already needs a person; undated statements add nothing to it
    return status, doc, first, history, reasons, conflict


def resolve_tender(observations: Sequence[TenderObservation], now: datetime, *, age_days: int | None = None,
                   announced: bool = False) -> TenderState:
    """`announced`: a supported tender anchor establishes that the procurement notice exists. Without any supported status
    wording that is 'announced — current status unverified', never 'open'."""
    reasons: list[str] = []
    age_days = age_days if age_days is not None else age_review_days()
    authoritative = sorted(
        (o for o in observations if AUTHORITY_RANK.get(o.authority, 0) >= AUTHORITATIVE_MIN),
        key=lambda o: o.order_key(),
    )
    ignored = len(observations) - len(authoritative)
    if ignored:
        reasons.append(f"{ignored} lower-authority observation(s) recorded but not used for status/deadline")

    history: list[dict] = []
    deadline: StatedDeadline | None = None
    deadline_family: str | None = None
    deadline_document: str | None = None
    conflict = False
    conflict_reasons: list[str] = []

    # STATUS follows evidential chronology (fifth instruction of 27 Oct 2026, item 1), computed apart from the processing order
    # used for deadlines below: retrieval may order processing, it never proves that one status statement supersedes another.
    status, status_doc, status_first, status_history, status_reasons, status_conflict = _status_chronology(authoritative)
    history += status_history
    reasons += status_reasons
    for obs in authoritative:
        when = (obs.published_at or obs.retrieved_at)
        if obs.contradiction and obs.status == "contradictory":
            reasons.append(f"contradictory source: {obs.contradiction}; not shown as open until reviewed")
        stated = obs.stated()
        if stated is None or (deadline is not None and stated.same_stated_value(deadline) and not _refines(stated, deadline)):
            continue
        refinement = deadline is not None and _refines(stated, deadline)
        same_document = deadline is not None and obs.document_id == deadline_document
        # A later notice from the same publisher revises the deadline; two different deadlines in ONE document (neither
        # marked as a revision) contradict each other and are shown as a conflict, never resolved by picking one.
        is_revision = obs.status == "revised" or (deadline_family is not None and obs.source_family == deadline_family and not same_document)
        if deadline is None or is_revision or refinement:
            history.append({"at": when.isoformat() if when else None, "field": "deadline",
                            "from": deadline.label() if deadline else None, "to": stated.label(),
                            "precision": stated.precision, "document_id": obs.document_id})
            deadline, deadline_family, deadline_document = stated, obs.source_family, obs.document_id
            conflict = False
            conflict_reasons = []          # a later revision resolves earlier conflicts; their text goes too
        elif same_document:
            conflict = True
            conflict_reasons.append(f"deadline conflict: the same document states {deadline.label()} and {stated.label()}; confirm with the issuer")
        else:
            conflict = True
            conflict_reasons.append(f"deadline conflict: {deadline.label()} vs {stated.label()} from an independent source; not merged")

    reasons += conflict_reasons
    if conflict:
        deadline = None
    # one history in date order (status entries come from the chronology above, deadline entries from the loop); undated last
    history.sort(key=lambda h: (h.get("at") is None, datetime.fromisoformat(h["at"]).astimezone(timezone.utc) if h.get("at") else datetime.min.replace(tzinfo=timezone.utc)))

    effective: EffectiveStatus = status  # type: ignore[assignment]
    newest = max((o.published_at for o in authoritative if o.published_at), default=None)
    retrieved = max((o.retrieved_at for o in authoritative if o.retrieved_at), default=None)
    # The age that decides freshness is the age of the STATUS STATEMENT, never of the newest document. For a stated status
    # it is the publication date of the latest document stating it; with no stated status (announced / historical) it is
    # the newest publication date of a document that announces the procurement. Unknown dates give no age at all.
    status_when = status_doc.published_at if status_doc is not None else None
    if status in ("open", "revised"):
        age = (now - status_when).days if status_when is not None else None
    else:
        age = (now - newest).days if newest is not None else None
    status_date_unknown = status in ("open", "revised") and status_doc is not None and status_when is None
    basis = ""
    if status in ("open", "revised", "unknown") and deadline is not None and deadline_mod.is_past(deadline, now):
        effective = "expired"
        reasons.append("deadline has passed")
        basis = (f"stated {status}; " if status != "unknown" else "") + f"the stated deadline {deadline.label()} has passed"
    elif status == "unknown" and announced and deadline is not None and not conflict:
        # An announced notice with a stated closing date that has not passed: applications are accepted until that date.
        effective = "open"
        basis = f"announced with a closing date of {deadline.label()} that has not passed (no other status wording)"
        if deadline_mod.may_be_past(deadline, now):
            reasons.append(f"the deadline may already have passed: the source states {deadline.label()}")
    elif status in ("open", "revised") and deadline is not None and deadline_mod.may_be_past(deadline, now):
        reasons.append(f"the deadline may already have passed: the source states {deadline.label()}")
        basis = f"stated {status}; deadline {deadline.label()} may already have passed"
    elif status in ("open", "revised") and deadline is None and not conflict and age is not None and age > age_days:
        # Open wording, no closing date, last stated long ago: the status is not currently verified. No date is invented, and
        # a newer document that does not state the status (eligibility, contact, clarification) does not renew it.
        effective = "unverified"
        reasons.append(f"status not currently verified: '{status}' was last stated {age} days ago (review threshold {age_days} days) with no "
                       "closing date, and no later document states it again; confirm with the issuer")
        basis = f"stated {status} {age} days ago with no closing date; not confirmed by a current source"
        if newest is not None and status_when is not None and newest > status_when:
            basis += f" (newer documents, up to {(now - newest).days} days old, state no status and do not renew it)"
    elif status in ("open", "revised") and deadline is None and not conflict and status_date_unknown:
        # Open wording in a document whose publication date is unknown (or not usable): its age cannot be shown, and the
        # retrieval time proves neither publication nor current status.
        effective = "unverified"
        reasons.append(f"status not currently verified: '{status}' is stated in a document whose publication date is unknown, with no closing "
                       "date; retrieval does not show that it is still open; confirm with the issuer")
        basis = (f"stated {status} in a document with no usable publication date; no closing date"
                 + (f"; retrieved {retrieved.date().isoformat()}, which does not verify the status" if retrieved else ""))
    elif status == "unknown" and announced and not conflict and (age is None or age <= age_days):
        effective = "announced"
        reasons.append("announced — current status unverified: the notice establishes that a procurement exists; nothing states that "
                       "applications are still being accepted")
        basis = ("announced — current status unverified" + (f"; published {age} days ago" if age is not None else "; publication date unknown")
                 + "; no closing date stated")
    elif status == "unknown" and not conflict and age is not None and age > age_days:
        effective = "historical"
        reasons.append(f"historical notice: published {age} days ago (review threshold {age_days} days) with no supported status wording and "
                       "no current confirmation; not shown as open")
        basis = f"no supported status wording; published {age} days ago; treated as historical until a current source confirms it"
    elif status == "unknown":
        basis = "no supported status wording in any authoritative source" + (f"; published {age} days ago" if age is not None else "; publication date unknown")
    elif status in ("open", "revised") and deadline is None:
        basis = f"stated {status}" + (f" {age} days ago" if age is not None else "") + "; no closing date stated"
        if status_doc is not None and status_first is not None and status_doc is not status_first and status_first.published_at is not None:
            basis += f" (first stated {(now - status_first.published_at).days} days ago, reconfirmed since)"
    else:
        basis = f"stated {status}" + (f"; deadline {deadline.label()}" if deadline is not None else "")
    actionable = effective in ("open", "revised") and deadline is not None and not conflict and not deadline_mod.is_past(deadline, now)
    if effective in ("open", "revised") and deadline is None and not conflict:
        reasons.append("deadline unknown")
    if deadline is not None and deadline.precision != "instant":
        reasons.append(f"deadline precision: {deadline.label()}")
    if status == "unknown" and effective not in ("announced", "open"):
        reasons.append("no authoritative status observation")
    return TenderState(effective, deadline, conflict, actionable, history, reasons, stated_status=status, published_at=newest, basis=basis,
                       status_asserted_at=status_first.published_at if status_first is not None else None,
                       status_verified_at=status_when, status_document_id=status_doc.document_id if status_doc is not None else None,
                       status_date_known=status_when is not None, retrieved_at=retrieved, status_conflict=status_conflict)
