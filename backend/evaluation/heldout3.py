"""Held-out set 3 (written 27 Oct 2026 BEFORE the freight-relevance, geography-conflict, status/age and interpretation
rules of that instruction were tuned; run once at the end of the release; no rule changed afterwards).

PROVENANCE: authored for this build in the form of real airline and procurement notices. None is a genuine notice.

New expectation fields (the harness reads them; they are scoring, not tuning):
- `opp(..., freight_scope=...)`: the record's freight scope ('cargo', 'mixed', 'unclear'); a passenger-only notice is never
  an opportunity: it is listed under gold `excluded` ({"scope": "passenger", "title_contains": ...}) and must appear as an
  excluded signal with its reason, not as an opportunity.
- `opp(status=...)` may be 'historical' (no supported status wording, published longer ago than the review threshold) or
  'unverified' (open wording, no closing date, published longer ago than the threshold).
- gold `geography_conflict`: True when the document's territory definition/title and another passage disagree, so the
  conflict must be flagged and the conflicting country must not be a supported delivery country.

LABELS v4 (27 Oct 2026, fifth instruction, item 4): one policy for terminal-only records. A cancellation, award or closure
of a tender that is not already tracked is kept as HISTORICAL INTELLIGENCE (a tender record with the terminal status,
outside the actionable pipeline and the live counts), never created as an opportunity. Labels that expected a terminal
opportunity (t04, t15, h04, j04 in notices.py; m10 in heldout4.py) or nothing at all (g09 in genuine.py, k12 in heldout3.py) now expect a
`historical` record instead. Previous results are kept in the release evidence.
"""
from __future__ import annotations

from evaluation.notices import Case, claim, f, opp

HELDOUT3: list[Case] = []


def add(c: Case) -> Case:
    HELDOUT3.append(c)
    return c


