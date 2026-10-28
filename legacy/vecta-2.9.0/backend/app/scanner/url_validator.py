"""Evidence URL validation (pipeline step 2: URL analysis).

WHY THIS EXISTS
===============
`validate_confirmed_opportunity()` requires at least one validated or
manually reviewed URL before a record can be Confirmed. Nothing was
performing that validation, so every scanned record's evidence stayed at
`not_reviewed` and every Confirmed classification was downgraded to
`unverified_lead` — which in turn made it a non-pipeline classification,
which held qualification at `verification_required`, which kept Pursuit
Priority capped. One missing step, four visible symptoms.

The fix is NOT to let the AI declare its own URLs valid. A model asserting
"this link works" is worth nothing — it is the same claim that needed
checking in the first place, and accepting it would hollow out the whole
evidence hierarchy. ATLAS checks the URL itself.

The validator is injectable so tests are deterministic and offline. The
default performs a real HTTP request; tests pass a stub. Production
behaviour and test behaviour therefore differ in the *transport* only —
the persistence and enforcement path is identical.
"""
from __future__ import annotations

import logging
from typing import Callable, Protocol

logger = logging.getLogger("atlas.scanner.url")

# Result values map onto UrlValidationStatus in taxonomy.py.
VALID = "valid"
UNREACHABLE = "unreachable"
INVALID = "invalid"
NOT_REVIEWED = "not_reviewed"

TIMEOUT_SECONDS = 8


class UrlValidator(Protocol):
    def __call__(self, url: str) -> str:  # returns one of the constants above
        ...


def http_url_validator(url: str) -> str:
    """Default production validator: does this URL actually resolve?

    A HEAD request is tried first (cheap, no body transfer); some servers
    reject HEAD, so a GET fallback follows. Anything that raises is
    `unreachable` rather than `invalid` — the distinction matters, because
    an unreachable URL may be a transient outage worth retrying, while an
    invalid one is malformed and never will be.
    """
    if not url or not url.startswith(("http://", "https://")):
        return INVALID

    try:
        import requests
    except ImportError:  # pragma: no cover - requests is in requirements.txt
        logger.warning("requests unavailable — URLs left unreviewed")
        return NOT_REVIEWED

    headers = {"User-Agent": "ATLAS/2.9 (VECTA Sports commercial intelligence)"}
    try:
        response = requests.head(url, timeout=TIMEOUT_SECONDS, allow_redirects=True, headers=headers)
        if response.status_code == 405 or response.status_code >= 400:
            response = requests.get(
                url, timeout=TIMEOUT_SECONDS, allow_redirects=True, headers=headers, stream=True
            )
        if 200 <= response.status_code < 400:
            return VALID
        if response.status_code in (401, 403):
            # Reachable but gated. It exists — a human can open it with the
            # right access — so this is not "unreachable", but it is not
            # confirmed either.
            return NOT_REVIEWED
        return UNREACHABLE
    except Exception as exc:  # noqa: BLE001
        logger.info("URL validation failed for %s: %s", url, exc)
        return UNREACHABLE


def offline_validator(url: str) -> str:
    """Marks everything not_reviewed. Used when validation is disabled, so
    the system degrades to "unverified" rather than to "assumed valid"."""
    return NOT_REVIEWED


def validate_evidence_urls(
    evidence_records: list[dict], validator: Callable[[str], str] | None = None
) -> list[dict]:
    """Returns the records with `url_validation_status` set by ATLAS.

    Any status the AI supplied is deliberately discarded — the model does
    not get to certify its own sources.
    """
    check = validator or http_url_validator
    out: list[dict] = []
    for record in evidence_records:
        updated = dict(record)
        updated["url_validation_status"] = check(record.get("url", ""))
        out.append(updated)
    return out
