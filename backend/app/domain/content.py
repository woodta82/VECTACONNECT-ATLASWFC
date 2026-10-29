"""Readable content from retrieved bytes (directive §3: content extraction).

- HTML: visible text without scripts, styles, navigation, headers, footers
  and forms; the document title; the declared language; a published date
  from standard metadata; same-site links (for listing sources).
- PDF: text layer via pypdf. A PDF without a text layer yields no text and
  is reported as such (no OCR is attempted).
- RSS / Atom: items with title, link and date. DOCTYPE and ENTITY
  declarations are refused before parsing (entity-expansion attacks).

Nothing here interprets the content. It is untrusted data for the
extractor and the reviewer.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

# No character cap: the whole readable text is kept (amendments of 26 Oct 2026, item 1). The only size limit is
# retrieval's byte limit, which fails the target visibly ("response exceeds N bytes") instead of cutting it.

_SKIP = {"script", "style", "noscript", "template", "svg", "nav", "header", "footer", "form", "aside", "button", "select", "iframe"}
_BLOCK = {"p", "div", "section", "article", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "dd", "dt",
          "blockquote", "pre", "main", "td", "th"}
_DATE_META = ("article:published_time", "og:published_time", "datepublished", "publishdate", "pubdate", "date", "dc.date",
              "dcterms.created", "dcterms.issued")


class ContentUnavailable(Exception):
    """No readable text could be obtained (e.g. a scanned PDF)."""


@dataclass
class Extracted:
    text: str
    title: str | None = None
    language: str | None = None
    published_at: datetime | None = None
    links: list[tuple[str, str]] = field(default_factory=list)   # (absolute url, anchor text)
    kind: str = "html"
    page_starts: list[int] = field(default_factory=list)   # PDFs: character offset where each page begins in `text`
    published_source: str | None = None   # 'page' (HTML metadata) or 'pdf_metadata'; see domain.publication
    # Links in navigation, header and footer (excluded from `links`, which lists article candidates). Relationship research
    # uses them: leadership, team and newsroom pages are usually reached from the site navigation.
    nav_links: list[tuple[str, str]] = field(default_factory=list)

    def page_of(self, offset: int) -> int | None:
        """1-based page number for a character offset (PDFs only)."""
        if not self.page_starts:
            return None
        page = 0
        for i, start in enumerate(self.page_starts):
            if start <= offset:
                page = i
        return page + 1


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(v)
        except (TypeError, ValueError, IndexError):
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
            if not m:
                return None
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # A date without an offset is recorded as UTC midnight of that date; it is
    # a publication date used for ordering, never a deadline.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class _HTMLText(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.parts: list[str] = []
        self.skip_depth = 0
        self.in_title = False
        self.title: list[str] = []
        self.lang: str | None = None
        self.meta_dates: list[str] = []
        self.time_dates: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._a_href: str | None = None
        self._a_text: list[str] = []
        self.nav_links: list[tuple[str, str]] = []
        self._nav_href: str | None = None
        self._nav_text: list[str] = []
        self._in_row = False
        self._cell_in_row = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"].split("-")[0].lower()[:8]
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key in _DATE_META and a.get("content"):
                self.meta_dates.append(a["content"])
        if tag == "time" and a.get("datetime"):
            self.time_dates.append(a["datetime"])
        if tag in _SKIP:
            self.skip_depth += 1
            return
        if tag == "a" and a.get("href") and self.skip_depth > 0:
            self._nav_href = urljoin(self.base, a["href"])
            self._nav_text = []
        if tag == "title":
            self.in_title = True
        if tag == "a" and a.get("href") and self.skip_depth == 0:   # navigation, header and footer links are not articles
            self._a_href = urljoin(self.base, a["href"])
            self._a_text = []
        if tag in ("td", "th"):
            # A table row stays one line, cells separated by " | ", so a row's reference, subject, place and date keep
            # their relationship in the text (and in any quote taken from it).
            if self._in_row and self._cell_in_row > 0:
                self.parts.append(" | ")
            self._cell_in_row += 1
            return
        if tag == "tr":
            self._in_row, self._cell_in_row = True, 0
            self.parts.append("\n")
            return
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "title":
            self.in_title = False
        if tag == "a" and self._a_href:
            self.links.append((self._a_href, " ".join("".join(self._a_text).split())))
            self._a_href = None
        if tag == "a" and self._nav_href:
            self.nav_links.append((self._nav_href, " ".join("".join(self._nav_text).split())))
            self._nav_href = None
        if tag in ("td", "th"):
            return
        if tag == "tr":
            self._in_row = False
            self.parts.append("\n")
            return
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
            return
        if self.skip_depth:
            if self._nav_href is not None:
                self._nav_text.append(data)
            return
        self.parts.append(data)
        if self._a_href is not None:
            self._a_text.append(data)


def _clean(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def extract_html(body: bytes, base_url: str, charset: str | None = None) -> Extracted:
    html = body.decode(charset or "utf-8", errors="replace")
    p = _HTMLText(base_url)
    p.feed(html)
    p.close()
    published = next((d for d in (parse_datetime(x) for x in p.meta_dates + p.time_dates) if d), None)
    title = " ".join("".join(p.title).split()) or None
    return Extracted(_clean("".join(p.parts)), title, p.lang, published, p.links, "html", published_source="page" if published else None,
                     nav_links=p.nav_links)


def extract_pdf(body: bytes) -> Extracted:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency declared in requirements.in
        raise ContentUnavailable("PDF support is not installed") from exc
    try:
        reader = PdfReader(io.BytesIO(body))
        pages = [(page.extract_text() or "") for page in reader.pages]      # every page: no page cap
    except Exception as exc:  # noqa: BLE001 - malformed PDFs are a content problem, reported as such
        raise ContentUnavailable(f"PDF could not be read: {exc.__class__.__name__}") from exc
    starts: list[int] = []
    chunks: list[str] = []
    pos = 0
    for raw in pages:
        cleaned = _clean(raw)
        starts.append(pos)
        chunks.append(cleaned)
        pos += len(cleaned) + 2                       # the "\n\n" separator below
    text = "\n\n".join(chunks)                     # not stripped: page offsets stay exact
    if not text.strip():
        raise ContentUnavailable("PDF has no text layer (scanned image); OCR is not performed")
    meta: Any = reader.metadata or {}
    title = str(meta.get("/Title")) if meta.get("/Title") else None
    # The document-information creation date, as a candidate publication date only: domain.publication decides whether it
    # can be used (a PDF generated on download carries the download time).
    from .publication import pdf_date

    created = pdf_date(meta.get("/CreationDate")) if hasattr(meta, "get") else None
    return Extracted(text, title, None, created, [], "pdf", starts, published_source="pdf_metadata" if created else None)


@dataclass
class FeedItem:
    title: str
    link: str
    published_at: datetime | None
    summary: str


_DECL = re.compile(rb"<!(DOCTYPE|ENTITY)", re.I)


def parse_feed(body: bytes, base_url: str) -> list[FeedItem]:
    if _DECL.search(body[:4096]) or b"<!ENTITY" in body:
        raise ContentUnavailable("feed contains DOCTYPE/ENTITY declarations and was refused")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ContentUnavailable(f"feed is not well-formed XML: {exc}") from exc

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    items: list[FeedItem] = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = link = summary = ""
        published = None
        for ch in el:
            name = local(ch.tag)
            if name == "title":
                title = (ch.text or "").strip()
            elif name == "link":
                link = (ch.get("href") or ch.text or "").strip()
            elif name in ("pubdate", "published", "updated", "date") and published is None:
                published = parse_datetime(ch.text)
            elif name in ("description", "summary"):
                summary = re.sub(r"<[^>]+>", " ", ch.text or "").strip()
        if link:
            items.append(FeedItem(title, urljoin(base_url, link), published, " ".join(summary.split())[:1000]))
    return items


def same_site_links(links: list[tuple[str, str]], base_url: str, limit: int) -> list[tuple[str, str]]:
    """Article links on a listing page: same host, http(s), not the page itself,
    de-duplicated, in page order."""
    host = (urlsplit(base_url).hostname or "").lower()
    base_norm = base_url.split("#", 1)[0].rstrip("/")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for url, text in links:
        u = url.split("#", 1)[0]
        parts = urlsplit(u)
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() != host:
            continue
        if u.rstrip("/") == base_norm or u in seen:
            continue
        if re.search(r"\.(jpg|jpeg|png|gif|svg|css|js|zip|docx?|xlsx?)$", parts.path, re.I):
            continue
        seen.add(u)
        out.append((u, text))
        if len(out) >= limit:
            break
    return out


def extract(body: bytes, content_type: str, url: str) -> Extracted:
    if content_type == "application/pdf":
        return extract_pdf(body)
    if content_type in ("text/plain",):
        return Extracted(_clean(body.decode("utf-8", errors="replace")), None, None, None, [], "text")
    if content_type in ("application/json",):
        raise ContentUnavailable("JSON documents are not parsed as articles")
    return extract_html(body, url)


# ---------------------------------------------------------------- relevant article links on a listing page (amendments item 5)

_NAV_WORDS = re.compile(r"^(home|about( us)?|contact( us)?|log ?in|sign ?in|sign ?up|register|privacy( policy)?|terms( of use| and conditions)?|"
                        r"cookies?( policy)?|careers?|jobs|sitemap|search|faq|help|subscribe|newsletter|menu|skip to content|next|previous|"
                        r"more|read more|back|top|en|fr|es|ar|english|francais|espanol|share|print|rss|feed|facebook|twitter|linkedin|youtube|"
                        r"instagram|accessibility|legal|disclaimer|imprint)$", re.I)
_NAV_PATH = re.compile(r"/(about|contact|login|signin|register|privacy|terms|cookies?|careers|jobs|sitemap|search|faq|help|subscribe|"
                       r"tag|tags|category|categories|author|page|feed|rss|wp-login|account|cart|lang)(/|$|\?)", re.I)
_ARTICLE_WORDS = re.compile(r"(tender|rfp|rfq|rfi|procure|notice|bid|award|contract|gssa|cargo|freight|logistic|airline|route|"
                            r"capacity|appoint|agent|handling|trucking|training|outsourc|appel|offre|licitac|convoca|press|news|announce|"
                            r"release|partnership|launch|service)", re.I)


def is_article_link(url: str, text: str | None, listing_url: str, keywords: str | None = None) -> bool:
    """A link on a listing page that is plausibly an article or notice worth reading (not site navigation).
    Deliberately inclusive: anything that might be a notice is kept and queued; only clear navigation is dropped."""
    label = " ".join((text or "").split())
    if label and _NAV_WORDS.match(label):
        return False
    path = urlsplit(url).path or "/"
    if _NAV_PATH.search(path) and not _ARTICLE_WORDS.search(label):
        return False
    base_path = (urlsplit(listing_url).path or "/").rstrip("/")
    words = [w for w in re.split(r"[,;\s]+", (keywords or "").lower()) if len(w) > 2]
    hay = f"{label} {path}".lower()
    if words and any(w in hay for w in words):
        return True
    if _ARTICLE_WORDS.search(hay):
        return True
    if base_path and path.startswith(base_path + "/") and path.rstrip("/") != base_path:
        return True                       # below the listing: an item of the list
    if re.search(r"\d{3,}|[a-z]+-[a-z]+-[a-z]+", path):
        return True                       # an id or a slug
    return len(label.split()) >= 4        # a headline-like link text
