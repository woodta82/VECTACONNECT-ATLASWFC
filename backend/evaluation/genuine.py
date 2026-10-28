"""Genuine evaluation set (27 Oct 2026, item 5): real public notices with manually checked expected results.

PROVENANCE: every case here is a GENUINE notice (real issuer, reference, dates, criteria and wording) captured on
27 Oct 2026 through the session's web-fetch tool, which returns verbatim quotes and paraphrased structure, not the
original bytes (`genuine_sources/README.md`, one file per notice). The documents below are rebuilt from the captured
text in the original's form (HTML, HTML table or PDF); every quoted sentence is kept exactly as captured. Expected
results were checked by a person against the captured text. The extractor is scripted: no AI provider key was
available. These cases were written once and run once; no rule was changed in response to their results.

Split name: `genuine`. The harness reports them separately from the authored sets.

LABEL CORRECTIONS (27 Oct 2026, second instruction, item 4) — the expected answers were reviewed again against the freight
brief and the captured source text, independently of what the application did; the previous results (labels v1) are kept in
`evidence/evaluation/report-genuine-labels-v1.md` for comparison. What changed and why:
- g01, g02, g12 (Air India Qatar, Air India West Africa, SpiceJet): PASSENGER GSA appointments. The brief is freight: a passenger-
  only mandate is not a freight opportunity. Gold `opportunities` -> [] and gold `excluded` (the record must be kept as excluded
  evidence with the reason). The stated facts (territory, open status, deadline, criteria) keep their field labels.
- g01: the disclaimer's Saudi Arabia conflicts with the defined territory (Qatar): gold `geography_conflict` True. g02: four
  territories in one title are a multi-country mandate, not a conflict: gold `geography_conflict` False.
- g12 (SpiceJet 2022): "Applicants shall submit a separate application for each territory" is a procedure, not an open status;
  the v1 label marked 'open' as correct — wrong. Both 'open' proposals are now False. The notice is four years old with no
  closing date and no status wording: a reviewer cannot call it open.
- g03 (KAA): "The Procuring Entity is Kenya Airports Authority" names Kenya only inside the authority's name; the v1 label called
  it a supported delivery country — wrong. False now, and a second proposal quoting the lot line (Nanyuki, Isiolo) is True.
- g11 (TED Menorca-Madrid): a passenger public-service-obligation route: gold `excluded`; the deadline "10/03/2026" has no
  day/month convention anywhere in the notice, so it must wait for review (False, previously True).
- g13 (Aena): the quoted sentence names neither Aena nor Spain (the v1 labels said it did): organisation and country False.
- Freight scope asserted on every remaining opportunity (cargo / mixed / unclear) so the pipeline's relevance reading is scored.

LABELS v3 (27 Oct 2026, third instruction, item 3: "An RFP title establishes that a procurement notice exists. It does not
independently establish that applications are still being accepted"):
- g07: the listing heading "publishes its tenders below. Each row is a separate request for proposal." names the notices; it
  does not state that any is still accepting proposals. The three 'open' proposals quoting it are now labelled not stated.
- g11: "El objeto de la presente licitación es ..." names the procurement; it does not state that offers are still accepted.
  Its 'open' proposal is now labelled not stated.
Previous results (labels v2) are kept for comparison.

LABELS v4 (27 Oct 2026, fifth instruction, item 4): one policy for terminal-only records. A cancellation, award or closure
of a tender that is not already tracked is kept as HISTORICAL INTELLIGENCE (a tender record with the terminal status,
outside the actionable pipeline and the live counts), never created as an opportunity. Labels that expected a terminal
opportunity (t04, t15, h04, j04 in notices.py; m10 in heldout4.py) or nothing at all (g09 in genuine.py, k12 in heldout3.py) now expect a
`historical` record instead. Previous results are kept in the release evidence.
"""
from __future__ import annotations

from evaluation.notices import Case, claim, f, opp

GENUINE: list[Case] = []


def add(c: Case) -> Case:
    c.extra = dict(c.extra or {}, genuine=True)
    GENUINE.append(c)
    return c


