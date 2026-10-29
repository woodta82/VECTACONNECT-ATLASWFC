"""Every named query is defined once: a second definition silently replaces the first in the dict."""
import re
from collections import Counter
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "repo" / "queries.py"


def test_no_query_name_is_defined_twice():
    names = re.findall(r'^Q\["([^"]+)"\]\s*=', SRC.read_text(), re.M)
    dupes = sorted(n for n, c in Counter(names).items() if c > 1)
    assert not dupes, dupes
