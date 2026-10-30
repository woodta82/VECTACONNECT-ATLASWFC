"""The global airport directory beyond the bundled seed (30 Oct 2026, amendment item 3), on PostgreSQL.

* status says which directory is in use (seed / partial / full) with source, version, refresh date and total records;
* a verified import package: built from the publisher's file, recomputed on load, a tampered package refused;
* selection by airport name, city, country (code or name), IATA and ICAO, airports without an IATA code, multiple selections, and the
  all-airports country / region / worldwide scope — through the API the screens use, and applied to discovery, the Dashboard and Opportunities;
* directory inclusion is never evidence of cargo operations.

The OurAirports rows below are written in the publisher's own format; the "full" threshold test uses generated rows (clearly synthetic
idents) because the complete file could not be downloaded in the build environment.
"""
from __future__ import annotations

import gzip
import json

import pytest

from app import airports_cli as cli
from app.services import airport_directory as ad
from app.services import discovery as dsc
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_relationship_journey import client_for

HEADER = ("id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,iso_region,municipality,scheduled_service,"
          "gps_code,iata_code,local_code,home_link,wikipedia_link,keywords\n")
ROWS = (
    "1,EYKA,medium_airport,Kaunas International Airport,54.96,24.08,256,EU,LT,LT-KU,Kaunas,yes,EYKA,KUN,,,,Karmelava\n"
    "2,EYVI,large_airport,Vilnius International Airport,54.63,25.28,646,EU,LT,LT-VL,Vilnius,yes,EYVI,VNO,,,,\n"
    "3,EYRU,small_airport,Rukla Airfield,55.05,24.3,300,EU,LT,LT-KU,Rukla,no,EYRU,,,,,\n"
    "4,EYKL,closed,Klaipeda Airport,55.70,21.24,10,EU,LT,LT-KL,Klaipeda,no,,,,,,\n"
    "5,EVRA,large_airport,Riga International Airport,56.92,23.97,36,EU,LV,LV-RIX,Riga,yes,EVRA,RIX,,,,\n"
    "6,FZAA,large_airport,Ndjili International Airport,-4.38,15.44,1027,AF,CD,CD-KN,Kinshasa,yes,FZAA,FIH,,,,N'djili\n"
    "7,FZQM,medium_airport,Kolwezi Airport,-10.76,25.5,5007,AF,CD,CD-LU,Kolwezi,yes,FZQM,KWZ,,,,\n"
    "8,CD-0003,small_airport,Kipushi Airstrip,-11.77,27.23,4200,AF,CD,CD-HK,Kipushi,no,,,,,,\n"
)


@pytest.fixture()
def db(sadb):  # noqa: F811
    return sadb


def test_status_names_the_directory_in_use_and_never_calls_a_sample_full(db, tmp_path):
    st = ad.status(db)
    assert st["using"] == "seed" and st["using_label"] == "Bundled seed only" and st["total_records"] >= 400
    assert st["dataset"]["name"] and st["dataset"]["version"] and st["dataset"]["refreshed_at"] and "never means an airport handles cargo" in st["cargo_rule"]
    ad.load_ourairports(db, HEADER + ROWS, version="2026-10-28", refreshed_at=None)
    st = ad.status(db)
    assert st["using"] == "partial" and st["maintained_rows"] == 8 and "not the complete dataset" in st["note"]
    assert st["dataset"]["source"].startswith("OurAirports") and st["dataset"]["version"] == "2026-10-28" and st["dataset"]["refreshed_at"] is None
    assert st["total_records"] == st["maintained_rows"] + st["seed_rows"]
    # the complete file (here: generated rows, enough to cross the threshold) makes it "full"
    big = HEADER + ROWS + "".join(f"{100 + i},ZZ{i:05d},small_airport,Synthetic Test Strip {i},0,0,0,AF,CD,CD-KN,Testville,no,,,,,,\n" for i in range(ad.FULL_MIN_ROWS))
    out = ad.load_ourairports(db, big, version="2026-10-28", refreshed_at=None)
    assert out["rows"] == ad.FULL_MIN_ROWS + 8
    st = ad.status(db)
    assert st["using"] == "full" and st["total_records"] >= ad.FULL_MIN_ROWS and "Full directory in use" in st["note"]


