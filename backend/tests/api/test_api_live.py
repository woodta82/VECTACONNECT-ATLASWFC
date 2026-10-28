"""The real FastAPI application over the production SQLAlchemy + psycopg 3
adapter against PostgreSQL. Skipped (reported as skipped) when FastAPI or
SQLAlchemy is not installed or WFC_TEST_PG is unset."""
import io
import json

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repo.db import SQLAlchemyDatabase  # noqa: E402
from tests.sql.pg import CONN, drop_db, fresh_db  # noqa: E402

PASSWORD = "Bootstrap-Pass-2026!"


@pytest.fixture(scope="module")
def client():
    pg = fresh_db()
    parts = dict(p.split("=", 1) for p in CONN.split())  # type: ignore[union-attr]
    url = f"postgresql+psycopg://{parts.get('user', 'atlas')}@{parts.get('host', '127.0.0.1')}:{parts.get('port', '5432')}/{pg.dbname}"
    settings = config.load({"ENVIRONMENT": "test", "DATABASE_URL": url, "LOGIN_USERNAME": "ops@wfc.example",
                            "LOGIN_BOOTSTRAP_PASSWORD": PASSWORD, "BUILD_ID": "pytest"})
    db = SQLAlchemyDatabase(settings.database_url)
    app = create_app(settings, lambda: db)
    with TestClient(app) as c:   # runs startup: credential bootstrap, connector register, model versions
        c.app_ref = app  # type: ignore[attr-defined]
        c.pg = pg  # type: ignore[attr-defined]
        yield c
    db._engine.dispose()
    drop_db(pg)


