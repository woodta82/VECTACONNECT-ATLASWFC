"""Authorised web search for relationship research (instruction of 28 Oct 2026, item 1; 29 Oct 2026: second provider).

Off unless configured. Two providers:
- SEARCH_PROVIDER=brave with SEARCH_API_KEY: the Brave Search API (`GET {base}/res/v1/web/search?q=...&count=...&country=..`,
  header `X-Subscription-Token`);
- SEARCH_PROVIDER=anthropic: the Claude API's web search tool (ATLAS v1.0's approach), using ANTHROPIC_API_KEY. Only the
  search RESULTS (the URLs and titles the tool returns) are used; nothing the model writes about them is taken as a fact.
Keys stay server-side and are redacted from every log and error. Results are search hits only: each page is then fetched through the SSRF-safe
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
    if settings.search_provider not in PROVIDERS:
        return f"unknown search provider {settings.search_provider}"
    if not settings.search_api_key:
        return "ANTHROPIC_API_KEY is not set" if settings.search_provider == "anthropic" else "SEARCH_API_KEY is not set"
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


def anthropic_web_search(settings: Settings, query: str, country: str | None, count: int) -> list[SearchResult]:
    """The Claude API's server-side web search tool. The request asks for a listing only; the result blocks carry the hits."""
    body = json.dumps({"model": settings.ai_model or "claude-sonnet-4-5", "max_tokens": 400,
                       "system": "Run exactly one web search for the user's query and reply with the single word 'done'. Do not summarise.",
                       "messages": [{"role": "user", "content": query + (f" (country: {country.upper()})" if country and len(country) == 2 else "")}],
                       "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]}).encode()
    req = urllib.request.Request(settings.ai_api_base_url.rstrip("/") + "/v1/messages", data=body, method="POST",
                                 headers={"content-type": "application/json", "x-api-key": settings.search_api_key or settings.anthropic_api_key,
                                          "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed, configured provider endpoint
            data = json.loads(resp.read(2 * 1024 * 1024))
    except urllib.error.HTTPError as exc:
        raise SearchFailed(f"search provider returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SearchFailed(f"search provider unreachable or invalid response: {exc.__class__.__name__}") from exc
    return parse_anthropic_results(data, count)


def parse_anthropic_results(data: dict, count: int) -> list[SearchResult]:
    out: list[SearchResult] = []
    seen: set[str] = set()
    for block in (data or {}).get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "web_search_tool_result":
            continue
        for hit in block.get("content") or []:
            if not isinstance(hit, dict) or hit.get("type") != "web_search_result":
                continue
            u = str(hit.get("url") or "")
            if not u.startswith(("https://", "http://")) or u in seen:
                continue
            seen.add(u)
            out.append(SearchResult(u, str(hit.get("title") or "")[:300], ""))
            if len(out) >= count:
                return out
    return out


PROVIDERS = {"brave": brave, "anthropic": anthropic_web_search}


def search(settings: Settings, query: str, *, country: str | None = None, transport: Transport | None = None) -> list[SearchResult]:
    reason = available(settings)
    if reason:
        raise SearchFailed(reason)
    try:
        return (transport or PROVIDERS[settings.search_provider])(settings, query, country, settings.search_results_per_query)
    except SearchFailed as exc:
        raise SearchFailed(ag.redact(str(exc), settings.secret_values)) from None


def web_search_link(query: str) -> str:
    """A link a person can open to run the same search themselves (labelled as not searched by ATLAS)."""
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)
