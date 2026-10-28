"""Deduplication: collapses the same opportunity found across multiple
sources into a single record. Uses normalised-title matching, which is
simple, fast, and auditable — a full fuzzy/semantic dedup would need a
vector index (noted as a natural next step once volume justifies it)."""
import re


def normalise_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def is_duplicate(title: str, existing_normalised_titles: set[str]) -> bool:
    norm = normalise_title(title)
    if norm in existing_normalised_titles:
        return True
    # Loose containment check catches near-duplicates like
    # "F1 Abu Dhabi hospitality tender 2026" vs "F1 Abu Dhabi hospitality tender"
    for existing in existing_normalised_titles:
        if len(norm) > 12 and (norm in existing or existing in norm):
            return True
    return False
