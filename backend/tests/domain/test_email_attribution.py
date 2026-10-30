"""Person-to-e-mail attribution (30 Oct 2026, amendment item 1): an address belongs to a person only when the page ties it to that
individual. Multiple people, multiple addresses, shared mailboxes, tables, neighbouring contact blocks, third-party press contacts."""
from app.domain import email_attribution as ea

ORG = ["Nemunas Cargo Services UAB"]
DOM = ["nemunascargo.example"]


def owner(text, names, email):
    hits = [a for a in ea.attribute(text, names, org_domains=DOM, org_names=ORG) if a.email == email]
    assert hits, email
    return hits[0]


def test_jane_smith_john_brown_the_first_email_in_the_sentence_is_not_janes():
    text = ("Jane Smith is Head of Cargo at Nemunas Cargo Services UAB. For sales enquiries please contact John Brown, Sales Manager, at "
            "john.brown@nemunascargo.example or call +370 37 000 000.")
    a = owner(text, ["Jane Smith", "John Brown"], "john.brown@nemunascargo.example")
    assert a.person == "John Brown" and a.confidence == "clear"
    jane, pending = ea.for_person(ea.attribute(text, ["Jane Smith", "John Brown"], org_domains=DOM), "Jane Smith")
    assert jane is None and pending == []
    # the same page when John Brown is NOT yet a known person: still never Jane's — the local part is another person's name
    a2 = owner(text, ["Jane Smith"], "john.brown@nemunascargo.example")
    assert a2.person is None and a2.kind in ("other_person", "unassigned") and "Jane" not in (a2.person or "")
    # one sentence, two people, the address between them: the nearer name before the address with nothing in between
    one = "Jane Smith (jane.smith@nemunascargo.example) and John Brown (john.brown@nemunascargo.example) lead the cargo team."
    att = ea.attribute(one, ["Jane Smith", "John Brown"], org_domains=DOM)
    assert {(x.email, x.person) for x in att} == {("jane.smith@nemunascargo.example", "Jane Smith"), ("john.brown@nemunascargo.example", "John Brown")}


def test_explicit_statement_without_a_name_like_local_part():
    text = "Ruta Kazlauskiene, Managing Director, Nemunas Cargo Services UAB. E-mail: rk@nemunascargo.example."
    a = owner(text, ["Ruta Kazlauskiene"], "rk@nemunascargo.example")
    assert a.person == "Ruta Kazlauskiene" and a.basis in ("explicit_statement", "name_match") and a.confidence == "clear"
    # the opaque address of the NEXT paragraph is not hers: another person stands between
    text2 = "Ruta Kazlauskiene, Managing Director. Tomas Petrauskas, Head of Cargo Sales. E-mail: tp@nemunascargo.example."
    a = owner(text2, ["Ruta Kazlauskiene", "Tomas Petrauskas"], "tp@nemunascargo.example")
    assert a.person == "Tomas Petrauskas"


def test_shared_and_departmental_mailboxes_are_never_a_persons():
    text = ("Jane Smith, Head of Cargo. For bookings write to cargo@nemunascargo.example; general enquiries info@nemunascargo.example. "
            "Sales: sales.kaunas@nemunascargo.example. Jane Smith can also be reached via cargo.sales@nemunascargo.example.")
    att = ea.attribute(text, ["Jane Smith"], org_domains=DOM)
    assert all(a.person is None and a.kind == "shared" for a in att), [(a.email, a.kind) for a in att]
    assert {a.department for a in att} == {"cargo", "info", "sales.kaunas", "cargo.sales"}
    assert ea.for_person(att, "Jane Smith") == (None, [])


