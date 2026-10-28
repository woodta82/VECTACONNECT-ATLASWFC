"""Held-out set 5 (written 27 Oct 2026, third instruction, BEFORE any rule of that instruction was changed; run once at the end
of the release; no rule changed afterwards).

PROVENANCE: authored for this build in the form of real airline and procurement notices. None is a genuine notice.
Gold conventions as in `heldout3.py`, plus:
- `excluded` entries may carry scope 'not_freight' (cargo explicitly excluded, or work outside the freight capability scope),
  'passenger' or 'conflicting';
- `opp(status="announced")`: a title or heading establishes that the procurement notice exists; nothing states that it is
  still accepting applications;
- `signal_expected`: the capability area of the signal a non-procurement notice must produce.

LABEL CLARIFICATION (27 Oct 2026, fourth instruction, item 5): n06's excluded passenger lot is now named by its lot
reference (CEA-PAX-2027-1) instead of the airline name it shares with the cargo lot. The airline-name label let the
harness match the cargo lot's opportunity as a "leak". The expected outcome is unchanged; results under the old matching
are kept in the release evidence.
"""
from __future__ import annotations

from evaluation.notices import Case, claim, f, opp

HELDOUT5: list[Case] = []


def add(c: Case) -> Case:
    HELDOUT5.append(c)
    return c