# ------------------------------------------------------------ g01 Air India / Air India Express, passenger GSA, Qatar (PDF)
G1T = 'REQUEST FOR PROPOSAL FOR APPOINTMENT OF "GENERAL SALES AGENT" ("GSA") FOR PASSENGER SALES OF AIR INDIA LIMITED AND AIR INDIA EXPRESS LIMITED IN QATAR'
G1A = "Date of Issue: 15-10-2026"
G1B = '"Territory" shall mean the geographical limits of the country i.e., Qatar.'
G1C = "Disclaimer: this request for proposal is issued for passenger sales in Kingdom of Saudi Arabia."
G1D = "appointment of GSA for sale of air passenger transportation of the Airlines within the Territory"
G1E = "Last date for submission of proposal 06-11-2026"
G1F = "Last date for submission of queries (if any) by Applicants on the RFP 24-10-2026"
G1G = "The Applicant should have at least 5(five) years of experience in travel business in the Territory."
G1H = "Applicant should provide a Bank Guarantee of USD 1,500,000 /- (US Dollar One Million Five Hundred Thousand only) to Air India Express and USD 425,000. /- (US Dollars Four Lakh Fifty Thousand Only) to Air India."
G1I = "The Applicant should have Turnover of at least USD 14,209,806 in the last financial year immediately preceding the date of this RFP."
G1J = "Airlines reserve the right to withdraw the RFP (in whole or in part) at any time."
add(Case("g01-air-india-qatar-gsa", "genuine", "en", "airline_representation", {"geo_mode": "country", "countries": ["QA"]}, ["QA"],
         ["genuine", "pdf", "conflicting_statements", "eligibility_numeric", "missing_timezone", "passenger_not_cargo"], "pdf", G1T,
         f"{G1T}\n\n{G1A}\n\nAIR INDIA LIMITED AND AIR INDIA EXPRESS LIMITED\n\n{G1B}\n\n{G1C}\n\n{G1D}\n\n{G1E}\n\n{G1F}\n\n{G1G}\n\n{G1H}\n\n{G1I}\n\n{G1J}",
         [claim("gssa_tender", G1T, {"airline": f("Air India", G1T), "country": f("Qatar", G1B), "service": f("GSSA", G1T), "status": f("open", G1E),
                                      "deadline": f("2026-11-06", G1E)}, {"airline": True, "country": True, "service": True, "status": True, "deadline": True}),
          claim("gssa_tender", G1T, {"airline": f("Air India", G1T), "country": f("Saudi Arabia", G1C), "service": f("GSSA", G1T), "status": f("open", G1E)},
                {"airline": True, "country": False, "service": True, "status": True}),
          claim("eligibility", G1G, {"airline": f("Air India", G1T), "eligibility": f("at least 5 years of experience in travel business in the Territory", G1G)},
                {"eligibility": True}),
          claim("eligibility", G1G, {"airline": f("Air India", G1T), "eligibility": f("at least 3 years of experience in travel business in the Territory", G1G)},
                {"eligibility": False}),
          claim("eligibility", G1H, {"airline": f("Air India", G1T), "eligibility": f("a Bank Guarantee of USD 1,500,000 to Air India Express and USD 425,000 to Air India", G1H)},
                {"eligibility": True}),
          claim("eligibility", G1H, {"airline": f("Air India", G1T), "eligibility": f("a Bank Guarantee of USD 425,000 to Air India Express and USD 1,500,000 to Air India", G1H)},
                {"eligibility": False}),
          claim("eligibility", G1I, {"airline": f("Air India", G1T), "eligibility": f("Turnover of at least USD 14,209,806 in the last financial year", G1I)}, {"eligibility": True}),
          claim("tender_deadline", G1F, {"airline": f("Air India", G1T), "deadline": f("2026-10-24", G1F)}, {"deadline": False})],
         {"opportunities": [], "excluded": [{"scope": "passenger", "title_contains": "Air India"}], "geography_conflict": True}, published="2026-10-15T08:00:00Z",
         notes="Genuine. PASSENGER GSA: never a freight opportunity (excluded evidence). The disclaimer names Saudi Arabia while the defined territory "
               "is Qatar: a geography conflict to flag; Saudi Arabia must not be supported. The bank-guarantee figures and words disagree in the original "
               "(425,000 vs four lakh fifty thousand). The query deadline is not the submission deadline."))

# ------------------------------------------------------------ g02 Air India, passenger GSA, four West African territories (PDF)
G2T = 'APPOINTMENT OF "GENERAL SALES AGENT" ("GSA") FOR PASSENGER SALES OF AIR INDIA LIMITED IN BENIN, COTE D\'IVOIRE, TOGO AND SENEGAL'
G2A = "Date of Issue: 21-05-2026"
G2B = "Last date for submission of queries 31-05-2026. Last date for submission of proposal 12-06-2026."
G2C = "The Applicant should have at least 5(five) years of experience in travel business in the Territory."
G2D = "The Applicant should have Turnover of at least USD 400,000/ in the last financial year."
G2E = "The Applicant should provide a separate Bank Guarantee up to USD 100,000/- to Air India."
G2F = "The Applicant should not be an IATA Accredited agent."
G2G = "The Applicant should be familiar/have experience with IATA BSP procedures or equivalent in the Territory."
add(Case("g02-air-india-west-africa-gsa", "genuine", "en", "airline_representation", {"geo_mode": "countries", "countries": ["BJ", "CI", "TG", "SN"]}, ["BJ", "CI", "TG", "SN"],
         ["genuine", "pdf", "multi_country", "eligibility_numeric", "negated_requirement", "passenger_not_cargo"], "pdf", G2T,
         f"{G2T}\n\n{G2A}\n\n{G2B}\n\n{G2C}\n\n{G2D}\n\n{G2E}\n\n{G2F}\n\n{G2G}",
         [claim("gssa_tender", G2T, {"airline": f("Air India", G2T), "country": f("Senegal", G2T), "service": f("GSSA", G2T), "status": f("open", G2B),
                                      "deadline": f("2026-06-12", G2B)}, {"airline": True, "country": True, "service": True, "status": True, "deadline": True}),
          claim("tender_deadline", G2B, {"airline": f("Air India", G2T), "deadline": f("2026-05-31", G2B)}, {"deadline": False}),
          claim("eligibility", G2D, {"airline": f("Air India", G2T), "eligibility": f("Turnover of at least USD 400,000 in the last financial year", G2D)}, {"eligibility": True}),
          claim("eligibility", G2D, {"airline": f("Air India", G2T), "eligibility": f("Turnover of at least USD 4,000,000 in the last financial year", G2D)}, {"eligibility": False}),
          claim("eligibility", G2F, {"airline": f("Air India", G2T), "eligibility": f("an IATA Accredited agent", G2F)}, {"eligibility": False}),
          claim("eligibility", G2E, {"airline": f("Air India", G2T), "eligibility": f("a separate Bank Guarantee up to USD 100,000 to Air India", G2E)}, {"eligibility": True})],
         {"opportunities": [], "excluded": [{"scope": "passenger", "title_contains": "Air India"}], "geography_conflict": False}, published="2026-05-21T08:00:00Z",
         notes="Genuine. PASSENGER GSA: excluded evidence, never a freight opportunity. Four territories in one RFP are a multi-country mandate, not a "
               "conflict. 'should not be an IATA Accredited agent' is a negative requirement: reading it as a positive one must not be supported."))