def test_two_people_one_address_nothing_singles_one_out_is_pending_review():
    text = "Jane Smith and John Brown handle cargo sales for Lithuania: cargosalesteam@nemunascargo.example or write to kaunas.sales@nemunascargo.example."
    att = ea.attribute(text, ["Jane Smith", "John Brown"], org_domains=DOM)
    # 'cargosalesteam' is a shared mailbox; 'kaunas.sales' too (sales): neither is anyone's
    assert all(a.person is None for a in att)
    text2 = "Jane Smith and John Brown handle cargo sales for Lithuania. E-mail: jb@nemunascargo.example."
    a = owner(text2, ["Jane Smith", "John Brown"], "jb@nemunascargo.example")
    assert a.person is None and a.confidence == "ambiguous" and set(a.candidates) == {"Jane Smith", "John Brown"}
    assert ea.for_person(ea.attribute(text2, ["Jane Smith", "John Brown"]), "Jane Smith")[1][0].email == "jb@nemunascargo.example"


def test_table_rows_bind_each_address_to_the_person_in_its_row():
    text = ("Name | Role | E-mail\n"
            "Jane Smith | Head of Cargo | j.smith@nemunascargo.example\n"
            "John Brown | Sales Manager | sales.manager@nemunascargo.example\n"
            "Anna Weiss | Operations | aw@nemunascargo.example\n")
    att = ea.attribute(text, ["Jane Smith", "John Brown", "Anna Weiss"], org_domains=DOM)
    by = {a.email: a for a in att}
    assert by["j.smith@nemunascargo.example"].person == "Jane Smith"
    assert by["sales.manager@nemunascargo.example"].person is None and by["sales.manager@nemunascargo.example"].kind == "shared"
    assert by["aw@nemunascargo.example"].person == "Anna Weiss" and by["aw@nemunascargo.example"].basis == "table_row"


def test_neighbouring_contact_blocks_do_not_leak_into_each_other():
    text = ("Jane Smith\nHead of Cargo\nTel +370 37 111 111\n\n"
            "John Brown\nSales Manager\nE-mail: jbrown@nemunascargo.example\n\n"
            "Anna Weiss\nOperations Manager\nE-mail: ops@nemunascargo.example\n")
    att = ea.attribute(text, ["Jane Smith", "John Brown", "Anna Weiss"], org_domains=DOM)
    by = {a.email: a for a in att}
    assert by["jbrown@nemunascargo.example"].person == "John Brown" and by["jbrown@nemunascargo.example"].basis in ("contact_block", "name_match")
    assert by["ops@nemunascargo.example"].person is None and by["ops@nemunascargo.example"].kind == "shared"
    assert ea.for_person(att, "Jane Smith") == (None, [])
    # a block whose address line follows another person's address is not the first person's
    text2 = "Jane Smith\nHead of Cargo\nE-mail: x1@nemunascargo.example\nE-mail: x2@nemunascargo.example\n"
    by2 = {a.email: a for a in ea.attribute(text2, ["Jane Smith"], org_domains=DOM)}
    assert by2["x1@nemunascargo.example"].person == "Jane Smith" and by2["x2@nemunascargo.example"].person is None


def test_third_party_press_contacts_belong_to_nobody_at_the_company():
    text = ("Nemunas Cargo Services UAB appoints Jane Smith as Head of Cargo. "
            "Press contact: Maria Lopez, Example PR Agency, maria.lopez@examplepr.example, +370 5 000 000.")
    att = ea.attribute(text, ["Jane Smith"], org_domains=DOM, org_names=ORG)
    a = next(x for x in att if x.email == "maria.lopez@examplepr.example")
    assert a.person is None and a.kind in ("third_party", "other_person", "unassigned")
    assert ea.for_person(att, "Jane Smith") == (None, [])
    # the company's own press officer, named with her role on the company's domain, is a person with an address
    own = "Media enquiries: Anna Weiss, Communications Manager, anna.weiss@nemunascargo.example."
    b = owner(own, ["Anna Weiss"], "anna.weiss@nemunascargo.example")
    assert b.person == "Anna Weiss" and b.confidence == "clear"
    # a known person beside a foreign-domain press address: pending review, never assigned
    mixed = "For further information: Jane Smith, Head of Cargo, via press@examplepr.example or jsmith@examplepr.example."
    c = owner(mixed, ["Jane Smith"], "jsmith@examplepr.example")
    assert c.person is None and c.confidence == "ambiguous" and c.candidates == ["Jane Smith"]


