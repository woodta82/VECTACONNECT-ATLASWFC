"""Amendments of 26 Oct 2026, items 1-4, at rule level: complete reading in sections, interpretation of
genuine opportunities, structured eligibility and document-wide contradictions."""
from datetime import date

import pytest

from app.ai import extraction as ai
from app.domain import ai_guard as ag
from app.domain import content as ct
from app.domain import eligibility as el
from app.domain import meaning
from app.domain import sections as sec
from app.domain.field_validation import FieldClaim as F
from app.domain.field_validation import validate_claim

REF = date(2026, 10, 26)


def v(claim_type, fields, text, quote=None):
    return validate_claim(claim_type, fields, text, claim_quote=quote or text, reference_date=REF)


def field(val, name):
    return next(f for f in val.fields if f.field == name)


# ---------------------------------------------------------------- 1. complete reading

@pytest.mark.parametrize("text", [
    "Example Air invites GSSA proposals. " * 6000,
    ("货运总代理招标。" * 3000 + "\n\n") * 4,
    "\n\n".join(f"Paragraph {i}: " + "cargo sales and service representation " * 40 for i in range(300)),
])
def test_sections_cover_every_character_and_fit_one_call(text):
    parts = sec.split(text, ai.SECTION_BYTES)
    assert len(parts) > 1 and sec.covers_everything(text, parts)
    assert all(len(p.text.encode()) <= ai.SECTION_BYTES for p in parts)
    assert all(parts[i + 1].start < parts[i].end for i in range(len(parts) - 1))       # overlapping: no boundary gap
    for p in parts:
        ag.build_prompt(p.text, max_chars=len(p.text), max_bytes=ai.MAX_INPUT_TOKENS - ai.MESSAGE_OVERHEAD_TOKENS)


def test_sections_prefer_paragraph_boundaries():
    text = "\n\n".join("x" * 900 for _ in range(60))
    parts = sec.split(text, 5000)
    assert all(p.text.endswith("\n\n") or p.end == len(text) for p in parts)


def test_short_text_is_one_section_and_progress_resumes():
    parts = sec.split("A short notice.", ai.SECTION_BYTES)
    assert len(parts) == 1 and parts[0].text == "A short notice."
    p = sec.Progress(4, [0, 1], ai.SECTION_BYTES, "f")
    assert not p.complete and p.remaining() == [2, 3] and p.label() == "read 2 of 4 section(s)"
    assert sec.Progress.from_json(p.to_json()) == p


def test_oversized_text_is_refused_never_cut():
    with pytest.raises(ag.DocumentTooLong):
        ag.build_prompt("x" * 100_000, max_chars=100_000, max_bytes=20_000)


def test_html_text_is_not_truncated():
    body = ("<html><body><main>" + "<p>Cargo notice paragraph with GSSA wording.</p>" * 8000
            + "<p>FINAL SENTENCE: proposals are due on 30 November 2026.</p></main></body></html>").encode()
    page = ct.extract_html(body, "https://portal.example/n/1")
    assert len(page.text) > 300_000 and page.text.endswith("proposals are due on 30 November 2026.")


def test_quote_location_in_full_text():
    text = "Intro.\n\n" + "filler " * 5000 + "Example Air invites GSSA proposals for Kenya."
    span = sec.locate_quote(text, "Example Air invites GSSA proposals for Kenya.")
    assert span is not None and text[span[0]:span[1]] == "Example Air invites GSSA proposals for Kenya."


# ---------------------------------------------------------------- 2. genuine opportunities

@pytest.mark.parametrize("text", [
    "Example Air invites GSSA proposals for Kenya. There is no application fee.",
    "Example Air invites GSSA proposals for Kenya with no application fee and no bid bond.",
    "No application fee is charged: Example Air invites GSSA proposals for Kenya.",
    "Example Air invites GSSA proposals for Kenya to replace the framework agreement signed in 2019.",
    "Example Air invites GSSA proposals for Kenya; the previous contract with the incumbent agent expired in 2025.",
    "Under the 2021 framework agreement, Example Air invites call-off proposals from GSSA providers for Kenya.",
    "Example Air, which last appointed a GSSA in 2018, invites GSSA proposals for Kenya.",
    "Example Air invites GSSA proposals for Kenya, to be received no later than 30 November 2026; tender documents are free of charge.",
])
def test_genuine_current_tenders_are_not_invalidated(text):
    r = v("gssa_tender", {"status": F("open", text), "country": F("Kenya", text)}, text)
    assert r.type_supported, r.type_reason
    assert field(r, "status").support == "supported", field(r, "status").reason
    assert r.contradiction is None