# ------------------------------------------------------------ g03 Kenya Airports Authority, ground handling, two lots (PDF)
G3T = "PROVISION OF GROUND HANDLING SERVICES AT LOT 1: NANYUKI AIRSTRIP AND LOT 2: ISIOLO INTERNATIONAL AIRPORT"
G3A = "The Procuring Entity is Kenya Airports Authority. The reference number is: KAA/OT/MBD/0018/2025-2026"
G3B = "Lot 1- Nanyuki Airstrip, Lot 2 –Isiolo International Airport."
G3C = "Completed Tender documents and its attachments shall be submitted online before the closing date 19th February, 2026 at 11.00 am"
G3D = "Tender Security of Kenya shillings one hundred thousand (Kshs. 100,000.00) only"
G3E = "A valid and current KRA tax compliance certificate. In case of Joint venture both must provide."
G3F = "Copy of valid and current IATA accreditation certificate."
G3G = "The Procuring Entity reserves the right to accept or reject any Tender, and to annul the Tendering process and reject all Tenders at any time prior to Contract Award."
add(Case("g03-kaa-ground-handling", "genuine", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["genuine", "pdf", "multi_lot", "missing_timezone", "eligibility_numeric"], "pdf", G3T,
         f"{G3T}\n\n{G3A}\n\n{G3B}\n\n{G3C}\n\n{G3D}\n\n{G3E}\n\n{G3F}\n\n{G3G}",
         [claim("service_tender", G3A, {"organisation": f("Kenya Airports Authority", G3A), "country": f("Kenya", G3A), "service": f("HANDLING", G3T),
                                         "status": f("open", G3C), "tender_ref": f("KAA/OT/MBD/0018/2025-2026", G3A), "deadline": f("2026-02-19T11:00:00", G3C)},
                {"organisation": True, "country": False, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("tender_scope", G3B, {"organisation": f("Kenya Airports Authority", G3A), "tender_ref": f("KAA/OT/MBD/0018/2025-2026", G3A),
                                      "contract_territory": f("Kenya", G3B)}, {"tender_ref": True, "contract_territory": True}),
          claim("eligibility", G3D, {"organisation": f("Kenya Airports Authority", G3A), "tender_ref": f("KAA/OT/MBD/0018/2025-2026", G3A),
                                     "eligibility": f("Tender Security of Kenya shillings one hundred thousand (Kshs. 100,000.00)", G3D)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", G3D, {"organisation": f("Kenya Airports Authority", G3A), "tender_ref": f("KAA/OT/MBD/0018/2025-2026", G3A),
                                     "eligibility": f("Tender Security of Kshs. 1,000,000.00", G3D)}, {"tender_ref": True, "eligibility": False}),
          claim("eligibility", G3E, {"organisation": f("Kenya Airports Authority", G3A), "tender_ref": f("KAA/OT/MBD/0018/2025-2026", G3A),
                                     "eligibility": f("a valid and current KRA tax compliance certificate", G3E)}, {"tender_ref": True, "eligibility": True}),
          claim("tender_status", G3G, {"organisation": f("Kenya Airports Authority", G3A), "tender_ref": f("KAA/OT/MBD/0018/2025-2026", G3A), "status": f("cancelled", G3G)},
                {"tender_ref": True, "status": False})],
         {"opportunities": [opp("KAA/OT/MBD/0018/2025-2026", status="expired", day="2026-02-19", precision="local_time", service="HANDLING", freight_scope="unclear")]},
         published="2026-01-20T08:00:00Z",
         notes="Genuine. One reference, two lots; 11.00 am with no zone is a local time; the closing date has passed (expired). 'reserves the right to "
               "annul' is not a cancellation. 'Kenya Airports Authority' names Kenya only as part of the authority; the lot line (Nanyuki, Isiolo) does. "
               "Ground handling with no cargo wording: freight relevance unclear, pending review."))

# ------------------------------------------------------------ g04 UN Secretariat EOI, ground handling, Haiti and Dominican Republic (HTML)
G4T = "Provision of Airport Ground Handling Services in support of UNSOH"
G4A = "Reference: EOIUNPD24179. Published: 13-Feb-2026. Deadline: 02-Mar-2026, 23:59 (GMT -4.00). Beneficiary countries: Dominican Republic and Haiti."
G4B = "The United Nations Support Office in Haiti (UNSOH) plans to contract qualified providers for as-needed airport ground handling at major airports in Haiti and the Dominican Republic."
G4C = "This EOI does not constitute a solicitation."
G4D = "At least five years of airport ground handling or aviation services experience for international or humanitarian operations."
G4E = "Vendors must be registered in UNGM at the Basic level or higher to be considered."
add(Case("g04-un-eoi-ground-handling", "genuine", "en", "outsourcing_training", {"geo_mode": "countries", "countries": ["DO", "HT"]}, ["DO", "HT"],
         ["genuine", "expression_of_interest", "timezone_offset", "eligibility_numeric"], "html", G4T,
         f"{G4T}\n\n{G4A}\n\n{G4B}\n\n{G4C}\n\n{G4D}\n\n{G4E}",
         [claim("service_tender", G4B, {"organisation": f("United Nations Support Office in Haiti", G4B), "country": f("Haiti", G4B), "service": f("HANDLING", G4B),
                                         "status": f("open", G4A), "tender_ref": f("EOIUNPD24179", G4A), "deadline": f("2026-03-02T23:59:00", G4A)},
                {"organisation": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", G4D, {"organisation": f("United Nations Support Office in Haiti", G4B), "tender_ref": f("EOIUNPD24179", G4A),
                                     "eligibility": f("at least five years of airport ground handling or aviation services experience", G4D)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", G4D, {"organisation": f("United Nations Support Office in Haiti", G4B), "tender_ref": f("EOIUNPD24179", G4A),
                                     "eligibility": f("at least fifteen years of airport ground handling experience", G4D)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("EOIUNPD24179", status="expired", day="2026-03-02", precision="instant", service="HANDLING", freight_scope="unclear")]}, published="2026-02-13T08:00:00Z",
         notes="Genuine. An EOI with an explicit offset (GMT -4.00): an exact instant; passed (expired). 'does not constitute a solicitation' is a status "
               "nuance the system does not model (limitation)."))

# ------------------------------------------------------------ g05 My Freighter GSA pre-qualification (trade association news, HTML)
G5A = "NAP airline partner My Freighter Airlines is seeking qualified General Sales Agents to represent the carrier in South Korea, Hong Kong, Bangladesh, Singapore, Ghana, Ethiopia, Kenya and Uganda."
G5B = "The pre-qualification process requires applicants to submit their company profile, market coverage, GSA experience, key-account network, local market assessment and a proposed commercial and customer-service strategy."
G5C = "The opportunity is for qualified NAP and NAV AERO members with an established presence in the listed markets: established cargo sales and logistics companies with strong local market knowledge."
add(Case("g05-my-freighter-gsa-news", "genuine", "en", "airline_representation", {"geo_mode": "region", "countries": [], "regions": ["EASTERN_AFRICA"]}, ["KE", "ET", "UG", "GH"],
         ["genuine", "trade_press", "multi_country", "missing_deadline", "uninterpretable_eligibility"], "html", "My Freighter Opens GSA Tender Across Asia and Africa",
         f"{G5A}\n\n{G5B}\n\n{G5C}",
         [claim("gssa_tender", G5A, {"airline": f("My Freighter Airlines", G5A), "country": f("Kenya", G5A), "service": f("GSSA", G5A), "status": f("open", G5A)},
                {"airline": True, "country": True, "service": True, "status": True}),
          claim("eligibility", G5C, {"airline": f("My Freighter Airlines", G5A), "eligibility": f("NAP and NAV AERO members with an established presence in the listed markets", G5C)},
                {"eligibility": True}),
          claim("tender_deadline", G5B, {"airline": f("My Freighter Airlines", G5A), "deadline": f("2026-09-30", G5B)}, {"deadline": False})],
         {"opportunities": [opp(None, day=None, precision=None, service="GSSA", title_contains="My Freighter", freight_scope="cargo")]}, published="2026-09-09T08:00:00Z",
         notes="Genuine trade-association item: a GSA pre-qualification across eight markets, no deadline stated; the eligibility is membership-based wording."))

# ------------------------------------------------------------ g06 FlyUs appointed by Air Canada Cargo (trade press, HTML): not a tender
G6A = "GSSA FlyUs is opening a new office in Puerto Rico's San Juan following the start of a new contract with Air Canada Cargo."
G6B = "FlyUs will provide agency services for the Canadian airline's three-times-per-week freighter service between San Juan and Toronto Pearson."
G6C = "The appointment builds on a longstanding relationship between FlyUs and Air Canada."
add(Case("g06-flyus-air-canada-appointment", "genuine", "en", "airline_representation", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["PR", "CA"],
         ["genuine", "trade_press", "award", "not_procurement"], "html", "FlyUs expands in Puerto Rico following Air Canada win", f"{G6A}\n\n{G6B}\n\n{G6C}",
         [claim("representation_change", G6A, {"airline": f("Air Canada", G6A), "organisation": f("FlyUs", G6A), "country": f("Puerto Rico", G6A)},
                {"airline": True, "organisation": True, "country": True}),
          claim("gssa_tender", G6A, {"airline": f("Air Canada", G6A), "country": f("Puerto Rico", G6A), "service": f("GSSA", G6A), "status": f("open", G6A)},
                {"airline": True, "country": True, "service": True, "status": False})],
         {"opportunities": [], "signal_expected": "airline_representation"}, published="2026-10-12T08:00:00Z",
         notes="Genuine. An appointment already made: a representation change, never an open tender."))

# ------------------------------------------------------------ g07 Mumbai airport tender listing (HTML table)
G7H = "Chhatrapati Shivaji Maharaj International Airport, Mumbai, publishes its tenders below. Each row is a separate request for proposal."
R1 = "Ground handling services concession bidding | Not listed | Commercial | 22/01/2026 | 28/02/2026 05:00 PM"
R2 = "Cargo community system for EDI services (AMAX IT) | Not listed | Commercial | 29/05/2025 | 05/06/2025 05:00 PM"
R3 = "Non-aeronautical services concession | Not listed | Commercial | 28/08/2026 | 05/09/2026 05:00 PM"
add(Case("g07-mumbai-airport-tender-table", "genuine", "en", "technology_solutions", {"geo_mode": "country", "countries": ["IN"]}, ["IN"],
         ["genuine", "table", "multi_opportunity", "missing_timezone", "missing_reference"], "html-table", "Tenders - Mumbai Airport (BOM)", G7H,
         [claim("service_tender", R1, {"organisation": f("Chhatrapati Shivaji Maharaj International Airport", G7H), "country": f("India", G7H), "service": f("HANDLING", R1),
                                        "status": f("open", G7H), "deadline": f("2026-02-28T17:00:00", R1)},
                {"organisation": True, "country": True, "service": True, "status": False, "deadline": True}),
          claim("service_tender", R2, {"organisation": f("Chhatrapati Shivaji Maharaj International Airport", G7H), "country": f("India", G7H), "service": f("TECHNOLOGY", R2),
                                        "status": f("open", G7H), "deadline": f("2025-06-05T17:00:00", R2)},
                {"organisation": True, "country": True, "service": True, "status": False, "deadline": True}),
          claim("service_tender", R3, {"organisation": f("Chhatrapati Shivaji Maharaj International Airport", G7H), "country": f("India", G7H), "service": f("HANDLING", R3),
                                        "status": f("open", G7H), "deadline": f("2026-09-05T17:00:00", R3)},
                {"organisation": True, "country": True, "service": False, "status": False, "deadline": True})],
         {"opportunities": [opp(None, status="expired", day="2026-02-28", precision="local_time", service="HANDLING", title_contains="Chhatrapati", freight_scope="unclear"),
                            opp(None, status="expired", day="2025-06-05", precision="local_time", service="TECHNOLOGY", title_contains="Chhatrapati", freight_scope="cargo")]},
         table_rows=[["Title", "Reference", "Category", "Published", "Due"],
                     ["Ground handling services concession bidding", "Not listed", "Commercial", "22/01/2026", "28/02/2026 05:00 PM"],
                     ["Cargo community system for EDI services (AMAX IT)", "Not listed", "Commercial", "29/05/2025", "05/06/2025 05:00 PM"],
                     ["Non-aeronautical services concession", "Not listed", "Commercial", "28/08/2026", "05/09/2026 05:00 PM"]],
         published="2026-10-01T08:00:00Z",
         notes="Genuine listing (titles condensed by the capture). No references: separate rows must still be separate records; the non-aeronautical "
               "concession is not a freight service. 05:00 PM with no zone is a local time."))

# ------------------------------------------------------------ g08 Aéroports de Paris, assistance en escale (French, HTML)
G8T = "Procédure de sélection des prestataires d'assistance en escale autorisés à rendre les services faisant l'objet d'une limitation"
G8A = "Nom officiel: AEROPORTS DE PARIS. Lieu : 93 - TREMBLAY EN FRANCE, aéroport de Paris-Charles de Gaulle."
G8B = "Les services concernés sur l'aéroport de Paris-Charles de Gaulle sont ceux relevant des catégories suivantes : assistance bagages, chargement et déchargement de l'avion, déplacement de l'avion."
G8C = "Référence : AO-2543-1860. Mise en ligne : 16/10/2025."
G8D = "Date limite de réception des demandes de participation: 13/02/2026 12:00:00 (UTC+1)"
G8E = "Durée: 84 Mois. Sources des critères de sélection: Document de marché."
add(Case("g08-adp-cdg-assistance-escale", "genuine", "fr", "outsourcing_training", {"geo_mode": "region", "countries": [], "regions": ["EU"]}, ["FR"],
         ["genuine", "language_fr", "timezone_offset", "missing_criteria"], "html", G8T, f"{G8T}\n\n{G8A}\n\n{G8B}\n\n{G8C}\n\n{G8D}\n\n{G8E}",
         [claim("service_tender", G8T, {"organisation": f("Aéroports de Paris", G8A), "country": f("France", G8A), "service": f("HANDLING", G8B),
                                         "status": f("open", G8D), "tender_ref": f("AO-2543-1860", G8C), "deadline": f("2026-02-13T12:00:00", G8D)},
                {"organisation": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", G8E, {"organisation": f("Aéroports de Paris", G8A), "tender_ref": f("AO-2543-1860", G8C),
                                     "eligibility": f("une durée de 84 mois", G8E)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("AO-2543-1860", status="expired", day="2026-02-13", precision="instant", service="HANDLING", freight_scope="mixed")]}, published="2025-10-16T08:00:00Z",
         notes="Genuine. French notice; UTC+1 stated; the criteria are only referenced to the tender documents (missing criteria); the duration is not an "
               "eligibility criterion. 'Tremblay en France' names France only inside a place name: the delivery country is established by 'Paris-Charles de Gaulle' "
               "through the city register (Paris)."))

# ------------------------------------------------------------ g09 SGSIA Alger: avis d'annulation (French, HTML)
G9A = "Assistance en escale à l'aéroport d'Alger Houari Boumediene. Référence 58/DCO/SGSIA/2023. Appel d'offres initial publié le 31/08/2023."
G9B = "La SGSIA (Société de Gestion des Services et Infrastructures Aéroportuaires) déclare l'annulation de l'appel d'offre national et international ouvert."
add(Case("g09-sgsia-alger-annulation", "genuine", "fr", "outsourcing_training", {"geo_mode": "country", "countries": ["DZ"]}, ["DZ"],
         ["genuine", "language_fr", "cancellation"], "html", "AVIS D'ANNULATION — Assistance en escale à l'aéroport", f"{G9A}\n\n{G9B}",
         [claim("tender_status", G9B, {"organisation": f("SGSIA", G9B), "tender_ref": f("58/DCO/SGSIA/2023", G9A), "status": f("cancelled", G9B)},
                {"tender_ref": True, "status": True}),
          claim("service_tender", G9A, {"organisation": f("SGSIA", G9B), "country": f("Algeria", G9A), "service": f("HANDLING", G9A), "status": f("open", G9A),
                                         "tender_ref": f("58/DCO/SGSIA/2023", G9A)}, {"organisation": True, "country": True, "service": True, "status": False, "tender_ref": True})],
         {"opportunities": [], "historical": [{"ref": "58/DCO/SGSIA/2023", "status": "cancelled"}]}, published="2024-10-06T08:00:00Z",
         notes="Genuine cancellation notice. If a record is created it must be 'cancelled', never 'open'. Algeria is named only through Alger (city register)."))

# ------------------------------------------------------------ g10 EGSA Oran, selection of a ground-handling operator (French title, portal fields in English)
G10A = "Sélection d'un opérateur pour l'exercice des services d'assistance en escale. EGSA Etablissement de Gestion de Services Aéroportuaires d'Oran."
G10B = "Publication date: 22/05/2023. Due date: 20/06/2023. Reference 2331100263. Type: National call for tenders. Withdrawal of documents at l'aéroport internationnal d'oran ahmed ben bella."
add(Case("g10-egsa-oran-assistance-escale", "genuine", "fr", "outsourcing_training", {"geo_mode": "country", "countries": ["DZ"]}, ["DZ"],
         ["genuine", "language_fr", "expired", "missing_criteria"], "html", "Sélection d'un opérateur pour l'exercice des services d'assistance en escale",
         f"{G10A}\n\n{G10B}",
         [claim("service_tender", G10A, {"organisation": f("EGSA Oran", G10A), "country": f("Algeria", G10B), "service": f("HANDLING", G10A), "status": f("open", G10B),
                                          "tender_ref": f("2331100263", G10B), "deadline": f("2023-06-20", G10B)},
                {"organisation": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("2331100263", status="expired", day="2023-06-20", precision="date", service="HANDLING", freight_scope="unclear")]}, published="2023-05-22T08:00:00Z",
         notes="Genuine, expired. The country is never named: Oran resolves through the city register. No criteria are listed."))

# ------------------------------------------------------------ g11 TED: public-service-obligation air services Menorca–Madrid (Spanish, HTML)
G11T = "Servicios de transporte aéreo sometidos a obligaciones de servicio público en la ruta Menorca-Madrid."
G11A = "Dirección General de Aviación Civil. Lugar de ejecución: Madrid (ES300), País: España. Identificador 367A2025, anuncio 120109-2026."
G11B = "El objeto de la presente licitación es la prestación de servicios de transporte aéreo regular en la ruta Menorca-Madrid."
G11C = "Plazo de recepción de ofertas: 10/03/2026 14:30:00 (UTC+01:00) Hora de Europa Central."
G11D = "Criterios de selección: Volumen de negocios anual general; Referencias sobre servicios específicos."
add(Case("g11-ted-menorca-madrid-pso", "genuine", "es", "service_operations", {"geo_mode": "country", "countries": ["ES"]}, ["ES"],
         ["genuine", "language_es", "not_freight", "timezone_offset"], "html", G11T, f"{G11T}\n\n{G11A}\n\n{G11B}\n\n{G11C}\n\n{G11D}",
         [claim("service_tender", G11B, {"organisation": f("Dirección General de Aviación Civil", G11A), "country": f("Spain", G11A), "service": f("HANDLING", G11B),
                                          "status": f("open", G11B), "tender_ref": f("120109-2026", G11A), "deadline": f("2026-03-10T14:30:00", G11C)},
                {"organisation": True, "country": True, "service": False, "status": False, "tender_ref": True, "deadline": False})],
         {"opportunities": [], "excluded": [{"scope": "passenger"}]}, published="2026-02-20T08:00:00Z",
         notes="Genuine, Spanish. A passenger public-service-obligation route: no freight service; excluded evidence, never an opportunity. "
               "'10/03/2026' has no day/month convention anywhere in the notice: the deadline waits for review (not a fact)."))

# ------------------------------------------------------------ g12 SpiceJet passenger GSA RFP (PDF, 2022, no territory, no deadline)
G12T = "REQUEST FOR PROPOSAL (RFP) FOR APPOINTMENT OF ONLINE/ OFFLINE PASSENGER GENERAL SALES AGENTS"
G12A = "SpiceJet Limited. Request for Proposal for Appointment of Offline GSAs dated September 15, 2022."
G12B = "Applicants shall submit a separate application for each territory they apply for. Provide the trade registration number if registration is a legal requirement in the territory/ country."
G12C = "SpiceJet reserves the right to withdraw the RFP (in whole or in part) at any time."
add(Case("g12-spicejet-gsa-rfp-2022", "genuine", "en", "airline_representation", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["IN"],
         ["genuine", "pdf", "missing_deadline", "missing_geography", "stale", "passenger_not_cargo"], "pdf", G12T, f"{G12T}\n\n{G12A}\n\n{G12B}\n\n{G12C}",
         [claim("gssa_tender", G12T, {"airline": f("SpiceJet", G12A), "service": f("GSSA", G12T), "status": f("open", G12B)},
                {"airline": True, "service": True, "status": False}),
          claim("gssa_tender", G12T, {"airline": f("SpiceJet", G12A), "country": f("India", G12A), "service": f("GSSA", G12T), "status": f("open", G12B)},
                {"airline": True, "country": False, "service": True, "status": False})],
         {"opportunities": [], "excluded": [{"scope": "passenger", "title_contains": "SpiceJet"}]}, published="2022-09-15T08:00:00Z",
         notes="Genuine, four years old, no territory, no deadline, PASSENGER GSAs. 'shall submit a separate application' is a procedure, not an open "
               "status (both 'open' proposals are wrong). Excluded evidence, never a freight opportunity."))

# ------------------------------------------------------------ g13 Aena: handling licences assigned (Spanish press release): award, not a tender
G13A = "Finaliza el proceso de asignación de las licencias para el servicio de asistencia en tierra a las compañías aéreas. 26 de septiembre de 2023."
G13B = "Se han renovado 41 licencias para 43 aeropuertos por un período de 7 años. Las empresas asignadas para prestar los servicios de asistencia en tierra a terceros son Aviapartner, Groundforce, Iberia, Menzies, Swissport y Unión Handling."
G13C = "La segunda licencia será licitada en un nuevo proceso de selección independiente."
add(Case("g13-aena-handling-licences-awarded", "genuine", "es", "outsourcing_training", {"geo_mode": "country", "countries": ["ES"]}, ["ES"],
         ["genuine", "language_es", "award", "planned"], "html", "Finaliza el proceso de asignación de las licencias de handling", f"{G13A}\n\n{G13B}\n\n{G13C}",
         [claim("tender_status", G13B, {"organisation": f("Aena", G13A), "status": f("awarded", G13B)}, {"status": True}),
          claim("service_tender", G13C, {"organisation": f("Aena", G13A), "country": f("Spain", G13A), "service": f("HANDLING", G13A), "status": f("open", G13C)},
                {"organisation": False, "country": False, "service": True, "status": False})],
         {"opportunities": []}, published="2023-09-26T08:00:00Z",
         notes="Genuine, Spanish. Licences already awarded; a future tender is announced ('será licitada'), which is planned, not open."))


# ============================================================ added 27 Oct 2026 (second instruction, item 7): the five capability areas that had no
# genuine example. Captured AFTER the rules of that instruction were tuned and run once; no rule was changed in response.
# ------------------------------------------------------------ g14 Etihad Cargo appoints road feeder service providers, USA (trade press, 2022): an award
G14T = "Etihad Cargo appoints road feeder service providers in the USA"
G14A = "Etihad Cargo has appointed Accelerated, Inc. and Jet Airways of the US, Inc. as its road feeder service (RFS) providers for customers in US territories."
G14B = "The partnerships connect offline points with the carrier's main gateways, including international airports in Chicago, New York and Washington."
add(Case("g14-etihad-rfs-appointment-us", "genuine", "en", "trucking_gateways", {"geo_mode": "country", "countries": ["US"]}, ["US"],
         ["genuine", "trade_press", "award", "stale"], "html", G14T, f"{G14A}\n\n{G14B}",
         [claim("representation_change", G14A, {"airline": f("Etihad Cargo", G14A), "organisation": f("Accelerated, Inc.", G14A), "country": f("United States", G14A)},
                {"airline": True, "organisation": True, "country": False}),
          claim("service_tender", G14A, {"airline": f("Etihad Cargo", G14A), "country": f("United States", G14A), "service": f("TRUCKING", G14A), "status": f("open", G14A)},
                {"airline": True, "country": False, "service": True, "status": False})],
         {"opportunities": [], "signal_expected": "trucking_gateways"}, published="2022-04-18T08:00:00Z",
         notes="Genuine (2022). Providers already appointed: no open tender. 'US territories' does not name the United States as written."))

# ------------------------------------------------------------ g15 Oman Air Cargo daily Muscat-Dubai road feeder service (trade press): a trucking gateway signal
G15T = "Oman Air Cargo launches daily Muscat-Dubai road feeder service to strengthen regional cargo links"
G15A = "Oman Air Cargo has introduced a daily Road Feeder Service (RFS) between Muscat, Oman, and Dubai, UAE."
G15B = "The service accommodates perishables and general cargo, including freight that may not fit on narrowbody aircraft."
add(Case("g15-oman-air-rfs-muscat-dubai", "genuine", "en", "trucking_gateways", {"geo_mode": "countries", "countries": ["OM", "AE"]}, ["OM", "AE"],
         ["genuine", "trade_press", "capacity", "route"], "html", G15T, f"{G15A}\n\n{G15B}",
         [claim("route_launch", G15A, {"airline": f("Oman Air Cargo", G15A), "origin": f("Oman", G15A), "destination": f("United Arab Emirates", G15A)},
                {"airline": True, "origin": True, "destination": True}),
          claim("service_tender", G15A, {"airline": f("Oman Air Cargo", G15A), "country": f("Oman", G15A), "service": f("TRUCKING", G15A), "status": f("open", G15A)},
                {"airline": True, "country": True, "service": True, "status": False})],
         {"opportunities": [], "signal_expected": "trucking_gateways"}, published="2026-06-18T08:00:00Z",
         notes="Genuine. A trucking service launched by the airline: a gateway signal, not a tender."))

# ------------------------------------------------------------ g16 Qatar Airways Cargo winter freighter network (trade press): capacity and lanes
G16T = "Qatar Airways Cargo expands winter freighter network"
G16A = "The carrier will launch a weekly Boeing 777 freighter service from Copenhagen on 25 October, routed Doha-Budapest-Copenhagen-Doha, with 100 tonnes of export capacity per week."
G16B = "Two weekly Boeing 777 freighters operate Doha-Liège-Dallas-Doha, providing 200 tonnes of main-deck capacity into Dallas and 100 tonnes outbound per week."
add(Case("g16-qatar-cargo-winter-freighters", "genuine", "en", "capacity_lanes", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["QA", "DK", "US"],
         ["genuine", "trade_press", "capacity", "worldwide"], "html", G16T, f"{G16A}\n\n{G16B}",
         [claim("route_launch", G16A, {"airline": f("Qatar Airways Cargo", G16T), "origin": f("Denmark", G16A), "destination": f("Qatar", G16A)},
                {"airline": True, "origin": False, "destination": False}),
          claim("capacity_statement", G16B, {"airline": f("Qatar Airways Cargo", G16T), "destination": f("United States", G16B)},
                {"airline": True, "destination": False}),
          claim("gssa_tender", G16A, {"airline": f("Qatar Airways Cargo", G16T), "country": f("Denmark", G16A), "status": f("open", G16A)},
                {"airline": True, "country": False, "status": False})],
         {"opportunities": [], "signal_expected": "capacity_lanes"}, published="2026-10-22T08:00:00Z",
         notes="Genuine. New freighter capacity: a lane signal, never a tender. The cities are named, the countries are not; the route ends are "
               "multi-stop rotations, so country-level origin/destination readings are not established as written."))

# ------------------------------------------------------------ g17 My Freighter / China Southern interline agreement: network development
G17T = "My Freighter signs interline agreement with China Southern Airlines"
G17A = "My Freighter has signed an interline agreement with China Southern Airlines (CZ)."
G17B = "Under the interline framework, seamless cargo transfers between flights operated by both airlines are enabled, expanding and strengthening air cargo connectivity between Central Asia and China."
add(Case("g17-my-freighter-china-southern-interline", "genuine", "en", "network_development", {"geo_mode": "region", "countries": [], "regions": ["CENTRAL_ASIA"]}, ["UZ", "CN"],
         ["genuine", "partnership", "company_release"], "html", G17T, f"{G17A}\n\n{G17B}",
         [claim("partnership", G17A, {"airline": f("My Freighter", G17A), "organisation": f("China Southern Airlines", G17A)}, {"airline": True, "organisation": True}),
          claim("partnership", G17B, {"airline": f("My Freighter", G17A), "country": f("China", G17B)}, {"airline": True, "country": False})],
         {"opportunities": [], "signal_expected": "network_development"}, published="2026-02-11T08:00:00Z",
         notes="Genuine. An interline partnership: a network signal, not an opportunity; 'connectivity between Central Asia and China' is not a delivery country."))

# ------------------------------------------------------------ g18 Future Forwarding opens Farnborough branch: forwarder sales intelligence, not procurement
G18T = "Future Forwarding Expands UK Presence with New Farnborough Branch"
G18A = "Future Forwarding announces the opening of a new office in Farnborough, strengthening its UK network."
G18B = "The office will enhance freight forwarding services across Air, Courier, Road, Rail, Sea and E-Commerce."
add(Case("g18-future-forwarding-farnborough", "genuine", "en", "forwarder_sales", {"geo_mode": "country", "countries": ["GB"]}, ["GB"],
         ["genuine", "company_release", "not_procurement", "internal_area"], "html", G18T, f"{G18A}\n\n{G18B}",
         [claim("service_tender", G18A, {"organisation": f("Future Forwarding", G18A), "country": f("United Kingdom", G18T), "service": f("HANDLING", G18B), "status": f("open", G18A)},
                {"organisation": True, "country": True, "service": False, "status": False})],
         {"opportunities": []}, published="2026-01-14T08:00:00Z",
         notes="Genuine. A forwarder's branch opening: sales intelligence for forwarder accounts, never a procurement; no tender type is stated."))

# ------------------------------------------------------------ g19 Jayud block space agreement Zhengzhou-Chicago: account growth / capacity
G19T = "Jayud secures annual air cargo capacity on Zhengzhou-Chicago route, expanding cross-border logistics capabilities"
G19A = "Jayud Global Logistics Limited secured capacity under a Block Space Agreement between Zhengzhou Xinzheng International Airport (CGO) and Chicago O'Hare International Airport (ORD)."
G19B = "Under the one-year agreement, effective January 17, 2026, B747-400F freighter flights operate three times weekly with guaranteed weekly cargo capacity of approximately 16,800 kilograms."
add(Case("g19-jayud-bsa-cgo-ord", "genuine", "en", "account_growth", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["CN", "US"],
         ["genuine", "trade_press", "capacity", "partnership"], "html", G19T, f"{G19A}\n\n{G19B}",
         [claim("capacity_statement", G19B, {"organisation": f("Jayud Global Logistics Limited", G19A)}, {"organisation": True}),
          claim("partnership", G19A, {"organisation": f("Jayud Global Logistics Limited", G19A)}, {"organisation": True}),
          claim("tender_deadline", G19B, {"organisation": f("Jayud Global Logistics Limited", G19A), "deadline": f("2026-01-17", G19B)}, {"deadline": False})],
         {"opportunities": []}, published="2026-01-14T08:00:00Z",
         notes="Genuine. A forwarder's block space agreement with an unnamed carrier: account and capacity intelligence; the effective date is not a deadline. "
               "LABEL CORRECTED after the first run: the organisation field's own quote (G19A) names Jayud verbatim, so the label is True; the "
               "first label wrongly judged it against the claim quote (G19B). The first run is kept in the evidence."))


def genuine_cases() -> list[Case]:
    return list(GENUINE)