def test_name_match_forms_and_no_match_on_a_different_person():
    assert ea.name_matches("jane.smith@x.example", "Jane Smith")
    assert ea.name_matches("jsmith2@x.example", "Jane Smith")
    assert ea.name_matches("smithj@x.example", "Jane Smith")
    assert ea.name_matches("ruta.kazlauskiene@x.example", "Rūta Kazlauskienė")
    assert ea.name_matches("jan.devries@x.example", "Jan de Vries") or ea.name_matches("jan.vries@x.example", "Jan de Vries")
    assert not ea.name_matches("john.brown@x.example", "Jane Smith")
    assert ea.mailbox_kind("cargo@x.example")[0] == "shared" and ea.mailbox_kind("jane.smith@x.example")[0] == "name_like"
    assert ea.mailbox_kind("jk@x.example")[0] == "opaque" and ea.mailbox_kind("emily.post@x.example")[0] == "name_like"


# ================================================================================ 4.8.0: ownership needs explicit evidence; currency
# The amendment's two examples were not included in the instruction; they are reconstructed from its description and quoted here verbatim.
SUPPLIER_EXAMPLE = ("Jane Smith is Head of Cargo at Nemunas Cargo Services UAB. "
                    "Our booking platform is provided by Example Cargo Systems Ltd; for technical support contact their account manager at "
                    "jane.smith@examplecargosystems.example.")
INVALID_EXAMPLE = ("John Brown, Sales Manager, Nemunas Cargo Services UAB. "
                   "Do not use john.brown@nemunascargo.example — this address is no longer valid. Please write to sales@nemunascargo.example instead.")


def test_external_supplier_example_a_matching_local_part_is_not_ownership():
    att = ea.attribute(SUPPLIER_EXAMPLE, ["Jane Smith"], org_domains=DOM, org_names=ORG)
    a = next(x for x in att if x.email == "jane.smith@examplecargosystems.example")
    assert a.person is None and a.kind == "third_party" and a.confidence == "ambiguous" and "supplier" in a.reason
    assert "the local part matches Jane Smith" in a.supporting[0]
    assert ea.for_person(att, "Jane Smith")[0] is None


def test_a_matching_local_part_alone_is_pending_review_never_assigned():
    text = "Our cargo team can be reached at jane.smith@nemunascargo.example for bookings."
    a = owner(text, ["Jane Smith"], "jane.smith@nemunascargo.example")
    assert a.person is None and a.kind == "name_only" and a.confidence == "ambiguous" and a.candidates == ["Jane Smith"]
    assert "nothing on the page states whose address it is" in a.reason
    # the same address WITH an explicit statement is hers, and the matching name is recorded as supporting evidence
    b = owner("Jane Smith, Head of Cargo: jane.smith@nemunascargo.example.", ["Jane Smith"], "jane.smith@nemunascargo.example")
    assert b.person == "Jane Smith" and b.basis == "explicit_statement" and b.supporting == ["the local part is Jane Smith's own name"]


def test_same_name_people_and_initials():
    # two people whose initials give the same local part: the structure decides, the name never does
    text = "John Smith, Head of Sales. E-mail: jsmith@nemunascargo.example.\n\nJane Smith, Head of Cargo. Tel +370 37 111 111."
    a = owner(text, ["John Smith", "Jane Smith"], "jsmith@nemunascargo.example")
    assert a.person == "John Smith" and a.basis == "explicit_statement"
    # the same initials with no structure: both are candidates, neither is assigned
    b = owner("Write to jsmith@nemunascargo.example.", ["John Smith", "Jane Smith"], "jsmith@nemunascargo.example")
    assert b.person is None and set(b.candidates) == {"John Smith", "Jane Smith"} and "several people share it" in b.reason
    # a namesake at a partner: same name, the partner's domain, no explanation — investigate, never assign
    c = owner("Jane Smith (Baltic Partner Air): jane.smith@balticpartner.example.", ["Jane Smith"], "jane.smith@balticpartner.example")
    assert c.person is None and c.kind == "investigate" and "does not explain the relationship" in c.reason


