"""Authorised web search for relationship research (instruction of 28 Oct 2026, item 1).

Off unless configured (SEARCH_PROVIDER=brave and SEARCH_API_KEY). The only implemented provider is the Brave Search API
(`GET {base}/res/v1/web/search?q=...&count=...&country=..`, header `X-Subscription-Token`). The key stays server-side and
is redacted from every log and error. Results are search hits only: each page is then fetched through the SSRF-safe
retriever (robots.txt respected) and read by the attribution rules; nothing is taken from the snippet alone.

When search is not configured, research says so, lists the queries it would have run, and offers them as links a person
can open (never presented as researched results).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from ..config import Settings
from ..domain import ai_guard as ag


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str


class SearchFailed(Exception):
    pass


Transport = Callable[[Settings, str, str | None, int], list[SearchResult]]


def available(settings: Settings) -> str | None:
    """None when search is connected, else the reason it is not."""
    if not settings.search_provider:
        return "no authorised search connector is configured (SEARCH_PROVIDER and SEARCH_API_KEY not set)"
    if not settings.search_api_key:
        return "SEARCH_API_KEY is not set"
    if settings.search_max_queries <= 0:
        return "SEARCH_MAX_QUERIES is 0"
    return None


def brave(settings: Settings, query: str, country: str | None, count: int) -> list[SearchResult]:
    params = {"q": query, "count": str(count)}
    if country and len(country) == 2:
        params["country"] = country.upper()
    url = settings.search_api_base_url.rstrip("/") + "/res/v1/web/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": settings.search_api_key})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed, configured provider endpoint
            data = json.loads(resp.read(2 * 1024 * 1024))
    except urllib.error.HTTPError as exc:
        raise SearchFailed(f"search provider returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SearchFailed(f"search provider unreachable or invalid response: {exc.__class__.__name__}") from exc
    items = ((data or {}).get("web") or {}).get("results") or []
    out: list[SearchResult] = []
    for it in items[:count]:
        if not isinstance(it, dict):
            continue
        u = str(it.get("url") or "")
        if not u.startswith(("https://", "http://")):
            continue
        out.append(SearchResult(u, str(it.get("title") or "")[:300], str(it.get("description") or "")[:500]))
    return out


def search(settings: Settings, query: str, *, country: str | None = None, transport: Transport | None = None) -> list[SearchResult]:
    reason = available(settings)
    if reason:
        raise SearchFailed(reason)
    try:
        return (transport or brave)(settings, query, country, settings.search_results_per_query)
    except SearchFailed as exc:
        raise SearchFailed(ag.redact(str(exc), settings.secret_values)) from None


def web_search_link(query: str) -> str:
    """A link a person can open to run the same search themselves (labelled as not searched by ATLAS)."""
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)