@pytest.mark.parametrize("text,why", [
    ("Example Air is not inviting GSSA proposals for Kenya.", "negated"),
    ("Example Air has no plans to invite GSSA proposals for Kenya.", "negated"),
    ("In 2019 Example Air invited GSSA proposals for Kenya.", "past"),
])
def test_real_negations_and_history_still_count(text, why):
    assert v("gssa_tender", {}, text).type_supported is False


# ---------------------------------------------------------------- 3. eligibility structure

SRC = "Bidders must have at least 5 years of GSSA experience and an annual turnover of not less than USD 2 million."


@pytest.mark.parametrize("value,expected,why", [
    ("at least 5 years of GSSA experience", "supported", "match"),
    ("a maximum of 5 years of GSSA experience", "unsupported", "turns it into a maximum"),
    ("at least 3 years of GSSA experience", "unsupported", "not 3"),
    ("at least 5 months of GSSA experience", "unsupported", "in year"),
    ("5 years of GSSA experience", "review_required", "drops it"),
    ("annual turnover of not less than USD 2 million", "supported", "match"),
    ("annual turnover of not less than EUR 2 million", "unsupported", "money"),
])
def test_minimum_maximum_numbers_and_units(value, expected, why):
    f = field(v("eligibility", {"eligibility": F(value, SRC)}, SRC), "eligibility")
    assert f.support == expected, (value, f.reason)
    if expected != "supported" and why != "money":
        assert why in f.reason


def test_and_or_combinations_are_preserved():
    src = "Applicants must hold an IATA cargo agent accreditation or a Kenya CAA licence."
    assert field(v("eligibility", {"eligibility": F("must hold an IATA cargo agent accreditation and a Kenya CAA licence", src)}, src),
                 "eligibility").support == "unsupported"
    assert field(v("eligibility", {"eligibility": F("must hold an IATA cargo agent accreditation", src)}, src),
                 "eligibility").support == "review_required"
    assert field(v("eligibility", {"eligibility": F("must hold an IATA cargo agent accreditation or a Kenya CAA licence", src)}, src),
                 "eligibility").support == "supported"
    both = "Applicants must hold an IATA cargo agent accreditation and a Kenya CAA licence."
    assert field(v("eligibility", {"eligibility": F("an IATA cargo agent accreditation or a Kenya CAA licence", both)}, both),
                 "eligibility").support == "unsupported"


def test_conditions_and_dates_are_preserved():
    src = "Where the bidder is based outside Kenya, it must hold a Kenya CAA licence valid until 31 December 2027."
    f = field(v("eligibility", {"eligibility": F("must hold a Kenya CAA licence valid until 31 December 2027", src)}, src), "eligibility")
    assert f.support == "review_required" and "condition" in f.reason
    f = field(v("eligibility", {"eligibility": F("where the bidder is based outside Kenya, a Kenya CAA licence valid until 31 December 2026",
                                                 src)}, src), "eligibility")
    assert f.support == "unsupported" and "2026-12-31" in f.reason
    ok = field(v("eligibility", {"eligibility": F("where the bidder is based outside Kenya, a Kenya CAA licence valid until 31 December 2027",
                                                  src)}, src), "eligibility")
    assert ok.support == "supported"


def test_atoms_parse_comparators():
    a = el.atoms("no more than 3 aircraft, 80% or more of staff, more than 10 employees")
    assert [(x.comparator, x.number, x.unit) for x in a] == [("max", 3, "aircraft"), ("min", 80, "percent"), ("min_strict", 10, "staff")]


# ---------------------------------------------------------------- 4. contradictions

def test_contradiction_across_the_document_is_flagged():
    doc = ("Example Air invites GSSA proposals for Kenya. Proposals are due on 30 November 2026.\n\n"
           "Notice of 20 October 2026: this tender has been cancelled.")
    q = "Example Air invites GSSA proposals for Kenya."
    r = validate_claim("gssa_tender", {"status": F("open", q)}, doc, claim_quote=q, reference_date=REF)
    assert r.contradiction and "has been cancelled" in r.contradiction
    assert field(r, "status").support == "review_required" and "contradictory" in field(r, "status").reason


@pytest.mark.parametrize("doc", [
    "Example Air invites GSSA proposals for Kenya. The earlier 2022 tender was cancelled.",
    "Example Air invites GSSA proposals for Kenya. The tender has not been cancelled despite press reports.",
    "Example Air invites GSSA proposals for Kenya. The previous framework agreement has expired.",
])
def test_references_to_other_processes_are_not_contradictions(doc):
    assert meaning.status_contradiction(doc, reference_year=2026) is None


# ---------------------------------------------------------------- independent review of the amendments (regressions)