def test_a_domain_mismatch_prompts_investigation_and_an_explained_relationship_is_accepted():
    sub = "Our Riga subsidiary is run by Anna Weiss, Station Manager, at anna.weiss@nemunas-riga.example."
    a = owner(sub, ["Anna Weiss"], "anna.weiss@nemunas-riga.example")
    assert a.person == "Anna Weiss" and any("subsidiary" in x for x in a.supporting)
    agent = "Cargo sales in Latvia are handled by our appointed agent, Peter Ozols, Baltic GSA SIA: p.ozols@balticgsa.example."
    assert owner(agent, ["Peter Ozols"], "p.ozols@balticgsa.example").person == "Peter Ozols"
    adviser = "Peter Ozols, an independent adviser to the board, can be reached at p.ozols@ozols-consulting.example."
    assert owner(adviser, ["Peter Ozols"], "p.ozols@ozols-consulting.example").person == "Peter Ozols"
    unexplained = "Peter Ozols, Sales Manager: p.ozols@gmail.example."
    x = owner(unexplained, ["Peter Ozols"], "p.ozols@gmail.example")
    assert x.person is None and x.kind == "investigate" and x.candidates == ["Peter Ozols"]
    # without a known organisation domain there is nothing to compare: the structural tie stands
    assert ea.attribute(unexplained, ["Peter Ozols"])[0].person == "Peter Ozols"


def test_partner_and_third_party_contacts():
    partner = ("Nemunas Cargo Services UAB works with its partner company Example Road Feeder SIA. "
               "Contact their dispatcher, Ivars Liepa, at ivars.liepa@roadfeeder.example.")
    a = owner(partner, ["Ivars Liepa"], "ivars.liepa@roadfeeder.example")
    assert a.person is None                                              # the partner's dispatcher, not a person at the company


def test_invalid_example_do_not_use_no_longer_valid():
    att = ea.attribute(INVALID_EXAMPLE, ["John Brown"], org_domains=DOM, org_names=ORG)
    by = {x.email: x for x in att}
    old = by["john.brown@nemunascargo.example"]
    assert old.currency == "historical" and "Do not use" in old.currency_reason
    assert ea.for_person(att, "John Brown") == (None, [])                 # never offered as a current route
    assert [h.email for h in ea.historical_for(att, "John Brown")] == ["john.brown@nemunascargo.example"]
    assert by["sales@nemunascargo.example"].currency == "current" and by["sales@nemunascargo.example"].kind == "shared"


def test_obsolete_replaced_withdrawn_and_former_employee_wording():
    cases = {
        "Tomas Petrauskas, Head of Cargo Sales: tomas.petrauskas@nemunascargo.example (this address is no longer monitored).": "historical",
        "Tomas Petrauskas, Head of Cargo Sales. His old address tomas.p@nemunascargo.example was replaced by tp@nemunascargo.example.": None,
        "Tomas Petrauskas has left the company. Tomas Petrauskas, former Head of Cargo Sales: tp@nemunascargo.example.": "historical",
        "Tomas Petrauskas, Head of Cargo Sales: tp@nemunascargo.example.": "current",
    }
    for text, expected in cases.items():
        att = ea.attribute(text, ["Tomas Petrauskas"], org_domains=DOM)
        if expected:
            assert att[0].currency == expected, (text, att[0])
    replaced = ea.attribute("Tomas Petrauskas, Head of Cargo Sales. His old address tomas.p@nemunascargo.example was replaced by tp@nemunascargo.example.",
                            ["Tomas Petrauskas"], org_domains=DOM)
    by = {x.email: x.currency for x in replaced}
    assert by == {"tomas.p@nemunascargo.example": "historical", "tp@nemunascargo.example": "current"}
