# Airport directory import package

Place a verified import package here (`airports.csv.gz` + `manifest.json`) and set `AIRPORTS_PACKAGE=/srv/airports-package`
to load it at deployment instead of downloading. Build one where the publisher's site is reachable:

    curl -O https://davidmegginson.github.io/ourairports-data/airports.csv
    python -m app.airports_cli package --file airports.csv --version <date> --refreshed-at <date> --out deploy/airports-package
    python -m app.airports_cli verify deploy/airports-package

OurAirports releases its data into the public domain, so the package may be redistributed. The loader recomputes the SHA-256,
row and code counts and refuses a package that does not match its manifest. No package is included in this release: the build
environment had no outbound access to the publisher.
