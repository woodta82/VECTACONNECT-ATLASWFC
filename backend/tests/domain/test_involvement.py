"""A person's evidenced involvement (4.9.0): a third-party press contact is never a commercial contact merely because an announcement names
them; useful external contacts keep their actual role."""
from app.domain import involvement as inv

NEM = ["Nemunas Cargo Services UAB"]


def c(quote, role, org, aff="unknown"):
    return inv.classify(quote, role, org, aff, NEM)[0]


def test_third_party_press_contact_is_not_a_commercial_contact():
    q = "Press contact: Maria Lopez, Example PR Agency, maria.lopez@examplepr.example, +370 5 000 000."
    assert c(q, None, "Example PR Agency", "other_organisation") == "press_contact"
    assert c(q, None, None) == "press_contact"                                     # organisation not even established
    assert c("For media enquiries contact Laura Kim, Account Director, Bright Comms Ltd.", "Account Director", "Bright Comms Ltd") == "press_contact"


def test_the_companys_own_communications_officer_is_a_press_contact_but_its_cargo_head_is_not():
    assert c("Media contact: Anna Weiss, Communications Manager, Nemunas Cargo Services UAB.", "Communications Manager",
             "Nemunas Cargo Services UAB", "employee") == "press_contact"
    q = "For more information, contact Tomas Petrauskas, Head of Cargo Sales at Nemunas Cargo Services UAB."
    assert c(q, "Head of Cargo Sales", "Nemunas Cargo Services UAB", "employee") == "employee"


def test_employee_representative_adviser_unresolved():
    assert c("Ruta Kazlauskiene is Managing Director of Nemunas Cargo Services UAB.", "Managing Director", "Nemunas Cargo Services UAB", "employee") == "employee"
    assert c("Amber Example Air has appointed Baltic GSA SIA as its cargo GSSA; Peter Ozols, Managing Director of Baltic GSA SIA, said …",
             "Managing Director", "Baltic GSA SIA", "partner") == "appointed_representative"
    assert c("The transaction was advised by Ozols Legal; partner Ilze Berzina, legal adviser to the buyer, said …", "Partner", "Ozols Legal",
             "other_organisation") == "external_adviser"
    assert c("John Brown attended the conference.", None, None) == "unresolved"


def test_labels_and_commercial_split():
    assert set(inv.LABELS) == set(inv.INVOLVEMENTS)
    assert "press_contact" in inv.EXTERNAL and "press_contact" not in inv.COMMERCIAL and "appointed_representative" in inv.COMMERCIAL