def test_import_package_is_verified_before_loading_and_a_tampered_one_is_refused(db, tmp_path):
    m = cli.build_package(HEADER + ROWS, tmp_path / "pkg", version="2026-10-28", refreshed_at="2026-10-28T00:00:00+00:00")
    assert m["rows"] == 8 and m["with_iata"] == 5 and m["without_iata"] == 3 and m["with_icao"] == 6 and not m["complete"] and len(m["sha256"]) == 64
    text, manifest = cli.read_package(tmp_path / "pkg")
    assert text == HEADER + ROWS and manifest["licence"].startswith("Public domain")
    assert cli.main(["verify", str(tmp_path / "pkg")]) == 0
    # one row altered inside the archive: refused, nothing loaded
    with gzip.open(tmp_path / "pkg" / "airports.csv.gz", "wt", encoding="utf-8") as f:
        f.write((HEADER + ROWS).replace("Kaunas International Airport", "Kaunas Intl"))
    with pytest.raises(SystemExit, match="does not match its manifest"):
        cli.read_package(tmp_path / "pkg")
    bad = json.loads((tmp_path / "pkg" / "manifest.json").read_text())
    bad["format"] = "something-else/9"
    (tmp_path / "pkg" / "manifest.json").write_text(json.dumps(bad))
    with pytest.raises(SystemExit, match="unknown package format"):
        cli.read_package(tmp_path / "pkg")
    assert ad.status(db)["using"] == "seed"


def test_selection_by_name_city_country_iata_icao_without_iata_multiple_and_all_airports_scopes(db):
    ad.load_ourairports(db, HEADER + ROWS, version="2026-10-28")
    cl = client_for(db)
    try:
        def first(q, **kw):
            items = cl.get("/airports", params={"q": q, **kw}).json()["items"]
            return items[0] if items else None
        assert first("Kaunas International")["iata"] == "KUN"                      # name
        assert first("kolwezi")["iata"] == "KWZ"                                     # city
        assert first("KUN")["icao"] == "EYKA" and first("EYKA")["iata"] == "KUN"     # IATA, ICAO
        assert first("FZAA")["name"] == "Ndjili International Airport"
        assert first("karmelava")["iata"] == "KUN" and first("ndjili")["iata"] == "FIH"   # aliases from the dataset
        kip = first("kipushi")                                                       # no IATA, no ICAO: the dataset's own identifier
        assert kip["iata"] is None and kip["ident"] == "CD-0003" and "no IATA code" in kip["label"]
        assert first("rukla")["iata"] is None and first("rukla")["icao"] == "EYRU"
        lt = {a["ident"] for a in cl.get("/airports", params={"country": "LT", "limit": 50}).json()["items"]}
        assert {"EYKA", "EYVI", "EYRU"} <= lt and "EYKL" not in lt                    # country code; closed airports not offered
        by_name = {a["ident"] for a in cl.get("/airports", params={"q": "Lithuania", "limit": 50}).json()["items"]}
        assert {"EYKA", "EYVI", "EYRU"} <= by_name                                    # country typed by name
        assert cl.get("/airports", params={"q": "EYKL", "include_closed": "true"}).json()["items"][0]["status"] == "closed"
        assert cl.get("/airports/CD-0003").json()["name"] == "Kipushi Airstrip"
        # multiple selection, including an airport without an IATA code, across countries: discovery keeps them all
        spec = dsc.validate_spec(db, dsc.SearchSpec("worldwide", [], [], ["airline_representation"], airports=["KUN", "EYRU", "CD-0003", "FZQM"]))
        assert spec.airports == ["CD-0003", "EYKA", "EYRU", "FZQM"] and spec.countries == ["CD", "LT"]
        with pytest.raises(dsc.DiscoveryRejected, match="not in the directory"):
            dsc.validate_spec(db, dsc.SearchSpec("worldwide", [], [], [], airports=["XQZ"]))
        with pytest.raises(dsc.DiscoveryRejected, match="outside the selected countries"):
            dsc.validate_spec(db, dsc.SearchSpec("country", ["LV"], [], [], airports=["KUN"]))
        # the all-airports scopes: a country, a region or worldwide without naming airports
        assert dsc.validate_spec(db, dsc.SearchSpec("country", ["CD"], [], ["airline_representation"])).airports == []
        assert ad.scope_countries(db, countries=[], region="EU") and "LT" in ad.scope_countries(db, countries=[], region="EU")
        assert dsc.validate_spec(db, dsc.SearchSpec("worldwide", [], [], ["airline_representation"])).countries == []
        # the same multi-selection filters the Dashboard and Opportunities (nothing matches yet: no opportunity names these airports)
        assert cl.get("/dashboard", params={"airports": "KUN,CD-0003"}).status_code == 200
        assert cl.get("/records", params={"airports": "KUN,CD-0003"}).json()["total"] == 0
    finally:
        cl.__exit__(None, None, None)


