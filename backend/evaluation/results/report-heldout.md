# Extraction-quality evaluation

Run at 2026-10-26T16:38:36+00:00 on validation rules v2. 12 cases (0 tuning, 12 held-out).

**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices (RFP pages, corrigenda, award and cancellation notices, newsroom items, tabular tender listings, PDF notices; English, French, Spanish, Portuguese, German). None is a genuine notice: no public portal was reachable from the build environment and no authorised source was supplied. The extractor is SCRIPTED (it returns the case's proposals, correct and incorrect readings alike); no AI provider was called. These numbers therefore measure the validation, identity, deadline, contradiction and coverage logic on authored notices. They are not real-world extraction quality and do not show market coverage.

**Held-out protocol.** Held-out cases were written before the final rule changes and run once at the end; no rule was changed after seeing their results. Failures in the held-out set are reported below as limitations.

## By split

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| heldout | 12 | 10/10 (100%) | 10/10 (100%) | 35/40 (88%) | 0/15 (0%) | 12/84 (14%) | 12/12 (100%) |

## By category

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| amendment | 2 | 2/2 (100%) | 2/2 (100%) | 5/8 (62%) | 0/1 (0%) | 3/13 (23%) | 2/2 (100%) |
| cancellation | 1 | 1/1 (100%) | 1/1 (100%) | 1/4 (25%) | 0/1 (0%) | 2/7 (29%) | 1/1 (100%) |
| capacity | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/3 (0%) | 0/4 (0%) | 1/1 (100%) |
| conflicting_statements | 1 | 1/1 (100%) | 1/1 (100%) | 1/4 (25%) | 0/1 (0%) | 2/7 (29%) | 1/1 (100%) |
| eligibility_complex | 2 | 2/2 (100%) | 2/2 (100%) | 7/8 (88%) | 0/3 (0%) | 2/19 (11%) | 2/2 (100%) |
| eligibility_dates | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/2 (0%) | 1/10 (10%) | 1/1 (100%) |
| eligibility_numeric | 3 | 3/3 (100%) | 3/3 (100%) | 12/12 (100%) | 0/4 (0%) | 6/28 (21%) | 3/3 (100%) |
| eligibility_roles | 1 | 1/1 (100%) | 1/1 (100%) | 3/4 (75%) | 0/2 (0%) | 0/10 (0%) | 1/1 (100%) |
| internal_area | 2 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/3 (0%) | 0/2 (0%) | 2/2 (100%) |
| language_es | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 2/9 (22%) | 1/1 (100%) |
| language_fr | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 3/9 (33%) | 1/1 (100%) |
| long_document | 1 | 1/1 (100%) | 1/1 (100%) | 3/4 (75%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| missing_deadline | 1 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/1 (0%) | 1/12 (8%) | 1/1 (100%) |
| multi_opportunity | 1 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/1 (0%) | 1/12 (8%) | 1/1 (100%) |
| not_procurement | 2 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/3 (0%) | 0/2 (0%) | 2/2 (100%) |
| pdf | 1 | 1/1 (100%) | 1/1 (100%) | 3/4 (75%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| table | 1 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/1 (0%) | 1/12 (8%) | 1/1 (100%) |
| timezone_unclear | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 2/9 (22%) | 1/1 (100%) |
| worldwide | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/3 (0%) | 0/4 (0%) | 1/1 (100%) |

## By language

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| en | 10 | 8/8 (100%) | 8/8 (100%) | 27/32 (84%) | 0/13 (0%) | 7/66 (11%) | 10/10 (100%) |
| es | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 2/9 (22%) | 1/1 (100%) |
| fr | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 3/9 (33%) | 1/1 (100%) |

## By capability area

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| airline_representation | 4 | 4/4 (100%) | 4/4 (100%) | 11/16 (69%) | 0/4 (0%) | 4/32 (12%) | 4/4 (100%) |
| capacity_lanes | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/3 (0%) | 0/4 (0%) | 1/1 (100%) |
| forwarder_sales | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/2 (0%) | 0/2 (0%) | 1/1 (100%) |
| outsourcing_training | 3 | 3/3 (100%) | 3/3 (100%) | 12/12 (100%) | 0/3 (0%) | 4/25 (16%) | 3/3 (100%) |
| service_operations | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/1 (0%) | 0/0 (n/a) | 1/1 (100%) |
| technology_solutions | 1 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/1 (0%) | 1/12 (8%) | 1/1 (100%) |
| trucking_gateways | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 3/9 (33%) | 1/1 (100%) |

## By search mode

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| countries | 2 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/1 (0%) | 4/15 (27%) | 2/2 (100%) |
| country | 7 | 5/5 (100%) | 5/5 (100%) | 15/20 (75%) | 0/8 (0%) | 6/43 (14%) | 7/7 (100%) |
| region | 2 | 3/3 (100%) | 3/3 (100%) | 12/12 (100%) | 0/3 (0%) | 2/22 (9%) | 2/2 (100%) |
| worldwide | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/3 (0%) | 0/4 (0%) | 1/1 (100%) |

## Per case

| Case | Split | Lang | Area | Found/gold | Missed | False opp. | Field acc. | False sup. | Missed sup. | Coverage | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h01-gssa-sc-roles | heldout | en | airline_representation | 1/1 | — | 0 | 3/4 (75%) | 0 | 0 | complete |  |
| h02-invoicing-sa-dates | heldout | en | outsourcing_training | 1/1 | — | 0 | 4/4 (100%) | 0 | 1 | complete | missed: eligibility.eligibility = 'a licence valid after 30 June 2027 and at least 25 staff': review_required (the source's date 2027-02-01 (on or before) is left out of the value) |
| h03-fr-trucking-sn | heldout | fr | trucking_gateways | 1/1 | — | 0 | 4/4 (100%) | 0 | 3 | complete | missed: service_tender.country = 'Senegal': unsupported (the quote does not state Senegal); eligibility.tender_ref = 'ASH-RFS-2026-2': not_assessed (the proposal did not reach validation (not in a read section, or rejected before field validation)); eligibility.eligibility = 'au moins 8 camions et une licence de transport routier valide au Sénégal': not_assessed (the proposal did not reach validation (not in a read section, or rejected before field validation)) |
| h04-withdrawn-mw | heldout | en | airline_representation | 1/1 | — | 0 | 1/4 (25%) | 0 | 2 | complete | contradiction flagged: yes · missed: tender_status.tender_ref = 'EXA-GSSA-2026-110': not_assessed (the proposal did not reach validation (not in a read section, or rejected before field validation)); tender_status.status = 'cancelled': not_assessed (the proposal did not reach validation (not in a read section, or rejected before field validation)) |
| h05-table-ea | heldout | en | technology_solutions | 2/2 | — | 0 | 8/8 (100%) | 0 | 1 | complete | missed: service_tender.country = 'Kenya': unsupported (Kenya is named, but the quote does not establish it as the delivery country: named, but the sentence does not say whethe) |
| h06-long-pdf-cv | heldout | en | airline_representation | 1/1 | — | 0 | 3/4 (75%) | 0 | 0 | complete; first run flagged incomplete: yes |  |
| h07-es-training-cl | heldout | es | outsourcing_training | 1/1 | — | 0 | 4/4 (100%) | 0 | 2 | complete | missed: eligibility.tender_ref = 'ACS-CAP-2026-3': not_assessed (the proposal did not reach validation (not in a read section, or rejected before field validation)); eligibility.eligibility = 'al menos tres instructores certificados': not_assessed (the proposal did not reach validation (not in a read section, or rejected before field validation)) |
| h08-capacity-sg-au | heldout | en | capacity_lanes | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete | signal areas: airline_representation (expected airline_representation) |
| h09-or-condition-bw | heldout | en | airline_representation | 1/1 | — | 0 | 4/4 (100%) | 0 | 2 | complete | missed: eligibility.tender_ref = 'EXA-GSSA-2026-115': not_assessed (the proposal did not reach validation (not in a read section, or rejected before field validation)); eligibility.eligibility = 'an office in Gaborone or Francistown': not_assessed (the proposal did not reach validation (not in a read section, or rejected before field validation)) |
| h10-forwarder-hub-za | heldout | en | forwarder_sales | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete |  |
| h11-amended-scope-de | heldout | en | outsourcing_training | 1/1 | — | 0 | 4/4 (100%) | 0 | 1 | complete | missed: service_tender.country = 'Germany': unsupported (Germany is named, but the quote does not establish it as the delivery country: named, but the sentence does not say whet) |
| h12-ops-relocation-ke | heldout | en | service_operations | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete |  |

## Reading the numbers

- *Opportunity precision/recall*: opportunities created by the pipeline against the opportunities a reviewer finds in the notice, matched by tender reference. A cancelled, awarded or non-procurement notice has no gold opportunity, so anything created is false.
- *Field accuracy*: status, deadline day, deadline precision and service of each matched opportunity against the gold.
- *False 'supported'*: proposed values the notice does not state that were labelled supported. This is the measure the eligibility amendment targets; the target is zero.
- *Missed 'supported'*: values the notice does state that were not labelled supported (a stricter rule costs some recall; those go to review, never to 'supported').
- *Coverage*: whether every document was completely read by the end; long documents must first be flagged incomplete.
- Capability areas fed by WFC's own records (account growth, forwarder sales, service and operations) have no discoverable opportunities by design; their cases check that no opportunity is invented from a public notice.
