"""The interpretation never presents a cancelled, awarded, closed or expired tender as something WFC could bid for."""
import pytest

from app.domain import overview as ov

BASE = {"module": "airline_representation", "organisation": "Example Air", "record_type": "tender", "deadline_at": "2027-03-15T00:00:00+00:00"}


@pytest.mark.parametrize("status", ["cancelled", "awarded", "closed", "expired"])
def test_terminal_tender_is_not_presented_as_biddable(status):
    out = ov.interpretation({**BASE, "tender_status": status}, ["Kenya"])
    assert out["text"].startswith(f"The source states this tender is {ov.TENDER_STATUS_LABELS[status].lower()}: it cannot be bid for")
    assert "if it is reissued" in out["text"]


@pytest.mark.parametrize("status", ["open", "revised", "announced", "unverified", None])
def test_live_or_unverified_tender_keeps_the_relevance_text(status):
    out = ov.interpretation({**BASE, "tender_status": status}, ["Kenya"])
    assert out["text"].startswith("A representation mandate") and "cannot be bid for" not in out["text"]
    assert out["label"] == "ATLAS interpretation (not a source fact)"
