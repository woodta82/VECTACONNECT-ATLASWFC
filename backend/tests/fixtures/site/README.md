# Fixture source site (SYNTHETIC)

Every organisation, tender, reference and route here is invented ("Example Air",
"Sample Airways", "Coastal Handling"). Nothing describes a real airline, tender or
WFC record. The site is served on 127.0.0.1 by `tests/fixtures/servers.py`
(or `tools/fixture_site.py`) for offline tests, the browser journeys and the
local demonstration stack. It stands in for real airline newsrooms and
procurement portals, which are configured as sources in a deployment.

`people/` and `people-later/` (28 Oct 2026, relationship-intelligence journey): an invented airline ("Savanna Example
Air") with a Kenya tender naming a procurement contact, a syndicated copy of it, a Uganda tender, a route announcement
quoting a head of cargo, and (served separately so it can arrive later) the Kenya tender's cancellation. The people
named are invented.

`sea-company/`, `sea-press/` and `robots.txt` (28 Oct 2026, relationship-research continuation): the invented airline's own
site (navigation to a leadership page, a media centre with news items, a page `robots.txt` disallows) and a trade-press
appointment page. `/search-api/res/v1/web/search` is a SIMULATED stand-in for the Brave Search API with a fixed index of
fixture pages; the local stack points `SEARCH_API_BASE_URL` at it. Every person and organisation named is invented.
