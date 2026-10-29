"""The eligibility verdict must not depend on set iteration order (PYTHONHASHSEED).

Found in the 4.0.0-wfc.10 evaluation: case t06 alternated between 'unsupported' and 'review_required' between runs
because the first conflicting country decides the verdict and countries came from an unordered set.
"""
import pytest

from app.domain import eligibility

SOURCE = ("Applicants based in Ethiopia must hold an ECAA licence; applicants based outside Ethiopia must hold a licence "
          "if operating in Djibouti.")
VALUE = "applicants based in Djibouti must hold a licence if operating outside Ethiopia"


@pytest.mark.parametrize("order", [["DJ", "ET"], ["ET", "DJ"]])
def test_verdict_independent_of_country_order(monkeypatch, order):
    real = eligibility.countries_mentioned

    class Ordered(set):
        def __iter__(self):
            return iter([c for c in order if c in self] + [c for c in set.__iter__(self) if c not in order])

    monkeypatch.setattr(eligibility, "countries_mentioned", lambda t: Ordered(real(t)))
    out = eligibility.compare(VALUE, SOURCE)
    assert list(eligibility.country_roles(VALUE)) == sorted(eligibility.country_roles(VALUE))
    assert out[0] == "unsupported", out
