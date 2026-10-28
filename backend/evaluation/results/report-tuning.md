# Extraction-quality evaluation

Run at 2026-10-26T16:38:12+00:00 on validation rules v2. 20 cases (20 tuning, 0 held-out).

**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices (RFP pages, corrigenda, award and cancellation notices, newsroom items, tabular tender listings, PDF notices; English, French, Spanish, Portuguese, German). None is a genuine notice: no public portal was reachable from the build environment and no authorised source was supplied. The extractor is SCRIPTED (it returns the case's proposals, correct and incorrect readings alike); no AI provider was called. These numbers therefore measure the validation, identity, deadline, contradiction and coverage logic on authored notices. They are not real-world extraction quality and do not show market coverage.

**Held-out protocol.** Held-out cases were written before the final rule changes and run once at the end; no rule was changed after seeing their results. Failures in the held-out set are reported below as limitations.

## By split

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| tuning | 20 | 16/16 (100%) | 16/16 (100%) | 64/64 (100%) | 0/23 (0%) | 2/128 (2%) | 20/20 (100%) |

## By category

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| amendment | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/1 (0%) | 0/4 (0%) | 1/1 (100%) |
| award | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 0/6 (0%) | 1/1 (100%) |
| cancellation | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 0/6 (0%) | 1/1 (100%) |
| capacity | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/5 (0%) | 0/2 (0%) | 1/1 (100%) |
| conflicting_statements | 2 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/1 (0%) | 0/14 (0%) | 2/2 (100%) |
| eligibility_complex | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/3 (0%) | 1/13 (8%) | 1/1 (100%) |
| eligibility_dates | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/3 (0%) | 1/13 (8%) | 1/1 (100%) |
| eligibility_numeric | 2 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/2 (0%) | 0/18 (0%) | 2/2 (100%) |
| eligibility_roles | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/3 (0%) | 1/13 (8%) | 1/1 (100%) |
| historical_reference | 2 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/3 (0%) | 0/14 (0%) | 2/2 (100%) |
| internal_area | 3 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/5 (0%) | 0/5 (0%) | 3/3 (100%) |
| language_de | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| language_es | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| language_fr | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 0/6 (0%) | 1/1 (100%) |
| language_pt | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| long_document | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| missing_deadline | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 0/6 (0%) | 1/1 (100%) |
| multi_opportunity | 2 | 4/4 (100%) | 4/4 (100%) | 16/16 (100%) | 0/2 (0%) | 1/26 (4%) | 2/2 (100%) |
| not_procurement | 3 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/5 (0%) | 0/5 (0%) | 3/3 (100%) |
| partnership | 2 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/1 (0%) | 0/3 (0%) | 2/2 (100%) |
| pdf | 2 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/1 (0%) | 0/15 (0%) | 2/2 (100%) |
| plain | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 0/9 (0%) | 1/1 (100%) |
| table | 1 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/1 (0%) | 1/13 (8%) | 1/1 (100%) |
| timezone_unclear | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| worldwide | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/5 (0%) | 0/2 (0%) | 1/1 (100%) |

## By language

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| de | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| en | 16 | 12/12 (100%) | 12/12 (100%) | 48/48 (100%) | 0/22 (0%) | 2/104 (2%) | 16/16 (100%) |
| es | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| fr | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 0/6 (0%) | 1/1 (100%) |
| pt | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |

## By capability area

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| account_growth | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/1 (0%) | 0/1 (0%) | 1/1 (100%) |
| airline_representation | 9 | 9/9 (100%) | 9/9 (100%) | 36/36 (100%) | 0/10 (0%) | 1/71 (1%) | 9/9 (100%) |
| capacity_lanes | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/5 (0%) | 0/2 (0%) | 1/1 (100%) |
| forwarder_sales | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/2 (0%) | 0/2 (0%) | 1/1 (100%) |
| network_development | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/2 (0%) | 1/1 (100%) |
| outsourcing_training | 4 | 5/5 (100%) | 5/5 (100%) | 20/20 (100%) | 0/2 (0%) | 1/33 (3%) | 4/4 (100%) |
| service_operations | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/2 (0%) | 0/2 (0%) | 1/1 (100%) |
| technology_solutions | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/0 (n/a) | 0/6 (0%) | 1/1 (100%) |
| trucking_gateways | 1 | 1/1 (100%) | 1/1 (100%) | 4/4 (100%) | 0/1 (0%) | 0/9 (0%) | 1/1 (100%) |

## By search mode

| Group | Cases | Opportunity precision | Opportunity recall | Field accuracy | False 'supported' | Missed 'supported' | Complete coverage |
|---|---|---|---|---|---|---|---|
| countries | 3 | 2/2 (100%) | 2/2 (100%) | 8/8 (100%) | 0/2 (0%) | 0/16 (0%) | 3/3 (100%) |
| country | 14 | 11/11 (100%) | 11/11 (100%) | 44/44 (100%) | 0/15 (0%) | 1/91 (1%) | 14/14 (100%) |
| region | 2 | 3/3 (100%) | 3/3 (100%) | 12/12 (100%) | 0/1 (0%) | 1/19 (5%) | 2/2 (100%) |
| worldwide | 1 | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/5 (0%) | 0/2 (0%) | 1/1 (100%) |

## Per case

| Case | Split | Lang | Area | Found/gold | Missed | False opp. | Field acc. | False sup. | Missed sup. | Coverage | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| t01-gssa-ke | tuning | en | airline_representation | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t02-two-lots-ug | tuning | en | airline_representation | 2/2 | — | 0 | 8/8 (100%) | 0 | 0 | complete |  |
| t03-corrigendum-ke | tuning | en | airline_representation | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete |  |
| t04-cancelled-tz | tuning | en | airline_representation | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete | contradiction flagged: yes |
| t05-historical-gh | tuning | en | airline_representation | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t06-eligibility-complex-et | tuning | en | airline_representation | 1/1 | — | 0 | 4/4 (100%) | 0 | 1 | complete | missed: eligibility.eligibility = 'three years of insurance cover and five years of GSSA experience': review_required (the source's date 2027-01-01 (on or before) is left out of the value) |
| t07-table-gcc | tuning | en | outsourcing_training | 2/2 | — | 0 | 8/8 (100%) | 0 | 1 | complete | missed: service_tender.country = 'Qatar': unsupported (Qatar is named, but the quote does not establish it as the delivery country: named, but the sentence does not say whethe) |
| t08-pdf-trucking-ae | tuning | en | trucking_gateways | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t09-fr-training-no-deadline | tuning | fr | outsourcing_training | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t10-es-technology-tz-unclear | tuning | es | technology_solutions | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t11-conflicting-deadlines-rw | tuning | en | outsourcing_training | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t12-capacity-worldwide | tuning | en | capacity_lanes | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete | signal areas: capacity_lanes (expected capacity_lanes) |
| t13-partnership-om | tuning | en | network_development | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete | signal areas: network_development (expected network_development) |
| t14-long-pdf-mu | tuning | en | airline_representation | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete; first run flagged incomplete: yes |  |
| t15-award-zm | tuning | en | airline_representation | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t16-pt-handling-ao | tuning | pt | outsourcing_training | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t17-forwarder-news-ke | tuning | en | forwarder_sales | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete |  |
| t18-de-gssa-at | tuning | de | airline_representation | 1/1 | — | 0 | 4/4 (100%) | 0 | 0 | complete |  |
| t19-ops-notice-ke | tuning | en | service_operations | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete |  |
| t20-account-growth-ae | tuning | en | account_growth | 0/0 | — | 0 | 0/0 (n/a) | 0 | 0 | complete | signal areas: network_development (expected network_development) |

## Reading the numbers

- *Opportunity precision/recall*: opportunities created by the pipeline against the opportunities a reviewer finds in the notice, matched by tender reference. A cancelled, awarded or non-procurement notice has no gold opportunity, so anything created is false.
- *Field accuracy*: status, deadline day, deadline precision and service of each matched opportunity against the gold.
- *False 'supported'*: proposed values the notice does not state that were labelled supported. This is the measure the eligibility amendment targets; the target is zero.
- *Missed 'supported'*: values the notice does state that were not labelled supported (a stricter rule costs some recall; those go to review, never to 'supported').
- *Coverage*: whether every document was completely read by the end; long documents must first be flagged incomplete.
- Capability areas fed by WFC's own records (account growth, forwarder sales, service and operations) have no discoverable opportunities by design; their cases check that no opportunity is invented from a public notice.