def login(c) -> str:
    r = c.post("/auth/login", json={"username": "ops@wfc.example", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def test_health_reports_release_build_and_schema(client):
    live = client.get("/health/live").json()
    assert live["release"] == config.RELEASE and live["build"] == "pytest"
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["schema_revision"] == "wfc_0010"


def test_every_business_route_requires_the_session(client):
    anon = TestClient(client.app_ref)
    checked = 0
    # Enumerate from the OpenAPI document (newer FastAPI nests included routers).
    for route_path, ops in client.app_ref.openapi()["paths"].items():
        if route_path.startswith("/health") or route_path == "/auth/login":
            continue
        path = route_path.replace("{", "").replace("}", "")
        for method in ops:
            r = anon.request(method.upper(), path)
            assert r.status_code == 401, (method, route_path, r.status_code)
            assert r.headers["cache-control"] == "no-store"
            checked += 1
    assert checked >= 102                    # every business API, export and report (102 operations, 26 Oct 2026)
    for docs_path in ("/openapi.json", "/docs"):
        assert anon.get(docs_path).status_code == 401


def test_no_two_handlers_share_a_method_and_path(client):
    # A duplicate silently shadows the later handler (found once: /jobs/{id}/cancel).
    seen: dict[tuple[str, str], int] = {}
    for r in client.app_ref.routes:
        for m in getattr(r, "methods", None) or []:
            seen[(m, getattr(r, "path", ""))] = seen.get((m, getattr(r, "path", "")), 0) + 1
    assert [k for k, n in seen.items() if n > 1] == []


def test_openapi_contract_generates_behind_session(client):
    login(client)
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    doc = spec.json()
    assert doc["info"]["title"] == "VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE"
    paths = doc["paths"]
    for p in ("/opportunities", "/opportunities/{opp_id}/stage", "/imports/{dataset}/preview", "/imports/{job_id}/commit", "/lanes/{lane_id}",
              "/settings/kill-switch", "/discovery/searches", "/discovery/runs/{run_id}", "/sources", "/review", "/claims/{claim_id}/confirm",
              "/modules/account-growth", "/opportunities/{opp_id}/value", "/discovery/runs/{run_id}/results.csv"):
        assert p in paths, p
    stage = paths["/opportunities/{opp_id}/stage"]["post"]
    assert "requestBody" in stage   # body model resolved through @exact (review finding 17)


def test_get_routes_answer_with_data_or_honest_empty_states(client):
    login(client)
    for path in ["/briefing", "/opportunities", "/organisations?kind=airline", "/lanes?start=2026-10-01&end=2026-10-31",
                 "/service/exceptions", "/capabilities", "/relationships/people", "/tasks", "/network", "/reports/pipeline",
                 "/data-sources", "/settings", "/audit", "/search?q=ab",
                 "/technology/funnel?start=2026-10-01&end=2026-10-31", "/imports/templates/bookings.csv"]:
        r = client.get(path)
        assert r.status_code == 200, (path, r.text[:300])
    b = client.get("/briefing").json()
    assert {s["dataset"]: s["status"] for s in b["insight"]["sources"]}["exceptions"] == "not_connected"
    conns = {c["code"]: c["status"] for c in client.get("/data-sources").json()["connectors"]}
    assert conns["wfc_booking_system"] == "not_connected" and conns["anthropic_extraction"] == "not_connected"
    assert client.get("/settings").json()["ai_kill_switch"] is True


def _preview_commit(client, csrf, dataset, csv):
    files = {"file": (f"{dataset}.csv", io.BytesIO(csv.encode()), "text/csv")}
    pre = client.post(f"/imports/{dataset}/preview", files=files, headers={"X-CSRF-Token": csrf})
    assert pre.status_code == 200, pre.text
    com = client.post(f"/imports/{pre.json()['job_id']}/commit", headers={"X-CSRF-Token": csrf})
    assert com.status_code == 200, com.text
    return pre.json(), com.json()


def test_import_through_http_and_exact_decimals(client):
    csrf = login(client)
    # Reference data through the setup import workflow (no hand-inserted rows).
    _preview_commit(client, csrf, "operating_companies", "name,country\nWFC-UAE,AE\n")
    _preview_commit(client, csrf, "airports", "iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\n"
                                              "NBO,Jomo Kenyatta International,KE,Africa/Nairobi\n")
    csv = ("external_id,origin,destination,flight_date,booked_at,status,chargeable_weight,actual_weight,volume,revenue,currency,operating_company\n"
           "H-1,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,confirmed,1000.5,900,6.1,2500.10,USD,WFC-UAE\n"
           "H-2,DXB,DXB,2026-10-05,2026-10-01T09:00:00+04:00,confirmed,1,1,1,1,USD,WFC-UAE\n")
    files = {"file": ("b.csv", io.BytesIO(csv.encode()), "text/csv")}
    pre = client.post("/imports/bookings/preview", files=files, headers={"X-CSRF-Token": csrf})
    assert pre.status_code == 200, pre.text
    assert pre.json()["planned"]["insert"] == 1 and pre.json()["reconciliation"]["rows_quarantined"] == 1
    assert client.post(f"/imports/{pre.json()['job_id']}/commit").status_code == 403          # CSRF required
    com = client.post(f"/imports/{pre.json()['job_id']}/commit", headers={"X-CSRF-Token": csrf})
    assert com.status_code == 200, com.text
    assert com.json()["partial"] is True and "quarantined" in com.json()["partial_note"]
    again = client.post(f"/imports/{pre.json()['job_id']}/commit", headers={"X-CSRF-Token": csrf})
    assert again.status_code == 409                                                        # a preview commits once
    lanes = client.get("/lanes?start=2026-10-01&end=2026-10-31").json()["items"]
    lane = next(lane for lane in lanes if lane["origin"] == "DXB")
    assert lane["chargeable_kg"] == "1000.500"           # exact decimal string, not a float
    detail = client.get(f"/lanes/{lane['id']}?start=2026-10-01&end=2026-10-31").json()
    assert detail["utilisation"]["value"] is None and "no capacity" in detail["utilisation"]["reason"]
    assert detail["revenue"]["by_currency"] == {"USD": "2500.1000"}
    job = client.get(f"/imports/{com.json()['job_id']}").json()
    assert job["job"]["preview_job_id"] == pre.json()["job_id"] and len(job["errors"]) == 1


def test_new_workflow_routes_answer(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    for path in ["/discovery/options", "/discovery/searches", "/discovery/runs", "/sources", "/schedules", "/jobs", "/review",
                 "/modules/summary", "/modules/account-growth", "/modules/forwarder-sales", "/modules/capacity-lanes?start=2026-10-01&end=2026-10-31",
                 "/modules/trucking", "/modules/outsourcing-training", "/modules/technology?start=2026-10-01&end=2026-10-31",
                 "/settings/prioritisation", "/reference/geography", "/reference/lookups", "/referrals",
                 "/opportunities?countries=KE", "/briefing?region=GCC", "/reports/pipeline?countries=AE,KE"]:
        r = client.get(path)
        assert r.status_code == 200, (path, r.text[:300])
    assert client.get("/opportunities?countries=XX").status_code == 422
    assert client.get("/modules/account-growth").json()["status"] == "not_connected"
    src = client.post("/sources", json={"name": "Example portal", "source_type": "listing", "base_url": "https://portal.example/tenders/",
                                        "authority": "official_portal", "country_coverage": ["KE"], "refresh_minutes": 60}, headers=h)
    assert src.status_code == 200, src.text
    sid = src.json()["id"]
    assert client.get(f"/sources/{sid}").json()["schedule"] is not None                    # refresh frequency is a real schedule
    bad = client.post("/sources", json={"name": "Bad", "source_type": "search_template", "base_url": "https://portal.example/",
                                        "authority": "official_portal"}, headers=h)
    assert bad.status_code == 422
    run = client.post("/discovery/searches", json={"geo_mode": "country", "countries": ["KE"], "modules": ["airline_representation"]}, headers=h)
    assert run.status_code == 200, run.text
    plan = run.json()["run"]["plan"]
    assert plan["sources"] == [] and plan["coverage_gaps"] == ["KE"]                      # source disabled: nothing searched, said so
    assert client.post("/discovery/searches", json={"geo_mode": "country", "countries": ["KE", "UG"]}, headers=h).status_code == 422
    rid = run.json()["run"]["run_id"]
    assert client.post(f"/discovery/runs/{rid}/cancel", headers=h).status_code == 200
    assert client.get(f"/discovery/runs/{rid}").json()["run"]["status"] == "cancelled"
    assert client.get(f"/discovery/runs/{rid}/results.csv").status_code == 200


def test_export_is_formula_safe_and_audited(client):
    login(client)
    client.pg.run("INSERT INTO opportunities (module, dedup_key, title) VALUES ('network_development','x1','=HYPERLINK(\"http://evil\")')")
    r = client.get("/reports/opportunities.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.splitlines()
    assert lines[0] == "VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE"
    assert any(line.count("'=HYPERLINK") == 1 for line in lines)
    assert client.pg.val("SELECT count(*) FROM audit_events WHERE event_type='export' AND entity_id='opportunities.csv'") == "1"


def test_kill_switch_budget_and_validation_errors(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    assert client.post("/settings/kill-switch", json={"enabled": False}, headers=h).json() == {"ai_kill_switch": False}
    assert client.get("/settings").json()["ai_kill_switch"] is False
    assert client.post("/settings/kill-switch", json={"enabled": True}, headers=h).status_code == 200
    assert client.post("/settings/budget", json={"cap_usd": "50.00", "warn_at_usd": "40", "per_run_cap_usd": "2.5"}, headers=h).status_code == 200
    assert client.get("/settings").json()["budget"]["cap_usd"] == "50.0000"
    bad = client.post("/opportunities/00000000-0000-0000-0000-000000000000/stage", json={"to": "won"}, headers=h)
    assert bad.status_code == 422                                     # reason missing
    nf = client.post("/opportunities/00000000-0000-0000-0000-000000000000/stage", json={"to": "won", "reason": "test"}, headers=h)
    assert nf.status_code == 404
    assert client.get("/opportunities/00000000-0000-0000-0000-000000000000").status_code == 404


def test_logout_all_over_http(client):
    a, b = TestClient(client.app_ref), TestClient(client.app_ref)
    ta = login(a)
    login(b)
    assert a.post("/auth/logout-all", headers={"X-CSRF-Token": ta}).status_code == 200
    assert b.get("/briefing").status_code == 401
    assert json.loads(a.get("/briefing").text)["error"]["code"] == "unauthenticated"


def test_evidence_passage_is_inspectable_by_recorded_location(client):
    login(client)
    body = "Request for Proposal. " + ("General conditions apply to all bidders. " * 40) + \
           "Applicants based in Kenya must hold a licence if operating in France. Proposals are due on 30 November 2026."
    h = "a" * 64
    client.pg.run("INSERT INTO source_documents (id, original_url, canonical_url, content_hash, retrieved_at, body_text, excerpt, parser_version, "  # type: ignore[attr-defined]
                  "extraction_status) VALUES ('22222222-2222-2222-2222-222222222222', 'https://portal.example/rfp/1', 'https://portal.example/rfp/1', "
                  "'" + h + "', now(), $q$" + body + "$q$, 'Request for Proposal.', 'test', 'extracted')")
    quote = "Applicants based in Kenya must hold a licence if operating in France."
    a = body.index(quote)
    r = client.get(f"/documents/22222222-2222-2222-2222-222222222222/passage?quote={quote}&location=chars {a}-{a + len(quote)}&context=30")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["found"] and p["how"] == "recorded location" and p["passage"] == quote and p["document_version"] == h
    assert p["start"] == a and p["before"].endswith("bidders. ") and p["after"].startswith(" Proposals")
    # A stale location is not trusted: the quote is searched for instead.
    r2 = client.get(f"/documents/22222222-2222-2222-2222-222222222222/passage?quote={quote}&location=chars 0-10")
    assert r2.json()["found"] and r2.json()["how"] == "found in the text" and r2.json()["start"] == a
    # A quote that is not in the current text version is reported, never shown as found.
    r3 = client.get("/documents/22222222-2222-2222-2222-222222222222/passage?quote=Applicants based in France must hold a licence")
    assert r3.json()["found"] is False and "not found" in r3.json()["detail"]
