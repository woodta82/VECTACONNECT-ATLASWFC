"""Reading complete documents in sections (amendments of 26 Oct 2026, item 1).

A document longer than one extraction call is split into consecutive sections that together cover every
character. Sections end on a paragraph or sentence boundary where one exists inside the window, and each
section after the first starts a little before the previous one ended (OVERLAP_CHARS), so a sentence that
straddles a boundary is seen whole by at least one call. Nothing is dropped: `covers_everything` is checked by
the tests, and `progress` tells the caller exactly which sections remain.

Sizes are measured in UTF-8 bytes because the extraction budget is in bytes (tokens <= bytes), so a section
of Thai or Chinese text is as safe as one in English.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

OVERLAP_CHARS = 400
_BREAKS = (re.compile(r"\n\s*\n"), re.compile(r"\n"), re.compile(r"(?<=[.!?。！？])\s+"), re.compile(r"\s+"))


@dataclass(frozen=True)
class Section:
    index: int          # 0-based
    start: int          # character offset in the full text (inclusive)
    end: int            # character offset (exclusive)
    text: str


def _cut(text: str, start: int, max_bytes: int) -> int:
    """Largest end > start such that text[start:end] fits in max_bytes, preferring a natural break."""
    # Grow by bytes: find the furthest character index that fits.
    budget = max_bytes
    end = start
    n = len(text)
    while end < n:
        # "</document>" is escaped to "</ document>" in the prompt: one extra byte each, counted here
        size = len(text[end].encode()) + (1 if text[end] == "<" and text.startswith("</document>", end) else 0)
        if size > budget:
            break
        budget -= size
        end += 1
    if end >= n:
        return n
    if end == start:                      # a single character larger than the budget cannot happen for budgets >= 4
        return start + 1
    window = text[start:end]
    floor = len(window) // 2              # do not shrink a section below half the window to find a break
    for pattern in _BREAKS:
        last = None
        for m in pattern.finditer(window):
            if m.end() >= floor:
                last = m.end()
        if last is not None and last < len(window):
            return start + last
    return end


def split(text: str, max_bytes: int, overlap: int = OVERLAP_CHARS) -> list[Section]:
    if max_bytes < 64:
        raise ValueError("section budget too small")
    if not text:
        return [Section(0, 0, 0, "")]
    out: list[Section] = []
    start = 0
    n = len(text)
    while True:
        end = _cut(text, start, max_bytes)
        out.append(Section(len(out), start, end, text[start:end]))
        if end >= n:
            return out
        nxt = max(end - overlap, start + 1)
        # never re-read more than half a section, so progress is guaranteed
        nxt = max(nxt, start + (end - start) // 2)
        start = nxt


def covers_everything(text: str, sections: list[Section]) -> bool:
    pos = 0
    for s in sections:
        if s.start > pos or text[s.start:s.end] != s.text:
            return False
        pos = max(pos, s.end)
    return pos >= len(text)


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class Progress:
    """What has been read of one document. Stored on the document as JSON so a later run resumes."""
    total: int
    done: list[int]
    section_bytes: int
    fingerprint: str        # of the full text; if the text changes, reading starts again
    failures: dict[int, int] | None = None   # failed attempts per section (a section failing repeatedly is given up)
    page_starts: list[int] | None = None     # PDFs: where each page starts, so evidence keeps page numbers on resume

    @property
    def complete(self) -> bool:
        return len(set(self.done)) >= self.total

    def remaining(self) -> list[int]:
        d = set(self.done)
        return [i for i in range(self.total) if i not in d]

    def to_json(self) -> dict:
        return {"total": self.total, "done": sorted(set(self.done)), "section_bytes": self.section_bytes, "fingerprint": self.fingerprint,
                "failures": {str(k): v for k, v in (self.failures or {}).items()}, "page_starts": self.page_starts or []}

    @staticmethod
    def from_json(d: dict | None) -> Progress | None:
        if not d or "total" not in d:
            return None
        return Progress(int(d["total"]), [int(x) for x in d.get("done", [])], int(d.get("section_bytes", 0)), str(d.get("fingerprint", "")),
                        {int(k): int(v) for k, v in (d.get("failures") or {}).items()} or None, list(d.get("page_starts") or []) or None)

    def label(self) -> str:
        return f"read {len(set(self.done))} of {self.total} section(s)"


def locate_quote(text: str, quote: str, hint_start: int = 0) -> tuple[int, int] | None:
    """Character span of a quote in the full text (whitespace-insensitive), searching from the section first."""
    if not quote:
        return None
    i = text.find(quote, hint_start)
    if i < 0:
        i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    words = [re.escape(w) for w in quote.split()]
    if not words:
        return None
    m = re.compile(r"\s+".join(words)).search(text, hint_start) or re.compile(r"\s+".join(words)).search(text)
    return (m.start(), m.end()) if m else None