# k01 passenger-only GSA RFP: facts are stated (country, status, deadline) but the record is EXCLUDED from the freight pipeline
KA1 = "Gulf Example Airways invites proposals for the appointment of a General Sales Agent (GSA) for passenger sales and ticketing in Oman."
KA2 = "Tender reference GEA-PAX-2027-01. Proposals must be submitted by 20 January 2027 at 16:00 GST."
add(Case("k01-passenger-only-gsa-om", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["OM"]}, ["OM"],
         ["passenger_only", "freight_relevance"], "html", "RFP: passenger GSA, Oman", f"{KA1}\n\n{KA2}",
         [claim("gssa_tender", KA1, {"airline": f("Gulf Example Airways", KA1), "country": f("Oman", KA1), "service": f("GSSA", KA1), "status": f("open", KA2),
                                      "tender_ref": f("GEA-PAX-2027-01", KA2), "deadline": f("2027-01-20T16:00:00", KA2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Asia/Muscat")],
         {"opportunities": [], "excluded": [{"scope": "passenger", "title_contains": "Gulf Example Airways"}]},
         notes="Passenger sales and ticketing only: stated facts are supported, but no freight opportunity may exist; the signal is retained as excluded."))

# k02 cargo GSSA with explicit cargo wording: an opportunity with freight scope 'cargo'
KB1 = "Example Air invites proposals from general sales and service agents for cargo sales representation in Oman. Tender reference EXA-CGO-2027-02."
KB2 = "Proposals are due by 25 January 2027 at 12:00 GST."
add(Case("k02-cargo-gssa-om", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["OM"]}, ["OM"],
         ["freight_relevance", "plain"], "html", "RFP EXA-CGO-2027-02", f"{KB1}\n\n{KB2}",
         [claim("gssa_tender", KB1, {"airline": f("Example Air", KB1), "country": f("Oman", KB1), "service": f("GSSA", KB1), "status": f("open", KB1),
                                      "tender_ref": f("EXA-CGO-2027-02", KB1), "deadline": f("2027-01-25T12:00:00", KB2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Asia/Muscat")],
         {"opportunities": [opp("EXA-CGO-2027-02", day="2027-01-25", precision="instant", service="GSSA", freight_scope="cargo")]}))

# k03 generic "GSA" wording, neither cargo nor passenger stated: an opportunity that stays PENDING REVIEW (scope unclear)
KC1 = "Sample Airways invites proposals from general sales agents for representation in Bahrain. Tender reference SAW-GSA-2027-05."
KC2 = "Proposals must be received no later than 2 February 2027."
add(Case("k03-generic-gsa-unclear-bh", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["BH"]}, ["BH"],
         ["freight_relevance", "unclear_scope"], "html", "RFP SAW-GSA-2027-05", f"{KC1}\n\n{KC2}",
         [claim("gssa_tender", KC1, {"airline": f("Sample Airways", KC1), "country": f("Bahrain", KC1), "service": f("GSSA", KC1), "status": f("open", KC1),
                                      "tender_ref": f("SAW-GSA-2027-05", KC1), "deadline": f("2027-02-02", KC2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("SAW-GSA-2027-05", day="2027-02-02", precision="date", service="GSSA", freight_scope="unclear")]},
         notes="Generic GSA wording alone does not establish cargo relevance: the record exists but is pending review, not qualified."))

# k04 mixed mandate: passenger and cargo in one appointment: pending review as 'mixed'
KD1 = "Harbour Air Services seeks a general sales agent for passenger and cargo sales in Qatar. Tender reference HAS-GSA-2027-7. Bids are due on 9 February 2027."
add(Case("k04-mixed-gsa-qa", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["QA"]}, ["QA"],
         ["freight_relevance", "mixed_scope"], "html", "RFP HAS-GSA-2027-7", KD1,
         [claim("gssa_tender", KD1, {"airline": f("Harbour Air Services", KD1), "country": f("Qatar", KD1), "service": f("GSSA", KD1), "status": f("open", KD1),
                                      "tender_ref": f("HAS-GSA-2027-7", KD1), "deadline": f("2027-02-09", KD1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("HAS-GSA-2027-7", day="2027-02-09", precision="date", service="GSSA", freight_scope="mixed")]}))

# k05 defined territory (no preposition) vs a disclaimer naming another country: conflict flagged, the other country never supported
KE_T = "Request for proposal: cargo GSSA for the Territory"
KE1 = "Example Air invites proposals from cargo general sales and service agents for the Territory. Tender reference EXA-GSSA-2027-11."
KE2 = '"Territory" shall mean the geographical limits of the country, i.e. Bahrain.'
KE3 = "Disclaimer: this request for proposal is issued for cargo sales in the State of Kuwait and is governed by the laws of Kuwait."
KE4 = "Proposals must be submitted by 16 February 2027 at 14:00 AST."
add(Case("k05-defined-territory-vs-disclaimer", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["BH"]}, ["BH", "KW"],
         ["geography_conflict", "defined_territory", "conflicting_statements", "timezone_context"], "pdf", KE_T, f"{KE_T}\n\n{KE1}\n\n{KE2}\n\n{KE3}\n\n{KE4}",
         [claim("gssa_tender", KE1, {"airline": f("Example Air", KE1), "country": f("Bahrain", KE2), "service": f("GSSA", KE1), "status": f("open", KE1),
                                      "tender_ref": f("EXA-GSSA-2027-11", KE1), "deadline": f("2027-02-16T14:00:00", KE4)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("gssa_tender", KE1, {"airline": f("Example Air", KE1), "country": f("Kuwait", KE3), "service": f("GSSA", KE1), "status": f("open", KE1),
                                      "tender_ref": f("EXA-GSSA-2027-11", KE1)},
                {"airline": True, "country": False, "service": True, "status": True, "tender_ref": True})],
         {"opportunities": [opp("EXA-GSSA-2027-11", day="2027-02-16", precision="instant", service="GSSA", freight_scope="cargo")], "geography_conflict": True},
         notes="Bahrain is the defined territory (no preposition); the disclaimer's Kuwait must be flagged as a conflict, never a supported delivery territory. "
               "AST is established by Bahrain/Kuwait."))

# k06 genuine multi-country mandate with lots: every territory supported, no conflict
KF_T = "Request for proposal: cargo GSSA in Ghana, Togo and Benin"
KF1 = "Example Air invites proposals from cargo general sales and service agents in Ghana, Togo and Benin. Tender reference EXA-GSSA-2027-12."
KF2 = "Lot 1: Ghana (Accra). Lot 2: Togo (Lomé). Lot 3: Benin (Cotonou). Bidders may apply for one or more lots."
KF3 = "Proposals are due on 3 March 2027."
add(Case("k06-multi-country-lots-gh-tg-bj", "heldout3", "en", "airline_representation", {"geo_mode": "countries", "countries": ["GH", "TG", "BJ"]}, ["GH", "TG", "BJ"],
         ["multi_country", "multi_lot", "geography_roles"], "html", KF_T, f"{KF1}\n\n{KF2}\n\n{KF3}",
         [claim("gssa_tender", KF1, {"airline": f("Example Air", KF1), "country": f("Ghana", KF1), "service": f("GSSA", KF1), "status": f("open", KF1),
                                      "tender_ref": f("EXA-GSSA-2027-12", KF1), "deadline": f("2027-03-03", KF3)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("tender_scope", KF2, {"airline": f("Example Air", KF1), "tender_ref": f("EXA-GSSA-2027-12", KF1), "contract_territory": f("Togo", KF2)},
                {"tender_ref": True, "contract_territory": True}),
          claim("tender_scope", KF2, {"airline": f("Example Air", KF1), "tender_ref": f("EXA-GSSA-2027-12", KF1), "contract_territory": f("Benin", KF2)},
                {"tender_ref": True, "contract_territory": True}),
          claim("tender_scope", KF2, {"airline": f("Example Air", KF1), "tender_ref": f("EXA-GSSA-2027-12", KF1), "contract_territory": f("Nigeria", KF2)},
                {"tender_ref": True, "contract_territory": False})],
         {"opportunities": [opp("EXA-GSSA-2027-12", day="2027-03-03", precision="date", service="GSSA", freight_scope="cargo")], "geography_conflict": False}))

# k07 old notice with open wording but no closing date: status UNVERIFIED (not open, no invented date)
KG1 = "Example Air invites proposals from cargo GSSA providers for representation in Angola. Tender reference EXA-GSSA-2023-3."
KG2 = "Interested parties should contact the cargo department for the tender documents."
add(Case("k07-stale-open-no-deadline-ao", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["AO"]}, ["AO"],
         ["stale", "missing_deadline", "status_age"], "html", "RFP EXA-GSSA-2023-3", f"{KG1}\n\n{KG2}",
         [claim("gssa_tender", KG1, {"airline": f("Example Air", KG1), "country": f("Angola", KG1), "service": f("GSSA", KG1), "status": f("open", KG1),
                                      "tender_ref": f("EXA-GSSA-2023-3", KG1)}, {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True})],
         {"opportunities": [opp("EXA-GSSA-2023-3", status="unverified", day=None, precision=None, service="GSSA", freight_scope="cargo")]},
         published="2023-04-10T08:00:00Z",
         notes="The open wording is genuinely stated, but the notice is years old and gives no closing date: the status is not currently verified."))

# k08 old notice, no status wording, no deadline: HISTORICAL
KH1 = "Request for proposal for the appointment of a cargo general sales and service agent in Mozambique. Sample Airways. Reference SAW-GSSA-2022-9."
KH2 = "Applicants shall submit a separate application for each territory they apply for."
add(Case("k08-stale-no-status-mz", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["MZ"]}, ["MZ"],
         ["stale", "missing_deadline", "status_age"], "pdf", "RFP SAW-GSSA-2022-9", f"{KH1}\n\n{KH2}",
         [claim("gssa_tender", KH1, {"airline": f("Sample Airways", KH1), "country": f("Mozambique", KH1), "service": f("GSSA", KH1), "status": f("open", KH2),
                                      "tender_ref": f("SAW-GSSA-2022-9", KH1)}, {"airline": True, "country": True, "service": True, "status": False, "tender_ref": True})],
         {"opportunities": [opp("SAW-GSSA-2022-9", status="historical", day=None, precision=None, service="GSSA", freight_scope="cargo")]},
         published="2022-11-02T08:00:00Z",
         notes="'shall submit a separate application' is a procedure, not an open status; four years old without confirmation: historical."))

# k09 recent notice, no status wording, no deadline: unknown status (recent, so not historical), opportunity kept for review
KI1 = "Request for proposal for the appointment of a cargo GSSA in Rwanda. Example Air. Reference EXA-GSSA-2026-130."
add(Case("k09-recent-no-status-rw", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["RW"]}, ["RW"],
         ["missing_deadline", "status_age"], "html", "RFP EXA-GSSA-2026-130", KI1,
         [claim("gssa_tender", KI1, {"airline": f("Example Air", KI1), "country": f("Rwanda", KI1), "service": f("GSSA", KI1), "status": f("open", KI1),
                                      "tender_ref": f("EXA-GSSA-2026-130", KI1)}, {"airline": True, "country": True, "service": True, "status": False, "tender_ref": True})],
         {"opportunities": [opp("EXA-GSSA-2026-130", status="unknown", day=None, precision=None, service="GSSA", freight_scope="cargo")]},
         published="2026-10-20T08:00:00Z"))

# k10 French procurement announcement and service terminology
KJ1 = "Avis d'appel public à la concurrence : Air Exemple recherche des prestataires pour l'assistance en escale fret à l'aéroport de Lomé, Togo. Référence AEX-ESC-2027-2."
KJ2 = "Date limite de réception des offres : 15 mars 2027 à 10h00 GMT. Les candidats doivent justifier d'au moins trois ans d'expérience en manutention du fret."
add(Case("k10-fr-appel-public-tg", "heldout3", "fr", "outsourcing_training", {"geo_mode": "country", "countries": ["TG"]}, ["TG"],
         ["language_fr", "procurement_wording", "eligibility_numeric"], "html", "Avis d'appel public à la concurrence AEX-ESC-2027-2", f"{KJ1}\n\n{KJ2}",
         [claim("service_tender", KJ1, {"airline": f("Air Exemple", KJ1), "country": f("Togo", KJ1), "service": f("HANDLING", KJ1), "status": f("open", KJ2),
                                         "tender_ref": f("AEX-ESC-2027-2", KJ1), "deadline": f("2027-03-15T10:00:00", KJ2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", KJ2, {"airline": f("Air Exemple", KJ1), "tender_ref": f("AEX-ESC-2027-2", KJ1), "eligibility": f("au moins trois ans d'expérience en manutention du fret", KJ2)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", KJ2, {"airline": f("Air Exemple", KJ1), "tender_ref": f("AEX-ESC-2027-2", KJ1), "eligibility": f("au moins cinq ans d'expérience en manutention du fret", KJ2)},
                {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("AEX-ESC-2027-2", day="2027-03-15", precision="instant", service="HANDLING", freight_scope="cargo")]}, extra={"lang": "fr"}))

# k11 Spanish submission wording (open) and, in a second notice, award wording (awarded)
KK1 = "Convocatoria: Carga Ejemplo S.A. solicita ofertas para servicios de manipulación de carga aérea en Bogotá, Colombia. Referencia CEJ-HDL-2027-3."
KK2 = "Plazo de presentación de ofertas: 20 de febrero de 2027 a las 16:00 horas (hora de Colombia)."
add(Case("k11-es-presentacion-ofertas-co", "heldout3", "es", "outsourcing_training", {"geo_mode": "country", "countries": ["CO"]}, ["CO"],
         ["language_es", "procurement_wording"], "html", "Convocatoria CEJ-HDL-2027-3", f"{KK1}\n\n{KK2}",
         [claim("service_tender", KK1, {"organisation": f("Carga Ejemplo S.A.", KK1), "country": f("Colombia", KK1), "service": f("HANDLING", KK1), "status": f("open", KK2),
                                         "tender_ref": f("CEJ-HDL-2027-3", KK1), "deadline": f("2027-02-20T16:00:00", KK2)},
                {"organisation": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("CEJ-HDL-2027-3", day="2027-02-20", precision="local_time", service="HANDLING", freight_scope="cargo")]}, extra={"lang": "es"},
         notes="'hora de Colombia' names the place but no offset is stated: a local time."))

KL1 = "Adjudicación: la licitación CEJ-HDL-2026-9 para servicios de manipulación de carga aérea en Bogotá ha sido adjudicada a la empresa Servicios Andinos."
add(Case("k12-es-adjudicacion-co", "heldout3", "es", "outsourcing_training", {"geo_mode": "country", "countries": ["CO"]}, ["CO"],
         ["language_es", "award"], "html", "Adjudicación CEJ-HDL-2026-9", KL1,
         [claim("tender_status", KL1, {"organisation": f("Carga Ejemplo S.A.", KL1), "tender_ref": f("CEJ-HDL-2026-9", KL1), "status": f("awarded", KL1)},
                {"tender_ref": True, "status": True}),
          claim("service_tender", KL1, {"organisation": f("Servicios Andinos", KL1), "country": f("Colombia", KL1), "service": f("HANDLING", KL1), "status": f("open", KL1),
                                         "tender_ref": f("CEJ-HDL-2026-9", KL1)}, {"organisation": True, "country": True, "service": True, "status": False, "tender_ref": True})],
         {"opportunities": [], "historical": [{"ref": "CEJ-HDL-2026-9", "status": "awarded"}]}, extra={"lang": "es"}, notes="An award notice: never open. Bogotá names Colombia through the register, but the record is awarded, not a new opportunity."))

# k13 "seeking qualified ... agents" and EOI language with a planned contract
KM1 = "Example Air is seeking qualified General Sales and Service Agents to represent its cargo business in Zambia and Zimbabwe. Interested agents should submit their expression of interest by 30 January 2027."
add(Case("k13-seeking-agents-eoi-zm-zw", "heldout3", "en", "airline_representation", {"geo_mode": "countries", "countries": ["ZM", "ZW"]}, ["ZM", "ZW"],
         ["expression_of_interest", "procurement_wording", "multi_country"], "html", "Example Air seeks cargo GSSAs in Zambia and Zimbabwe", KM1,
         [claim("gssa_tender", KM1, {"airline": f("Example Air", KM1), "country": f("Zambia", KM1), "service": f("GSSA", KM1), "status": f("open", KM1),
                                      "deadline": f("2027-01-30", KM1)}, {"airline": True, "country": True, "service": True, "status": True, "deadline": True})],
         {"opportunities": [opp(None, day="2027-01-30", precision="date", service="GSSA", title_contains="Example Air", freight_scope="cargo")]}))

KN1 = "Expression of Interest EOI-RFS-2027-4: Sample Airways plans to contract qualified road feeder service providers for cargo trucking between Nairobi and Kampala."
KN2 = "Deadline for EOI submissions: 28 January 2027, 17:00 (UTC+3)."
add(Case("k14-eoi-plans-to-contract-rfs", "heldout3", "en", "trucking_gateways", {"geo_mode": "countries", "countries": ["KE", "UG"]}, ["KE", "UG"],
         ["expression_of_interest", "procurement_wording", "timezone_offset"], "html", "EOI-RFS-2027-4", f"{KN1}\n\n{KN2}",
         [claim("service_tender", KN1, {"airline": f("Sample Airways", KN1), "country": f("Kenya", KN1), "service": f("TRUCKING", KN1), "status": f("open", KN2),
                                         "tender_ref": f("EOI-RFS-2027-4", KN1), "deadline": f("2027-01-28T17:00:00", KN2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("EOI-RFS-2027-4", day="2027-01-28", precision="instant", service="TRUCKING", freight_scope="cargo")]},
         notes="'plans to contract' describes the later contract; the EOI itself is the current, open process."))

# k15 "should have" (advisory) and tender-security wording, with their meaning preserved
KO1 = "Example Air invites proposals from cargo GSSA providers in Ethiopia. Tender reference EXA-GSSA-2027-14. Proposals are due on 12 March 2027."
KO2 = "The Applicant should have at least three years of cargo GSA experience in the Territory. A Tender Security of USD 10,000 is required with the proposal."
add(Case("k15-should-have-tender-security-et", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["ET"]}, ["ET"],
         ["eligibility_numeric", "advisory_wording", "tender_security"], "html", "RFP EXA-GSSA-2027-14", f"{KO1}\n\n{KO2}",
         [claim("gssa_tender", KO1, {"airline": f("Example Air", KO1), "country": f("Ethiopia", KO1), "service": f("GSSA", KO1), "status": f("open", KO1),
                                      "tender_ref": f("EXA-GSSA-2027-14", KO1), "deadline": f("2027-03-12", KO1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", KO2, {"airline": f("Example Air", KO1), "tender_ref": f("EXA-GSSA-2027-14", KO1), "eligibility": f("at least three years of cargo GSA experience in the Territory", KO2)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", KO2, {"airline": f("Example Air", KO1), "tender_ref": f("EXA-GSSA-2027-14", KO1), "eligibility": f("at least five years of cargo GSA experience in the Territory", KO2)},
                {"tender_ref": True, "eligibility": False}),
          claim("eligibility", KO2, {"airline": f("Example Air", KO1), "tender_ref": f("EXA-GSSA-2027-14", KO1), "eligibility": f("a Tender Security of USD 10,000", KO2)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", KO2, {"airline": f("Example Air", KO1), "tender_ref": f("EXA-GSSA-2027-14", KO1), "eligibility": f("a Tender Security of USD 100,000", KO2)},
                {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("EXA-GSSA-2027-14", day="2027-03-12", precision="date", service="GSSA", freight_scope="cargo")]}))

# k16 amendment replacing a quantity, and a deadline extension stated as the new status
KP1 = "Corrigendum No. 1 to tender EXA-GSSA-2027-14 (cargo GSSA, Ethiopia)."
KP2 = "The minimum annual turnover is increased from USD 1 million to USD 2 million. The closing date, previously 12 March 2027, is now 26 March 2027."
add(Case("k16-corrigendum-quantity-and-extension-et", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["ET"]}, ["ET"],
         ["amendment", "quantity_replaced", "extension"], "html", "Corrigendum No. 1: EXA-GSSA-2027-14", f"{KP1}\n\n{KP2}",
         [claim("tender_status", KP2, {"airline": f("Example Air", KP1), "tender_ref": f("EXA-GSSA-2027-14", KP1), "status": f("revised", KP2), "deadline": f("2027-03-26", KP2)},
                {"tender_ref": True, "status": True, "deadline": True}),
          claim("tender_deadline", KP2, {"airline": f("Example Air", KP1), "tender_ref": f("EXA-GSSA-2027-14", KP1), "deadline": f("2027-03-12", KP2)},
                {"tender_ref": True, "deadline": False}),
          claim("eligibility", KP2, {"airline": f("Example Air", KP1), "tender_ref": f("EXA-GSSA-2027-14", KP1), "eligibility": f("a minimum annual turnover of USD 2 million", KP2)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", KP2, {"airline": f("Example Air", KP1), "tender_ref": f("EXA-GSSA-2027-14", KP1), "eligibility": f("a minimum annual turnover of USD 1 million", KP2)},
                {"tender_ref": True, "eligibility": False})],
         {"opportunities": [], "follower_only": True}, notes="The new quantity (USD 2 million) and the new date (26 March) stand; the replaced ones must not be supported."))

# k17 several eligibility criteria in one document, each proposed separately: every one must reach validation
KQ1 = "Example Air invites proposals from cargo GSSA providers in Uganda. Tender reference EXA-GSSA-2027-15. Proposals are due on 5 March 2027."
KQ2 = "Bidders must hold a valid IATA cargo agent accreditation."
KQ3 = "Bidders must have at least four years of cargo sales experience."
KQ4 = "Bidders must provide audited accounts for the last two financial years."
add(Case("k17-three-criteria-ug", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["UG"]}, ["UG"],
         ["eligibility_complex", "multiple_criteria"], "html", "RFP EXA-GSSA-2027-15", f"{KQ1}\n\n{KQ2}\n\n{KQ3}\n\n{KQ4}",
         [claim("gssa_tender", KQ1, {"airline": f("Example Air", KQ1), "country": f("Uganda", KQ1), "service": f("GSSA", KQ1), "status": f("open", KQ1),
                                      "tender_ref": f("EXA-GSSA-2027-15", KQ1), "deadline": f("2027-03-05", KQ1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", KQ2, {"airline": f("Example Air", KQ1), "tender_ref": f("EXA-GSSA-2027-15", KQ1), "eligibility": f("a valid IATA cargo agent accreditation", KQ2)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", KQ3, {"airline": f("Example Air", KQ1), "tender_ref": f("EXA-GSSA-2027-15", KQ1), "eligibility": f("at least four years of cargo sales experience", KQ3)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", KQ4, {"airline": f("Example Air", KQ1), "tender_ref": f("EXA-GSSA-2027-15", KQ1), "eligibility": f("audited accounts for the last two financial years", KQ4)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", KQ3, {"airline": f("Example Air", KQ1), "tender_ref": f("EXA-GSSA-2027-15", KQ1), "eligibility": f("at least two years of cargo sales experience", KQ3)},
                {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("EXA-GSSA-2027-15", day="2027-03-05", precision="date", service="GSSA", freight_scope="cargo")]}))

# k18 ambiguous numeric dates: the document's own dating convention establishes the reading
KR1 = "Request for proposal for the appointment of a cargo GSSA in Nepal. Sample Airways. Reference SAW-GSSA-2027-2. Date of issue: 20-01-2027."
KR2 = "Last date for submission of proposals: 05-03-2027 at 15:00 NPT."
add(Case("k18-numeric-dates-convention-np", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["NP"]}, ["NP"],
         ["ambiguous_dates", "date_convention"], "pdf", "RFP SAW-GSSA-2027-2", f"{KR1}\n\n{KR2}",
         [claim("gssa_tender", KR1, {"airline": f("Sample Airways", KR1), "country": f("Nepal", KR1), "service": f("GSSA", KR1), "status": f("open", KR2),
                                      "tender_ref": f("SAW-GSSA-2027-2", KR1), "deadline": f("2027-03-05T15:00:00", KR2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("tender_deadline", KR2, {"airline": f("Sample Airways", KR1), "tender_ref": f("SAW-GSSA-2027-2", KR1), "deadline": f("2027-05-03T15:00:00", KR2)},
                {"tender_ref": True, "deadline": False})],
         {"opportunities": [opp("SAW-GSSA-2027-2", day="2027-03-05", precision="instant", service="GSSA", freight_scope="cargo")]},
         notes="'20-01-2027' can only be day-first, so '05-03-2027' is 5 March; 3 May must not be supported."))

# k19 ambiguous numeric date with nothing to establish it: kept for review, not a fact
KS1 = "Example Air invites proposals from cargo GSSA providers in Sri Lanka. Tender reference EXA-GSSA-2027-16. Closing date: 05/03/2027."
add(Case("k19-numeric-date-unresolved-lk", "heldout3", "en", "airline_representation", {"geo_mode": "country", "countries": ["LK"]}, ["LK"],
         ["ambiguous_dates"], "html", "RFP EXA-GSSA-2027-16", KS1,
         [claim("gssa_tender", KS1, {"airline": f("Example Air", KS1), "country": f("Sri Lanka", KS1), "service": f("GSSA", KS1), "status": f("open", KS1),
                                      "tender_ref": f("EXA-GSSA-2027-16", KS1), "deadline": f("2027-03-05", KS1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": False})],
         {"opportunities": [opp("EXA-GSSA-2027-16", day=None, precision=None, service="GSSA", freight_scope="cargo")]},
         notes="Neither reading is established: the deadline waits for review; the record has no deadline."))

# k20 passenger route concession (public service obligation): not a freight opportunity
KT1 = "Licitación: servicios de transporte aéreo regular sometidos a obligaciones de servicio público en la ruta Valencia-Oviedo. Expediente 44A2027."
KT2 = "Plazo de recepción de ofertas: 15 de febrero de 2027 a las 12:00 (UTC+01:00)."
add(Case("k20-es-pso-passenger-route", "heldout3", "es", "service_operations", {"geo_mode": "country", "countries": ["ES"]}, ["ES"],
         ["language_es", "passenger_only", "freight_relevance"], "html", "Licitación 44A2027", f"{KT1}\n\n{KT2}",
         [claim("service_tender", KT1, {"organisation": f("Dirección General de Aviación Civil", KT1), "country": f("Spain", KT1), "service": f("HANDLING", KT1),
                                         "status": f("open", KT2), "tender_ref": f("44A2027", KT1), "deadline": f("2027-02-15T12:00:00", KT2)},
                {"organisation": False, "country": True, "service": False, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "passenger"}]}, extra={"lang": "es"},
         notes="A passenger air-service obligation: no freight service; the organisation is not named in the quote; Spain is named only through its cities."))


def heldout3_cases() -> list[Case]:
    return list(HELDOUT3)