# n01 the instruction's own failure: cargo explicitly excluded
NA1 = "Example Air invites proposals from general sales agents for representation in Kenya. Cargo sales are excluded from this mandate."
NA2 = "Tender reference EXA-GSA-2027-40. Proposals are due on 12 March 2027."
add(Case("n01-cargo-excluded-ke", "heldout5", "en", "airline_representation", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["freight_relevance", "cargo_excluded"], "html", "RFP EXA-GSA-2027-40", f"{NA1}\n\n{NA2}",
         [claim("gssa_tender", NA1, {"airline": f("Example Air", NA1), "country": f("Kenya", NA1), "service": f("GSSA", NA1), "status": f("open", NA2),
                                      "tender_ref": f("EXA-GSA-2027-40", NA2), "deadline": f("2027-03-12", NA2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "not_freight", "title_contains": "Example Air"}]},
         notes="The mandate excludes cargo: never a freight opportunity."))

# n02 passenger-only with incidental cargo wording about something else
NB1 = "Gulf Example Airways invites proposals for a general sales agent for passenger sales and ticketing in Bahrain. Reference GEA-PAX-2027-6."
NB2 = "The airline's cargo business is handled by its own cargo division and is not affected. Proposals are due on 20 March 2027."
add(Case("n02-passenger-with-incidental-cargo-bh", "heldout5", "en", "airline_representation", {"geo_mode": "country", "countries": ["BH"]}, ["BH"],
         ["freight_relevance", "passenger_only", "incidental_cargo"], "html", "RFP GEA-PAX-2027-6", f"{NB1}\n\n{NB2}",
         [claim("gssa_tender", NB1, {"airline": f("Gulf Example Airways", NB1), "country": f("Bahrain", NB1), "service": f("GSSA", NB1), "status": f("open", NB2),
                                      "tender_ref": f("GEA-PAX-2027-6", NB1), "deadline": f("2027-03-20", NB2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "passenger", "title_contains": "Gulf Example Airways"}]}))

# n03 historical cargo activity outside the current mandate
NC1 = "Example Air, which appointed a cargo GSA in Ghana in 2019, now invites proposals for a passenger sales agent in Ghana. Reference EXA-PAX-2027-7."
NC2 = "Proposals are due on 18 March 2027."
add(Case("n03-historical-cargo-passenger-mandate-gh", "heldout5", "en", "airline_representation", {"geo_mode": "country", "countries": ["GH"]}, ["GH"],
         ["freight_relevance", "historical_cargo"], "html", "RFP EXA-PAX-2027-7", f"{NC1}\n\n{NC2}",
         [claim("gssa_tender", NC1, {"airline": f("Example Air", NC1), "country": f("Ghana", NC1), "service": f("GSSA", NC1), "status": f("open", NC1),
                                      "tender_ref": f("EXA-PAX-2027-7", NC1), "deadline": f("2027-03-18", NC2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "passenger", "title_contains": "Example Air"}]},
         notes="The 2019 cargo appointment is background; the current mandate is passenger sales."))

# n04 conflicting inclusion and exclusion
ND1 = "Sample Airways invites proposals for cargo sales representation in Uganda. Reference SAW-GSA-2027-14."
ND2 = "Cargo sales are not part of this appointment. Proposals are due on 25 March 2027."
add(Case("n04-cargo-conflict-ug", "heldout5", "en", "airline_representation", {"geo_mode": "country", "countries": ["UG"]}, ["UG"],
         ["freight_relevance", "conflicting_statements"], "html", "RFP SAW-GSA-2027-14", f"{ND1}\n\n{ND2}",
         [claim("gssa_tender", ND1, {"airline": f("Sample Airways", ND1), "country": f("Uganda", ND1), "service": f("GSSA", ND1), "status": f("open", ND2),
                                      "tender_ref": f("SAW-GSA-2027-14", ND1), "deadline": f("2027-03-25", ND2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("SAW-GSA-2027-14", day="2027-03-25", precision="date", service="GSSA", freight_scope="conflicting")]},
         notes="One passage includes cargo, another excludes it: a record held for review, never qualified on cargo grounds."))

# n05 genuine positive cargo mandate
NE1 = "Example Air invites proposals for the appointment of a cargo GSSA to sell freighter and bellyhold capacity in Ethiopia. Reference EXA-CGO-2027-15."
NE2 = "Proposals must be submitted by 2 April 2027."
add(Case("n05-cargo-mandate-et", "heldout5", "en", "airline_representation", {"geo_mode": "country", "countries": ["ET"]}, ["ET"],
         ["freight_relevance", "plain"], "html", "RFP EXA-CGO-2027-15", f"{NE1}\n\n{NE2}",
         [claim("gssa_tender", NE1, {"airline": f("Example Air", NE1), "country": f("Ethiopia", NE1), "service": f("GSSA", NE1), "status": f("open", NE2),
                                      "tender_ref": f("EXA-CGO-2027-15", NE1), "deadline": f("2027-04-02", NE2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("EXA-CGO-2027-15", day="2027-04-02", precision="date", service="GSSA", freight_scope="cargo")]}))

# n06 separate passenger and cargo lots in one document
NF_T = "Request for proposals: general sales agents, Tanzania (two lots)"
NF1 = "Lot 1: passenger sales and ticketing agent in Tanzania. Reference CEA-PAX-2027-1. Proposals are due on 9 April 2027."
NF2 = "Lot 2: cargo general sales and service agent in Tanzania. Reference CEA-CGO-2027-2. Proposals are due on 9 April 2027."
NF0 = "Coastal Example Airways invites proposals for two separate lots."
add(Case("n06-passenger-and-cargo-lots-tz", "heldout5", "en", "airline_representation", {"geo_mode": "country", "countries": ["TZ"]}, ["TZ"],
         ["freight_relevance", "multi_lot", "multi_opportunity"], "html", NF_T, f"{NF0}\n\n{NF1}\n\n{NF2}",
         [claim("gssa_tender", NF1, {"airline": f("Coastal Example Airways", NF0), "country": f("Tanzania", NF1), "service": f("GSSA", NF1), "status": f("open", NF1),
                                      "tender_ref": f("CEA-PAX-2027-1", NF1), "deadline": f("2027-04-09", NF1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("gssa_tender", NF2, {"airline": f("Coastal Example Airways", NF0), "country": f("Tanzania", NF2), "service": f("GSSA", NF2), "status": f("open", NF2),
                                      "tender_ref": f("CEA-CGO-2027-2", NF2), "deadline": f("2027-04-09", NF2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("CEA-CGO-2027-2", day="2027-04-09", precision="date", service="GSSA", freight_scope="cargo")],
          "excluded": [{"scope": "passenger", "ref": "CEA-PAX-2027-1"}]},
         notes="Lot 1 is passenger (excluded), lot 2 cargo (an opportunity); the lots must not share one scope reading."))

# n07 the instruction's keyword failure: ramp lighting
NG1 = "Example Air invites tenders for ramp lighting maintenance at Mombasa airport, Kenya. Tender reference EXA-ENG-2027-3. Bids are due on 30 March 2027."
add(Case("n07-ramp-lighting-ke", "heldout5", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["freight_relevance", "incidental_keyword", "not_freight"], "html", "Tender EXA-ENG-2027-3", NG1,
         [claim("service_tender", NG1, {"airline": f("Example Air", NG1), "country": f("Kenya", NG1), "service": f("HANDLING", NG1), "status": f("open", NG1),
                                         "tender_ref": f("EXA-ENG-2027-3", NG1), "deadline": f("2027-03-30", NG1)},
                {"airline": True, "country": True, "service": False, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "not_freight", "title_contains": "Example Air"}]},
         notes="Lighting maintenance on a ramp is not freight work within the capability scope."))

# n08 passenger boarding bridge "loading" wording
NH1 = "Sample Airways invites quotations for passenger loading bridge maintenance at Entebbe, Uganda. Reference SAW-ENG-2027-8. Quotations are due on 4 April 2027."
add(Case("n08-loading-bridge-ug", "heldout5", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["UG"]}, ["UG"],
         ["freight_relevance", "incidental_keyword", "not_freight"], "html", "RFQ SAW-ENG-2027-8", NH1,
         [claim("service_tender", NH1, {"airline": f("Sample Airways", NH1), "country": f("Uganda", NH1), "service": f("HANDLING", NH1), "status": f("open", NH1),
                                         "tender_ref": f("SAW-ENG-2027-8", NH1), "deadline": f("2027-04-04", NH1)},
                {"airline": True, "country": True, "service": False, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "passenger", "title_contains": "Sample Airways"}]}))

# n09 tonnes and an abbreviation in a non-freight notice
NI1 = "Example Air invites proposals for aircraft catering supply at Kigali airport, Rwanda, of about 300 tonnes of meals per year. Reference EXA-CAT-2027-2. Proposals are due on 15 April 2027."
add(Case("n09-catering-tonnes-rw", "heldout5", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["RW"]}, ["RW"],
         ["freight_relevance", "incidental_keyword", "not_freight"], "html", "RFP EXA-CAT-2027-2", NI1,
         [claim("service_tender", NI1, {"airline": f("Example Air", NI1), "country": f("Rwanda", NI1), "service": f("HANDLING", NI1), "status": f("open", NI1),
                                         "tender_ref": f("EXA-CAT-2027-2", NI1), "deadline": f("2027-04-15", NI1)},
                {"airline": True, "country": True, "service": False, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "not_freight", "title_contains": "Example Air"}]}))

# n10 title-only RFP, recent: announced, current status unverified
NJ_T = "Request for proposal for the appointment of a cargo GSSA in Malawi"
NJ1 = "Request for proposal for the appointment of a cargo GSSA in Malawi. Example Air. Reference EXA-CGO-2027-17."
add(Case("n10-title-only-rfp-mw", "heldout5", "en", "airline_representation", {"geo_mode": "country", "countries": ["MW"]}, ["MW"],
         ["status_announced", "missing_deadline"], "pdf", NJ_T, NJ1,
         [claim("gssa_tender", NJ1, {"airline": f("Example Air", NJ1), "country": f("Malawi", NJ1), "service": f("GSSA", NJ1), "status": f("open", NJ1),
                                      "tender_ref": f("EXA-CGO-2027-17", NJ1)},
                {"airline": True, "country": True, "service": True, "status": False, "tender_ref": True})],
         {"opportunities": [opp("EXA-CGO-2027-17", status="announced", day=None, precision=None, service="GSSA", freight_scope="cargo")]},
         published="2026-10-21T08:00:00Z", notes="The title establishes the notice; nothing says it is still accepting proposals."))

# n11 title-only RFP but the body states a future closing date: open, verified by the deadline
NK1 = "Request for proposal for the appointment of a cargo GSSA in Zimbabwe. Sample Airways. Reference SAW-CGO-2027-18."
NK2 = "Proposals must be submitted by 28 April 2027."
add(Case("n11-rfp-with-closing-date-zw", "heldout5", "en", "airline_representation", {"geo_mode": "country", "countries": ["ZW"]}, ["ZW"],
         ["status_announced"], "pdf", "RFP SAW-CGO-2027-18", f"{NK1}\n\n{NK2}",
         [claim("gssa_tender", NK1, {"airline": f("Sample Airways", NK1), "country": f("Zimbabwe", NK1), "service": f("GSSA", NK1), "status": f("open", NK2),
                                      "tender_ref": f("SAW-CGO-2027-18", NK1), "deadline": f("2027-04-28", NK2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("SAW-CGO-2027-18", day="2027-04-28", precision="date", service="GSSA", freight_scope="cargo")]}))

# n12 multi-stop rotation
NL1 = "Example Cargo will launch a weekly freighter rotation Nairobi-Entebbe-Kigali-Nairobi from 5 January 2027, offering 90 tonnes per week."
add(Case("n12-multistop-rotation", "heldout5", "en", "capacity_lanes", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["KE", "UG", "RW"],
         ["capacity", "route", "multi_stop"], "html", "Example Cargo rotation", NL1,
         [claim("route_launch", NL1, {"airline": f("Example Cargo", NL1), "origin": f("Uganda", NL1), "destination": f("Rwanda", NL1)},
                {"airline": True, "origin": False, "destination": False}),
          claim("route_launch", NL1, {"airline": f("Example Cargo", NL1), "origin": f("Kenya", NL1), "destination": f("Kenya", NL1)},
                {"airline": True, "origin": False, "destination": False})],
         {"opportunities": [], "signal_expected": "capacity_lanes"},
         notes="A multi-stop rotation is not a single origin-destination pair; the stops are kept, the pair is not a fact."))

# n13 daily road feeder service launch
NM1 = "Example Cargo has introduced a daily road feeder service between Riyadh and Dammam, Saudi Arabia, from 1 December 2026."
add(Case("n13-daily-rfs-launch-sa", "heldout5", "en", "trucking_gateways", {"geo_mode": "country", "countries": ["SA"]}, ["SA"],
         ["route", "trucking_launch"], "html", "Example Cargo RFS", NM1,
         [claim("route_launch", NM1, {"airline": f("Example Cargo", NM1), "origin": f("Saudi Arabia", NM1), "destination": f("Saudi Arabia", NM1)},
                {"airline": True, "origin": True, "destination": True})],
         {"opportunities": [], "signal_expected": "trucking_gateways"}))

# n14 road-feeder provider appointment
NN1 = "Sample Airways has appointed Desert Road Logistics as its road feeder service provider for cargo between Muscat and Sohar in Oman."
add(Case("n14-rfs-provider-appointment-om", "heldout5", "en", "trucking_gateways", {"geo_mode": "country", "countries": ["OM"]}, ["OM"],
         ["award", "trucking_appointment"], "html", "Sample Airways RFS appointment", NN1,
         [claim("representation_change", NN1, {"airline": f("Sample Airways", NN1), "organisation": f("Desert Road Logistics", NN1), "country": f("Oman", NN1)},
                {"airline": True, "organisation": True, "country": True})],
         {"opportunities": [], "signal_expected": "trucking_gateways"}))

# n15 lower-case schedule wording
NO_T = "RFP SAW-GSSA-2027-19: cargo GSSA"
NO1 = "Sample Airways invites proposals from cargo GSSA providers. Tender reference SAW-GSSA-2027-19. Proposals are due on 6 April 2027."
NO2 = "schedule b: kenya and uganda."
add(Case("n15-lowercase-schedule", "heldout5", "en", "airline_representation", {"geo_mode": "countries", "countries": ["KE", "UG"]}, ["KE", "UG"],
         ["multi_lot", "geography_roles"], "html", NO_T, f"{NO1}\n\n{NO2}",
         [claim("gssa_tender", NO1, {"airline": f("Sample Airways", NO1), "service": f("GSSA", NO1), "status": f("open", NO1),
                                      "tender_ref": f("SAW-GSSA-2027-19", NO1), "deadline": f("2027-04-06", NO1)},
                {"airline": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("tender_scope", NO2, {"tender_ref": f("SAW-GSSA-2027-19", NO1), "contract_territory": f("Kenya", NO2)}, {"tender_ref": True, "contract_territory": True}),
          claim("tender_scope", NO2, {"tender_ref": f("SAW-GSSA-2027-19", NO1), "contract_territory": f("Tanzania", NO2)}, {"tender_ref": True, "contract_territory": False})],
         {"opportunities": [opp("SAW-GSSA-2027-19", day="2027-04-06", precision="date", service="GSSA", freight_scope="cargo")]}))

# n16 non-freight concession
NP1 = "Kigali International Airport invites bids for a duty-free retail concession in the departures hall. Reference KIA-RET-2027-1. Bids are due on 30 April 2027."
add(Case("n16-retail-concession-rw", "heldout5", "en", "service_operations", {"geo_mode": "country", "countries": ["RW"]}, ["RW"],
         ["not_freight", "concession"], "html", "Tender KIA-RET-2027-1", NP1,
         [claim("service_tender", NP1, {"organisation": f("Kigali International Airport", NP1), "country": f("Rwanda", NP1), "status": f("open", NP1),
                                         "tender_ref": f("KIA-RET-2027-1", NP1), "deadline": f("2027-04-30", NP1)},
                {"organisation": True, "country": False, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "not_freight", "title_contains": "Kigali"}]},
         notes="Rwanda is named only inside the airport's name; a retail concession is outside the freight scope."))

# n17 Spanish exclusion
NQ1 = "Aerolínea Ejemplo convoca a agentes generales de ventas para su representación en Perú. Se excluye la carga de este mandato. Referencia AEJ-GSA-2027-2."
NQ2 = "Plazo de presentación de ofertas: 10 de abril de 2027."
add(Case("n17-es-cargo-excluded-pe", "heldout5", "es", "airline_representation", {"geo_mode": "country", "countries": ["PE"]}, ["PE"],
         ["language_es", "cargo_excluded"], "html", "Convocatoria AEJ-GSA-2027-2", f"{NQ1}\n\n{NQ2}",
         [claim("gssa_tender", NQ1, {"airline": f("Aerolínea Ejemplo", NQ1), "country": f("Peru", NQ1), "service": f("GSSA", NQ1), "status": f("open", NQ2),
                                      "tender_ref": f("AEJ-GSA-2027-2", NQ1), "deadline": f("2027-04-10", NQ2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "not_freight", "title_contains": "Aerolínea Ejemplo"}]}, extra={"lang": "es"}))

# n18 negative control: a cargo handling tender whose "ramp" wording is genuine freight work
NR1 = "Example Air invites tenders for cargo ramp handling and ULD build-up at Accra, Ghana. Tender reference EXA-HDL-2027-21. Bids are due on 22 April 2027."
add(Case("n18-cargo-ramp-handling-gh", "heldout5", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["GH"]}, ["GH"],
         ["freight_relevance", "plain"], "html", "Tender EXA-HDL-2027-21", NR1,
         [claim("service_tender", NR1, {"airline": f("Example Air", NR1), "country": f("Ghana", NR1), "service": f("HANDLING", NR1), "status": f("open", NR1),
                                         "tender_ref": f("EXA-HDL-2027-21", NR1), "deadline": f("2027-04-22", NR1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("EXA-HDL-2027-21", day="2027-04-22", precision="date", service="HANDLING", freight_scope="cargo")]}))


def heldout5_cases() -> list[Case]:
    return list(HELDOUT5)