def test_the_current_tender_is_not_another_process():
    q = "The current tender for GSSA services in Kenya has been cancelled."
    assert field(v("tender_status", {"status": F("cancelled", q)}, q), "status").support == "supported"
    doc = "Example Air invites proposals for GSSA services in Kenya. The current tender has been cancelled."
    assert meaning.status_contradiction(doc, reference_year=2026) is not None


@pytest.mark.parametrize("doc,expected", [
    ("Example Air invites proposals for GSSA in Kenya. CANCELLED. Contract awarded to Swissport.", True),
    ("Example Air invites proposals for GSSA in Kenya. Update: this tender is awarded.", True),
    ("Example Air invites proposals for GSSA in Kenya. Submissions will be closed on 30 November 2026.", False),
    ("Example Air invites proposals for GSSA in Kenya and has appointed a consultant to run the process.", False),
])
def test_terminal_wording(doc, expected):
    assert (meaning.status_contradiction(doc, reference_year=2026) is not None) is expected


@pytest.mark.parametrize("text", [
    "Kenya Airways, which has no plans to exit the Ugandan market, invites proposals from GSSA providers for Uganda.",
    "Kenya Airways invites proposals from GSSA providers that are not already representing a competitor in Uganda.",
])
def test_negations_inside_relative_clauses_do_not_negate_the_tender(text):
    assert v("gssa_tender", {}, text).type_supported is True


@pytest.mark.parametrize("value,src,expected", [
    ("cargo handling experience", "Bidders must have at least 5 years of cargo handling experience.", "review_required"),
    ("USD 2 million turnover", "Minimum annual turnover of USD 2 million.", "review_required"),
    ("certificate valid on 31 December 2026", "A certificate valid until 31 December 2026 is required.", "review_required"),
    ("IATA accreditation", "IATA accreditation and FIATA membership are both required.", "review_required"),
    ("a minimum annual turnover of USD 2 million", "Minimum annual turnover of USD 2 million.", "supported"),
])
def test_dropped_minimums_dates_and_joint_requirements_need_review(value, src, expected):
    assert field(v("eligibility", {"eligibility": F(value, src)}, src), "eligibility").support == expected


def test_section_split_accounts_for_prompt_escaping():
    text = ("</document>" * 3000) + ("cargo notice " * 2000)
    parts = sec.split(text, ai.SECTION_BYTES)
    for p in parts:      # never DocumentTooLong, however many closing tags the page contains
        ag.build_prompt(p.text, max_chars=len(p.text), max_bytes=ai.MAX_INPUT_TOKENS - ai.MESSAGE_OVERHEAD_TOKENS)


# ---------------------------------------------------------------- 3b. relationship-level eligibility (validation version 2)
# The three demonstrated failures: same words, numbers and units, different meaning. None may be "supported".

SWAP_CASES = [
    ("Applicants based in Kenya must hold a licence if operating in France.",
     "Applicants based in France must hold a licence if operating in Kenya.", "country roles differ"),
    ("Applicants must have three years of insurance and five years of GSSA experience.",
     "Applicants must have five years of insurance and three years of GSSA experience.", "swaps"),
    ("Applicants must hold a licence valid before 1 January 2027.",
     "Applicants must hold a licence valid by 1 January 2027.", "inclusive vs exclusive"),
]


@pytest.mark.parametrize("src,wrong,why", SWAP_CASES)
def test_same_words_different_relationships_are_never_supported(src, wrong, why):
    f = field(v("eligibility", {"eligibility": F(wrong, src)}, src), "eligibility")
    assert f.support in ("unsupported", "review_required"), (wrong, f.support, f.reason)
    assert why in f.reason, f.reason


def test_the_three_failures_have_the_expected_verdicts():
    verdicts = [field(v("eligibility", {"eligibility": F(w, s)}, s), "eligibility").support for s, w, _ in SWAP_CASES]
    # swapped roles and swapped quantities contradict the source; a one-day boundary difference needs a person
    assert verdicts == ["unsupported", "unsupported", "review_required"], verdicts


@pytest.mark.parametrize("src,right", [
    ("Applicants based in Kenya must hold a licence if operating in France.", "Applicants based in Kenya must hold a licence if operating in France."),
    ("Applicants based in Kenya must hold a licence if operating in France.", "based in Kenya, a licence if operating in France"),
    ("Applicants must have three years of insurance and five years of GSSA experience.", "three years of insurance and five years of GSSA experience"),
    ("Applicants must have three years of insurance and five years of GSSA experience.", "5 years of GSSA experience and 3 years of insurance"),
    ("Applicants must hold a licence valid before 1 January 2027.", "a licence valid before 1 January 2027"),
    ("Applicants must hold a licence valid by 1 January 2027.", "a licence valid no later than 1 January 2027"),
])
def test_accurate_readings_of_the_same_sentences_still_pass(src, right):
    f = field(v("eligibility", {"eligibility": F(right, src)}, src), "eligibility")
    assert f.support == "supported", (right, f.reason)