def test_directory_inclusion_is_never_evidence_of_cargo_operations(db):
    org = str(db.scalar("org_insert_profile", name="Kolwezi Example Handling SARL", kind="handler", country="CD", website=None, origin="discovery", airport=None, carrier_type=None))
    before = {t: db.pg.val(f"SELECT count(*) FROM {t}") for t in ("organisation_airports", "opportunity_airports", "organisation_evidence")}
    ad.load_ourairports(db, HEADER + ROWS, version="2026-10-28")
    assert {t: db.pg.val(f"SELECT count(*) FROM {t}") for t in before} == before                   # no company or opportunity gains an airport
    assert db.pg.val(f"SELECT freight_scope FROM organisations WHERE id = '{org}'") == "unresolved"
    a = ad.resolve(db, "KWZ")
    assert a["scheduled_service"] is True and "cargo" not in json.dumps(a, default=str).lower()      # the directory holds no cargo claim


def test_a_failed_download_leaves_an_honest_status_and_readiness_is_not_proof_of_full_coverage(db, monkeypatch, capsys):
    """4.8.0 item 4: the deployment step cannot reach the publisher. The run reports the failure, exits 0 with --optional so the application
    starts, and the directory still says "Bundled seed only" — with the failed attempt recorded. /health/ready is "ready" but states that the
    full airport directory is NOT in use."""
    def no_network():
        raise OSError("CONNECT tunnel failed, response 403")
    monkeypatch.setattr(cli, "_db", lambda: db)
    monkeypatch.setattr(cli, "_download", no_network)
    assert cli.main(["load", "--auto", "--optional", "--if-stale", "30"]) == 0
    err = capsys.readouterr().err
    assert "NOT loaded" in err and "CONNECT tunnel failed" in err and "seed" in err
    st = ad.status(db)
    assert st["using"] == "seed" and st["last_attempt"]["ok"] is False and st["last_attempt"]["source"] == "download"
    assert "FAILED" in st["note"] and "CONNECT tunnel failed" in st["note"]
    assert cli.main(["load", "--download"]) == 1                                         # without --optional the failure fails the step
    cl = client_for(db)
    try:
        ready = cl.get("/health/ready").json()
        assert ready["status"] in ("ready", "degraded") and ready["airport_directory"]["full"] is False
        assert ready["airport_directory"]["using"] == "seed" and "NOT the full airport directory" in ready["airport_directory"]["note"]
        assert "FAILED" in cl.get("/airports/status").json()["note"]
    finally:
        cl.__exit__(None, None, None)
    # a later successful load (here a partial file) replaces the failure note; the status still never says "full" for a sample
    monkeypatch.setattr(cli, "_download", lambda: (HEADER + ROWS, None, "https://example.invalid/airports.csv"))
    assert cli.main(["load", "--download"]) == 0
    st = ad.status(db)
    assert st["using"] == "partial" and st["last_attempt"]["ok"] is True and "FAILED" not in st["note"]


def test_selection_reaches_airports_beyond_the_bundled_seed(db):
    from app.reference.airports import SEED
    seed_idents = {s["icao"] for s in SEED} | {s["iata"] for s in SEED}
    ad.load_ourairports(db, HEADER + ROWS, version="2026-10-28")
    beyond = [code for code in ("EYRU", "CD-0003", "FZQM") if code not in seed_idents]
    assert beyond == ["EYRU", "CD-0003", "FZQM"]                                        # none of these is in the seed
    for code in beyond:
        a = ad.resolve(db, code)
        assert a and a["source_key"] == "ourairports"
    spec = dsc.validate_spec(db, dsc.SearchSpec("countries", ["LT", "CD"], [], ["airline_representation"], airports=["EYRU", "CD-0003"]))
    assert spec.airports == ["CD-0003", "EYRU"]
