"""Extraction-quality evaluation (26 Oct 2026, evening, item 4).

`notices.py` holds the reviewed evaluation set; `run.py` runs every case through the production pipeline on
PostgreSQL (synthetic fetcher, scripted extractor output) and reports opportunity precision/recall, field accuracy,
false 'supported' decisions and incomplete-document coverage, by category, language, capability area and split.

PROVENANCE OF THE NOTICES: every notice in this set was AUTHORED for this build, in the form of real procurement
and airline notices, because no public portal was reachable from the build environment and no authorised source
was supplied. None is a genuine notice. The harness takes genuine notices in the same shape (a document plus gold
labels), and the report must say which it measured.
"""