def test_quantity_bound_to_the_wrong_requirement_is_not_supported():
    src = "Bidders must have USD 2 million of insurance cover and USD 5 million of annual turnover."
    bad = field(v("eligibility", {"eligibility": F("USD 5 million of insurance cover and USD 2 million of annual turnover", src)}, src), "eligibility")
    assert bad.support == "unsupported" and "swaps" in bad.reason
    part = field(v("eligibility", {"eligibility": F("USD 5 million of insurance cover", src)}, src), "eligibility")
    assert part.support != "supported"


def test_country_roles_based_operating_issued_are_kept_apart():
    src = "Bidders registered in Uganda with a licence issued by Kenya may operate in Tanzania."
    assert field(v("eligibility", {"eligibility": F("a licence issued by Uganda", src)}, src), "eligibility").support == "unsupported"
    assert field(v("eligibility", {"eligibility": F("bidders registered in Tanzania", src)}, src), "eligibility").support == "unsupported"
    assert field(v("eligibility", {"eligibility": F("a licence issued by Rwanda", src)}, src), "eligibility").support == "unsupported"
    assert field(v("eligibility", {"eligibility": F("bidders registered in Uganda with a licence issued by Kenya", src)}, src),
                 "eligibility").support == "supported"


def test_condition_scope_cannot_move_to_another_subject():
    src = "Applicants must hold a Kenya CAA licence if they are based outside Kenya."
    moved = field(v("eligibility", {"eligibility": F("Applicants based outside Kenya must hold a licence if it is a Kenya CAA licence", src)}, src),
                  "eligibility")
    assert moved.support != "supported"
    added = field(v("eligibility", {"eligibility": F("a Kenya CAA licence if operating in Kenya", "Applicants must hold a Kenya CAA licence.")},
                    "Applicants must hold a Kenya CAA licence."), "eligibility")
    assert added.support != "supported"
    narrowed = field(v("eligibility", {"eligibility": F("a Kenya CAA licence if based in Kenya", "Applicants must hold a Kenya CAA licence.")},
                       "Applicants must hold a Kenya CAA licence."), "eligibility")
    assert narrowed.support != "supported"
    assert el.compare("a Kenya CAA licence if based in Kenya", "Applicants must hold a Kenya CAA licence.") == \
        ("review_required", "the value adds a condition ('if ...') the source does not state")


@pytest.mark.parametrize("src,val,expected", [
    ("Certificates must be valid after 30 June 2027.", "certificates valid from 30 June 2027", "review_required"),     # exclusive vs inclusive
    ("Certificates must be valid after 30 June 2027.", "certificates valid after 30 June 2027", "supported"),
    ("Certificates must be valid on or before 30 June 2027.", "certificates valid by 30 June 2027", "supported"),      # both inclusive
    ("Certificates must be valid on or before 30 June 2027.", "certificates valid after 30 June 2027", "unsupported"),  # direction
])
def test_date_boundaries_inclusive_and_exclusive(src, val, expected):
    f = field(v("eligibility", {"eligibility": F(val, src)}, src), "eligibility")
    assert f.support == expected, (val, f.reason)


def test_dates_bound_to_their_own_requirement():
    src = "The insurance certificate must be valid until 31 March 2027 and the operating licence until 30 September 2027."
    f = field(v("eligibility", {"eligibility": F("operating licence valid until 31 March 2027", src)}, src), "eligibility")
    assert f.support != "supported", f.reason
    ok = field(v("eligibility", {"eligibility": F("insurance certificate valid until 31 March 2027 and operating licence valid until 30 September 2027",
                                                  src)}, src), "eligibility")
    assert ok.support == "supported", ok.reason


def test_validation_version_names_the_relationship_rules():
    assert el.VALIDATION_VERSION >= 2
    assert el.country_roles("Applicants based in Kenya must hold a licence if operating in France.") == {"KE": {"based_in"}, "FR": {"operating_in"}}


def test_qualifiers_stay_with_their_nouns():
    src = "Eligible bidders must hold IATA cargo agent accreditation and a Kenyan trading licence."
    swapped = field(v("eligibility", {"eligibility": F("a Kenyan cargo agent accreditation and an IATA trading licence", src)}, src), "eligibility")
    assert swapped.support != "supported" and "groups these words differently" in swapped.reason
    for ok in ("IATA cargo agent accreditation and a Kenyan trading licence", "IATA cargo agent accreditation; Kenyan trading licence",
               "accreditation as an IATA cargo agent and a Kenyan trading licence"):
        assert field(v("eligibility", {"eligibility": F(ok, src)}, src), "eligibility").support == "supported", ok
