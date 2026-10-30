# Public-source demonstration

Deployment: http://127.0.0.1:3000 · market: LT · airports: KUN
Started: 2026-10-30T08:36:18Z · inputs: **SIMULATED**

## Steps

- **preflight** (2026-10-30T08:36:18Z): {"search": {"connected": true, "detail": "connected", "provider": "brave", "enabled": true}, "extractor": {"connected": true, "detail": "connected", "estimate_per_document_usd": "0.1125", "kill_switch": true, "budget": null}, "directory": {"using": "seed", "total_records": 424, "dataset": {"key": "airport_seed", "name": "ATLAS bundled airport seed", "source": "curated by the ATLAS build (public knowledge; codes as published by ICAO/IATA)", "url": null, "licence": "no restriction", "version": "2026-10-30", "refreshed_at": "2026-10-30T00:00:00+00:00", "loaded_at": "2026-10-30T08:36:18.335566+00:
- **company_discovery** (2026-10-30T08:36:19Z): {"outcome": "incomplete", "organisations": [["Nemunas Cargo Services UAB", 100, "cargo_services"], ["Amber Example Air", 60, "belly"], ["Vilnius Freight Hub UAB", 55, "cargo_services"], ["Baltic Ticket Centre UAB", 0, "passenger_only"]], "unavailable": [{"method": "linkedin_profiles", "reason": "no authorised LinkedIn integration is connected: a LinkedIn search link is offered per contact, and a profile is saved only when a person confirms it"}]}
- **company_research** (2026-10-30T08:36:21Z): {"company": "Nemunas Cargo Services UAB", "website": "http://127.0.0.1:8089/nemunascargo/", "website_basis": "the page names the organisation in its title or opening lines and the site name matches (127.0.0.1)", "contact_page": "http://127.0.0.1:8089/nemunascargo/contact.html", "emails": [["cargo@nemunascargo.example", "cargo"], ["ops@nemunascargo.example", "operations"], ["ruta.kazlauskiene@nemunascargo.example", "personal"], ["sales@nemunascargo.example", "sales"]], "airports": [["KUN", "Station (operates here)"], ["VNO", "Served (from elsewhere)"]], "representation": [["Amber Example Air", 
- **company_research** (2026-10-30T08:36:21Z): {"company": "Amber Example Air", "website": null, "website_basis": null, "contact_page": null, "emails": [], "airports": [], "representation": [], "people": [], "fields": {"website": "not_found_after_research", "contact_page": "not_found_after_research", "emails": "not_searched", "services": "not_searched", "locations": "not_searched", "airports": "not_searched", "representation": "not_searched", "people": "not_found_after_research"}, "stages": {"identify": "not_applicable", "identity": "done", "company": "not_run", "people": "done", "relationships": "done", "relevance": "done"}, "pending": []
- **company_research** (2026-10-30T08:36:22Z): {"company": "Vilnius Freight Hub UAB", "website": null, "website_basis": null, "contact_page": null, "emails": [], "airports": [], "representation": [], "people": [], "fields": {"website": "not_found_after_research", "contact_page": "not_found_after_research", "emails": "not_searched", "services": "not_searched", "locations": "found", "airports": "not_searched", "representation": "not_searched", "people": "not_found_after_research"}, "stages": {"identify": "not_applicable", "identity": "done", "company": "not_run", "people": "done", "relationships": "done", "relevance": "done"}, "pending": []}
- **opportunity_search** (2026-10-30T08:36:32Z): {"status": "partial", "outcome": "incomplete", "results": [], "note": "a signal is tracked as an opportunity only by a person: rerun with --track-signal <id> after reviewing the results"}
- **opportunity_recorded_by_a_person** (2026-10-30T08:36:32Z): {"company": "Nemunas Cargo Services UAB", "opportunity": "b3041ba4-b712-48d3-a1c0-7f2ee0104fe6"}
- **research_file** (2026-10-30T08:36:33Z): {"stages": {"identify": "done", "identity": "done", "company": "done", "people": "done", "relationships": "done", "relevance": "done"}, "uncertain": ["No open tender or procurement is confirmed: this is potential, not a bid opportunity", "Relationship research has not been run for this opportunity", "No confirmed procurement or tender contact at Nemunas Cargo Services UAB", "No confirmed head of cargo / commercial leader at Nemunas Cargo Services UAB", "No confirmed country or regional representative at Nemunas Cargo Services UAB", "No existing WFC relationship recorded with anyone at Nemunas 

## Queries run

- cargo GSAs forwarders Kaunas airlines represent cargo OR freight OR airline ("Kaunas Airport" OR KUN OR "Kaunas") "Lithuania"
- ("GSSA" OR "GSA" OR "cargo sales agent" OR "general sales agent") cargo ("Kaunas Airport" OR KUN OR "Kaunas") "Lithuania"
- (airline OR "cargo airline" OR freighter) cargo ("Kaunas Airport" OR KUN OR "Kaunas") "Lithuania"
- ("represented airlines" OR "airlines we represent" OR "our principals" OR "GSA for") ("Kaunas Airport" OR KUN OR "Kaunas") "Lithuania"
- (directory OR members OR "list of") (GSSA OR "cargo agents" OR forwarders OR handlers) ("Kaunas Airport" OR KUN OR "Kaunas") "Lithuania"
- "Nemunas Cargo Services UAB" official website
- "Nemunas Cargo Services UAB" contact
- "Nemunas Cargo Services UAB" appoints OR appointed OR "joins as" cargo
- "Nemunas Cargo Services UAB" leadership team OR management team
- "Amber Example Air" official website
- "Amber Example Air" contact
- "Kilimanjaro Example Cargo" official website
- "Kilimanjaro Example Cargo" contact
- "Amber Example Air" appoints OR appointed OR "joins as" cargo
- "Amber Example Air" leadership team OR management team
- "Kilimanjaro Example Cargo" appoints OR appointed OR "joins as" cargo
- "Kilimanjaro Example Cargo" leadership team OR management team
- "Vilnius Freight Hub UAB" official website
- "Vilnius Freight Hub UAB" contact
- "Vilnius Freight Hub UAB" appoints OR appointed OR "joins as" cargo
- "Vilnius Freight Hub UAB" leadership team OR management team
- cargo GSAs forwarders Kaunas airlines represent cargo OR freight OR airline "Lithuania" ("Kaunas Airport" OR KUN OR "Kaunas")
- cargo GSAs forwarders Kaunas airlines represent (tender OR RFP OR "request for proposal" OR "expression of interest") (GSSA OR "cargo sales agent" OR "general sales agent" OR "cargo representation") "Lithuania" ("Kaunas Airport" OR KUN OR "Kaunas")
- cargo GSAs forwarders Kaunas airlines represent ("appoints" OR "appointed" OR "new GSSA" OR "cargo GSA") airline cargo "Lithuania" ("Kaunas Airport" OR KUN OR "Kaunas")
- cargo GSAs forwarders Kaunas airlines represent "total cargo management" OR "cargo outsourcing" airline "Lithuania" ("Kaunas Airport" OR KUN OR "Kaunas")
- "Nemunas Cargo Services UAB" ("procurement" OR "tender") Lithuania
- "Nemunas Cargo Services UAB" ("head of cargo" OR "cargo director") Lithuania
- "Nemunas Cargo Services UAB" ("country manager" OR "regional manager") Lithuania
- "Nemunas Cargo Services UAB" appoints OR appointed OR "joins as"
- "Nemunas Cargo Services UAB" press release Lithuania cargo
- "Amber Example Air" ("procurement" OR "tender") Lithuania
- "Amber Example Air" ("head of cargo" OR "cargo director") Lithuania
- "Kilimanjaro Example Cargo" ("procurement" OR "tender") Lithuania
- "Kilimanjaro Example Cargo" ("head of cargo" OR "cargo director") Lithuania

## Sources

- read: http://127.0.0.1:8089/nemunascargo/
- read: http://127.0.0.1:8089/nemunascargo/airlines.html
- read: http://127.0.0.1:8089/nemunascargo/contact.html
- read: http://127.0.0.1:8089/lt-news/amber-gssa.html
- read: http://127.0.0.1:8089/nemunascargo/team.html

## Costs

Total recorded: USD 0.0000 over 11 step(s).
- company discovery: USD 0.0000
- deep research Nemunas Cargo Services UAB: USD 0
- deep research Nemunas Cargo Services UAB: USD 0
- deep research Nemunas Cargo Services UAB: USD 0
- deep research Amber Example Air: USD 0
- deep research Amber Example Air: USD 0
- deep research Amber Example Air: USD 0
- deep research Vilnius Freight Hub UAB: USD 0
- deep research Vilnius Freight Hub UAB: USD 0
- deep research Vilnius Freight Hub UAB: USD 0
- deep research of the opportunity: USD 0

## Failures (recorded by the application)

- none recorded

## Unresolved gaps

See the research file's 'uncertain' list and each company's field statuses in demo.json.

## Manual comparison against the original sources (to be completed by the reviewer)

Fill in review.csv row by row against the ORIGINAL page, then summarise here:

### Incorrect associations (a fact, role or e-mail attached to the wrong company or person)

- …

### Missed information (on the original pages but not captured)

- …

### Review

Accuracy is OUTSTANDING until a reviewer fills in review.csv against the original pages.
