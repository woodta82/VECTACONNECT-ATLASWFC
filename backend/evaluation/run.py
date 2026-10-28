"""Run the evaluation set through the production pipeline and measure it.

    WFC_TEST_PG="host=127.0.0.1 port=5433 user=atlas" python -m evaluation.run --split all --out ../evidence/evaluation

Each case runs on a fresh PostgreSQL database built from the migrations, through the real discovery executor, ingestion,
validation, identity, signal evaluation and qualification, with two things injected at the edges:
- a synthetic fetcher serving the case's document (HTML, HTML table or PDF) from a listing page;
- a SCRIPTED extractor transport that returns the case's proposals for whichever section of the document it is shown
  (the proposals include wrong readings a model could produce). No AI provider is called: these numbers measure the
  validation, identity, deadline, contradiction and coverage logic, not a model's extraction.

Measured per case and aggregated by split, category, language and capability area:
- opportunity precision and recall against the gold opportunities (matched by tender reference);
- field accuracy of the resulting opportunities (status, deadline day, deadline precision, service);
- false 'supported' decisions: proposed field values the gold says the notice does NOT state, that the validator
  nevertheless labelled 'supported' (and missed supported: gold-true values not labelled supported);
- incomplete-document coverage: long documents must be marked incomplete while unread and complete afterwards.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.domain import eligibility  # noqa: E402
from app.domain.identity import norm_ref  # noqa: E402
from app.services import discovery as dsc  # noqa: E402
from app.services import sources_service as srcs  # noqa: E402
from app.services.audit import RequestMeta  # noqa: E402
from evaluation.genuine import genuine_cases  # noqa: E402
from evaluation.heldout3 import heldout3_cases  # noqa: E402
from evaluation.heldout4 import heldout4_cases  # noqa: E402
from evaluation.heldout5 import heldout5_cases  # noqa: E402
from evaluation.heldout6 import heldout6_cases  # noqa: E402
from evaluation.heldout7 import heldout7_cases  # noqa: E402
from evaluation.notices import Case, cases  # noqa: E402
from tests.integration.sa import url_for  # noqa: E402
from tests.integration.test_review3_regressions import Web, _listing  # noqa: E402
from tests.sql.pg import _base_args, drop_db, fresh_db  # noqa: E402


def sql_rows(dbname: str, sql: str) -> list[list[str]]:
    """Ad-hoc read for the harness: psql with a separator that cannot occur in the data (unit separator)."""
    import subprocess

    res = subprocess.run(_base_args(dbname) + ["-F", "\x1f", "-c", sql], capture_output=True, text=True, check=True)
    out = res.stdout.strip()
    return [line.split("\x1f") for line in out.splitlines()] if out else []

BASE = "https://notices.example"
META = RequestMeta(ip="127.0.0.1", request_id="eval", session_ref="evaluation00")
SETTINGS = config.load({"ENVIRONMENT": "test", "DATABASE_URL": "postgresql://x@y/z", "ANTHROPIC_API_KEY": "scripted-not-real",
                        "AI_MODEL": "scripted-extractor", "AI_PRICE_INPUT_PER_MTOK": "3", "AI_PRICE_OUTPUT_PER_MTOK": "15",
                        "AI_API_BASE_URL": "http://127.0.0.1:9"})
NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
EXTRACTOR = "scripted"   # or "configured": the AI extractor named by the environment (ANTHROPIC_API_KEY, AI_MODEL, AI_API_BASE_URL)


def configured_settings() -> config.Settings:
    """Settings for the configured AI extractor, taken from the environment; fails plainly when the key is missing."""
    env = dict(os.environ)
    env.setdefault("ENVIRONMENT", "test")
    env.setdefault("DATABASE_URL", "postgresql://x@y/z")
    missing = [k for k in ("ANTHROPIC_API_KEY", "AI_MODEL") if not env.get(k, "").strip()]
    if missing:
        raise SystemExit(f"[eval] --extractor configured needs {', '.join(missing)} in the environment; nothing was run")
    return config.load(env)


# ---------------------------------------------------------------- documents
def html_doc(c: Case) -> bytes:
    meta = f'<meta property="article:published_time" content="{c.published}">' if c.published else ""
    body = "".join(f"<p>{p}</p>" for p in c.body.split("\n\n"))
    if c.content_type == "html-table" and c.table_rows:
        head = "".join(f"<th>{h}</th>" for h in c.table_rows[0])
        rows = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in c.table_rows[1:])
        body += f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    return (f"<!doctype html><html lang='{c.language}'><head><title>{c.title}</title>{meta}</head><body><main><h1>{c.title}</h1>{body}</main>"
            f"</body></html>").encode()


def _pdf_date(value: str) -> str:
    d = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return d.strftime("D:%Y%m%d%H%M%SZ")


def pdf_doc(c: Case, *, title: str | None = None, body: str | None = None, created: str | None = None) -> bytes:
    """A PDF notice. Its document-information creation date is the notice's issue date (`created`; None = no date in the
    metadata at all), as a published PDF carries it; reportlab's own build-time stamp is not kept."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    title = title if title is not None else c.title
    body = body if body is not None else c.body
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    flow: list[Any] = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for p in body.split("\n\n"):
        flow += [Paragraph(p.replace("&", "&amp;").replace("<", "&lt;"), styles["Normal"]), Spacer(1, 6)]
    doc.build(flow)
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(buf.getvalue())))
    meta = {"/Title": title}
    if created:
        meta["/CreationDate"] = _pdf_date(created)
    writer.add_metadata(meta)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def document(c: Case) -> tuple[bytes, str]:
    if c.content_type == "pdf":
        return pdf_doc(c, created=c.extra.get("pdf_created", c.published)), "application/pdf"
    return html_doc(c), "text/html"


def extra_document(c: Case, d: dict[str, Any]) -> tuple[bytes, str]:
    if d.get("content_type") == "pdf":
        return pdf_doc(c, title=d["title"], body=d["body"], created=d.get("pdf_created", d.get("published"))), "application/pdf"
    view = Case(c.id, c.split, c.language, c.module, c.search, c.coverage, c.categories, "html", d["title"], d["body"], [], {},
                published=d.get("published"))
    return html_doc(view), "text/html"


# ---------------------------------------------------------------- scripted extractor
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def transport_for(c: Case, calls: list[str]):
    if EXTRACTOR == "configured":
        from app.ai.extraction import messages_api

        def real(settings, system, user):
            calls.append(user)
            return messages_api(settings, system, user)
        return real

    def transport(_settings, _system, user):
        calls.append(user)
        doc = user.split("<document>\n", 1)[-1].split("\n</document>", 1)[0]
        nd = _norm(doc)
        out = []
        for p in c.proposals:
            if _norm(p["quote"]) in nd:
                q = {k: v for k, v in p.items() if k != "gold"}
                out.append(q)
        return json.dumps({"language": c.language, "claims": out}), None, None
    return transport


NOTICE_TYPES = (("cancellation", "cancellation / withdrawal notice"), ("award", "award / appointment notice"), ("amendment", "corrigendum / amendment"),
                ("expression_of_interest", "expression of interest"), ("trade_press", "trade press item"), ("table", "tender listing (table)"),
                ("not_procurement", "non-procurement notice"), ("capacity", "route / capacity announcement"), ("partnership", "partnership announcement"),
                ("pdf", "RFP / tender document (PDF)"))


def notice_type(c: Case) -> str:
    for key, label in NOTICE_TYPES:
        if key in c.categories:
            return label
    return "RFP / tender page (HTML)"


# ---------------------------------------------------------------- one case
def run_case(c: Case) -> dict[str, Any]:
    pg = fresh_db()
    from app.repo.db import SQLAlchemyDatabase

    db = SQLAlchemyDatabase(url_for(pg))
    db.pg = pg  # type: ignore[attr-defined]
    result: dict[str, Any] = {"id": c.id, "split": c.split, "language": c.language, "module": c.module, "categories": c.categories,
                              "search_mode": c.search["geo_mode"], "content_type": c.content_type, "notes": c.notes, "notice_type": notice_type(c)}
    try:
        db.run("flag_set", key="ai_kill_switch", value="false")
        db.run("budget_set", cap="50.00", warn="40.00", per_run="0.25" if c.long else "10.00")
        body, ctype = document(c)
        url = f"{BASE}/{c.id}/notice"
        pages: dict[str, Any] = {url: (body, ctype)}
        urls = [url]
        for i, d in enumerate(c.documents, start=2):
            u = f"{BASE}/{c.id}/notice-{i}"
            pages[u] = extra_document(c, d)
            urls.append(u)
        web = Web({f"{BASE}/{c.id}/": _listing(urls), **pages})
        srcs.create_source(db, srcs.SourceSpec("Evaluation source", "listing", f"{BASE}/{c.id}/", "official_portal",
                                               country_coverage=c.coverage, global_coverage=c.search["geo_mode"] == "worldwide",
                                               language=c.language, local_language_permitted=True, retention_permitted=True, enabled=True), META)
        spec = dsc.SearchSpec(c.search["geo_mode"], c.search.get("countries", []), c.search.get("regions", []), [])
        sid = dsc.create_search(db, spec)
        calls: list[str] = []
        runs = []
        started = dsc.start_run(db, SETTINGS, search_id=sid)
        dsc.execute_run(db, SETTINGS, started["run_id"], None, fetch=web, transport=transport_for(c, calls), now=NOW)
        runs.append(db.one("run_get", id=started["run_id"]))
        docs = db.all("review_documents", limit=50)
        first_doc = sql_rows(pg.dbname, "SELECT extraction_status, coalesce(read_progress::text, '') FROM source_documents")
        result["first_run"] = {"status": runs[0]["status"], "outcome": runs[0]["outcome"], "calls": len(calls),
                               "documents": [{"status": r[0], "progress": json.loads(r[1]) if r[1] else None} for r in first_doc]}
        if c.long:
            # the first run must stop short and say so; then the ceiling is raised and the next run of the same search resumes
            db.run("budget_set", cap="50.00", warn="40.00", per_run="10.00")
            started2 = dsc.start_run(db, SETTINGS, search_id=sid)
            dsc.execute_run(db, SETTINGS, started2["run_id"], None, fetch=web, transport=transport_for(c, calls), now=NOW)
            runs.append(db.one("run_get", id=started2["run_id"]))
        final_docs = sql_rows(pg.dbname, "SELECT extraction_status, coalesce(read_progress::text, ''), status_contradiction IS NOT NULL FROM source_documents")
        result["final"] = {"runs": [{"status": r["status"], "outcome": r["outcome"]} for r in runs], "calls": len(calls),
                           "documents": [{"status": r[0], "progress": json.loads(r[1]) if r[1] else None, "contradictory": r[2] == "t"} for r in final_docs]}
        del docs
        # opportunities found
        found = []
        for r in sql_rows(pg.dbname, "SELECT o.id::text, coalesce(s.tender_ref, ''), o.title, coalesce(o.tender_status, ''), coalesce(o.deadline_info::text, ''), "
                            "coalesce(sv.code, ''), o.module, coalesce((s.tender_state->>'deadline_conflict'), ''), coalesce(o.freight_scope, ''), "
                            "coalesce(o.tender_status_basis, ''), "
                            "coalesce((SELECT string_agg(regexp_replace(ce.excerpt, '[\\r\\n]+', ' ', 'g'), chr(2)) FROM signal_claims sc JOIN claim_evidence ce ON ce.claim_id = sc.claim_id "
                            "WHERE sc.signal_id = o.signal_id), '') FROM opportunities o "
                            "LEFT JOIN services sv ON sv.id = o.service_id LEFT JOIN signals s ON s.id = o.signal_id"):
            info = json.loads(r[4]) if r[4] else None
            found.append({"id": r[0], "ref": r[1], "title": r[2], "status": r[3], "deadline_day": info.get("day") if info else None,
                          "deadline_precision": info.get("precision") if info else None, "service": r[5], "module": r[6],
                          "deadline_conflict": r[7] not in ("", "false", "null"), "freight_scope": r[8], "status_basis": r[9],
                          "evidence": [x for x in r[10].split("\x02") if x]})
        result["found"] = found
        # signals: module, classification, effective status, freight scope, its reason, title, tender reference, evidence excerpts
        result["signals"] = sql_rows(pg.dbname, "SELECT module, classification, coalesce(tender_state->>'status', ''), coalesce(freight_scope, ''), "
                                     "coalesce(freight_scope_reason, ''), title, coalesce(tender_ref, ''), "
                                     "coalesce((SELECT string_agg(regexp_replace(ce.excerpt, '[\\r\\n]+', ' ', 'g'), chr(2)) FROM signal_claims sc JOIN claim_evidence ce ON ce.claim_id = sc.claim_id "
                                     "WHERE sc.signal_id = signals.id), '') FROM signals")
        # publication dates as recorded (schema-tolerant: columns added by later revisions read as empty when absent)
        result["document_dates"] = sql_rows(pg.dbname, "SELECT canonical_url, coalesce(published_at::text, ''), coalesce(to_jsonb(d)->>'published_at_source', ''), "
                                            "coalesce(to_jsonb(d)->>'publication_flag', '') FROM source_documents d ORDER BY canonical_url")
        result["geography_conflicts"] = [r[0] for r in sql_rows(pg.dbname, "SELECT geography_conflict FROM source_documents WHERE geography_conflict IS NOT NULL")]
        result["rejections"] = sql_rows(pg.dbname, "SELECT reason, left(raw::text, 160) FROM extraction_rejections ORDER BY created_at")
        result["claims"] = sql_rows(pg.dbname, "SELECT c.claim_type, c.status, c.review_status, left(ce.excerpt, 80) FROM claims c "
                                      "JOIN claim_evidence ce ON ce.claim_id = c.id ORDER BY c.created_at")
        # field assessments, matched to the proposals
        rows = sql_rows(pg.dbname, "SELECT c.claim_type, ce.excerpt, cf.field, cf.value, cf.support, cf.reason FROM claim_fields cf "
                          "JOIN claims c ON c.id = cf.claim_id JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.source_document_id = cf.source_document_id "
                          "WHERE cf.superseded_at IS NULL")
        assessed: dict[tuple[str, str, str, str], tuple[str, str]] = {}
        for ct, quote, fld, value, support, reason in rows:
            assessed[(ct, _norm(quote), fld, _norm(value))] = (support, reason)
        fields = []
        for i, p in enumerate(c.proposals):
            for name, gold in p["gold"].items():
                key = (p["claim_type"], _norm(p["quote"]), name, _norm(p["fields"][name]["value"]))
                got = assessed.get(key)
                fields.append({"proposal": i, "claim_type": p["claim_type"], "field": name, "value": p["fields"][name]["value"], "gold_supported": gold,
                               "support": got[0] if got else "not_assessed", "reason": got[1] if got else "the proposal did not reach validation "
                               "(not in a read section, or rejected before field validation)"})
        result["fields"] = fields
        result["gold_opportunities"] = c.gold["opportunities"]
        result["gold_excluded"] = c.gold.get("excluded") or []
        result["metrics"] = measure(c, result)
    finally:
        db._engine.dispose()
        drop_db(pg)
    return result


# ---------------------------------------------------------------- metrics
def _split(joined: str) -> list[str]:
    return [x for x in (joined or "").split("\x02") if x]


def _excluded_matches(g: dict[str, Any], ref: str | None, title: str | None, evidence: list[str], *, unnamed: bool = False) -> bool:
    """Whether a record is the one an excluded gold entry names: by reference, else by its evidence passage, else (labels
    written before 27 Oct, fourth instruction) by the title text. An entry that names nothing (one excluded record per case)
    matches any record of its scope when `unnamed` is True (finding it), and none when False (counting leaks)."""
    if g.get("ref"):
        return bool(ref) and norm_ref(ref) == norm_ref(g["ref"])
    if g.get("quote"):
        q = _norm(g["quote"])
        return any(q in _norm(e) or _norm(e) in q for e in evidence if e)
    if g.get("title_contains"):
        return g["title_contains"].lower() in (title or "").lower()
    return unnamed


def measure(c: Case, r: dict[str, Any]) -> dict[str, Any]:
    gold = c.gold["opportunities"]
    found = r["found"]
    gold_refs = {norm_ref(g["ref"]) for g in gold if g["ref"]}
    found_refs = {norm_ref(o["ref"]) for o in found if o["ref"]}
    matched = gold_refs & found_refs
    # Gold opportunities without a reference are matched by title (one found record per gold, in order).
    title_gold = [g for g in gold if not g["ref"] and g.get("title_contains")]
    used: set[str] = set()
    title_matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for g in title_gold:
        cand = next((o for o in found if o["id"] not in used and not (o["ref"] and norm_ref(o["ref"]) in gold_refs)
                     and g["title_contains"].lower() in (o["title"] or "").lower()
                     and (g["service"] is None or o["service"] == g["service"] or len(title_gold) == 1)), None)
        if cand:
            used.add(cand["id"])
            title_matched.append((g, cand))
    unmatched_found = [o for o in found if o["id"] not in used and (not o["ref"] or norm_ref(o["ref"]) not in gold_refs)]
    tp = len(matched) + len(title_matched)
    m: dict[str, Any] = {"opportunities_gold": len(gold), "opportunities_found": len(found), "opportunities_matched": tp,
                         "false_opportunities": len(unmatched_found),
                         "missed_opportunities": sorted(gold_refs - found_refs) + [g["title_contains"] for g in title_gold if g not in [x for x, _ in title_matched]]}
    # field accuracy on matched opportunities
    checks = {"status": [0, 0], "deadline_day": [0, 0], "deadline_precision": [0, 0], "service": [0, 0], "freight_scope": [0, 0]}
    pairs = [(g, next(x for x in found if x["ref"] and norm_ref(x["ref"]) == norm_ref(g["ref"]))) for g in gold if g["ref"] and norm_ref(g["ref"]) in matched]
    pairs += title_matched
    for g, o in pairs:
        for k in checks:
            exp = g.get(k)
            if k == "freight_scope" and exp is None:
                continue                       # the gold does not assert the freight reading
            if k in ("deadline_day", "deadline_precision") and g["status"] in ("cancelled", "awarded", "closed") and exp is None:
                continue                       # a terminal record may keep the deadline it once stated; the gold does not assert it
            got = o[k]
            if k in ("deadline_day", "deadline_precision") and c.gold.get("deadline_conflict"):
                # a conflict must be shown, not resolved by picking one date
                ok = o["deadline_conflict"] or got in (None, "")
            else:
                ok = (got or None) == (exp or None)
            checks[k][1] += 1
            checks[k][0] += int(bool(ok))
    m["field_accuracy"] = {k: {"correct": v[0], "total": v[1]} for k, v in checks.items()}
    # Field completeness: of the record fields the gold says a matched opportunity should carry (a stated deadline, its precision,
    # the service, the freight scope), how many the record has at all (right or wrong). Accuracy above says how many are right.
    comp = [0, 0]
    for g, o in pairs:
        for k in ("deadline_day", "deadline_precision", "service", "freight_scope"):
            if g.get(k):
                comp[1] += 1
                comp[0] += int(bool(o.get(k)))
    m["completeness"] = {"present": comp[0], "expected": comp[1]}
    # false / missed supported
    fs = [x for x in r["fields"] if not x["gold_supported"] and x["support"] == "supported"]
    # A proposal with a wrong field that was rejected as a whole is a correct rejection: its other fields are not "missed".
    wrong_proposals = {x["proposal"] for x in r["fields"] if not x["gold_supported"]}
    ms = [x for x in r["fields"] if x["gold_supported"] and x["support"] != "supported"
          and not (x["support"] == "not_assessed" and x["proposal"] in wrong_proposals)]
    m["fields_assessed"] = len(r["fields"])
    m["false_supported"] = len(fs)
    m["false_supported_detail"] = [f"{x['claim_type']}.{x['field']} = {x['value']!r}" for x in fs]
    m["missed_supported"] = len(ms)
    m["missed_supported_detail"] = [f"{x['claim_type']}.{x['field']} = {x['value']!r}: {x['support']} ({x['reason'][:120]})" for x in ms]
    # coverage
    docs_first = r["first_run"]["documents"]
    docs_final = r["final"]["documents"]
    # Complete coverage: every document fully read ('partial' = fully read with some proposals rejected, which is complete reading).
    complete_final = all(d["status"] in ("extracted", "no_claims", "partial") and (d["progress"] is None or len(set(d["progress"]["done"])) >= d["progress"]["total"])
                         for d in docs_final)
    m["coverage"] = {"documents": len(docs_final), "complete_after_final_run": complete_final,
                     "first_run_status": r["first_run"]["status"], "first_run_outcome": r["first_run"]["outcome"]}
    if c.long:
        first_incomplete = any(d["status"] == "incomplete" for d in docs_first) and r["first_run"]["status"] == "partial"
        m["coverage"]["long_first_run_marked_incomplete"] = first_incomplete
        m["coverage"]["long_resumed_to_complete"] = complete_final
    if c.gold.get("contradictory_document"):
        m["contradiction_flagged"] = any(d["contradictory"] for d in docs_final)
    # Freight relevance (27 Oct, second instruction): records the gold EXCLUDES must appear as excluded signals, never as opportunities.
    excluded_gold = c.gold.get("excluded") or []
    if excluded_gold:
        # Matching by IDENTITY (27 Oct 2026, fourth instruction, item 5): an excluded record is the signal or opportunity with the
        # same tender/lot reference, or (no reference) the one whose evidence is the excluded passage. An airline name shared by a
        # passenger lot and a cargo lot never matches one to the other. Labels written before this change name only the airline
        # (`title_contains`); for those a record counts only if it is not itself matched to a gold opportunity.
        found_ex = [s_ for s_ in r["signals"] if s_[1] == "excluded"]
        gold_opp_ids = {o["id"] for o in found if o["ref"] and norm_ref(o["ref"]) in gold_refs} | used
        m["excluded_expected"] = len(excluded_gold)
        m["excluded_found"] = sum(1 for g in excluded_gold if any(s_[3] == g["scope"] and _excluded_matches(g, s_[6], s_[5], _split(s_[7]), unnamed=True)
                                                               for s_ in found_ex))
        m["excluded_leaked"] = sum(1 for g in excluded_gold if any(o["id"] not in gold_opp_ids and _excluded_matches(g, o["ref"], o["title"], o["evidence"])
                                                                   for o in found))
    # Relevance accuracy: every freight-relevance judgement the gold makes — a matched opportunity's freight scope, and each record the
    # gold excludes — compared with what the pipeline concluded. An unmatched gold opportunity with a scope counts as wrong.
    rel = [0, 0]
    matched_gold = {id(g) for g, _o in pairs}
    for g, o in pairs:
        if g.get("freight_scope"):
            rel[1] += 1
            rel[0] += int(o.get("freight_scope") == g["freight_scope"])
    for g in gold:
        if g.get("freight_scope") and id(g) not in matched_gold:
            rel[1] += 1
    if excluded_gold:
        rel[1] += len(excluded_gold)
        rel[0] += m["excluded_found"]
    m["relevance"] = {"correct": rel[0], "total": rel[1]}
    # Actionable-opportunity accuracy (27 Oct 2026, fifth instruction, item 4): only LIVE records (open or revised) count.
    live = ("open", "revised")
    found_live = {norm_ref(o["ref"]) for o in found if o["ref"] and o["status"] in live}
    # matched as for opportunities (by reference, or by title for a gold opportunity without one); both sides must be live
    m["actionable"] = {"gold": sum(1 for g in gold if g["status"] in live), "found": sum(1 for o in found if o["status"] in live),
                       "matched": sum(1 for g, o in pairs if g["status"] in live and o["status"] in live)}
    # Historical-record retention: terminal notices (cancellation, award, closure) the gold expects to be KEPT as intelligence
    # (a tender record with that terminal status), never live. Matched by reference.
    hist = c.gold.get("historical") or []
    if hist:
        sig_status = {}
        for s_ in r["signals"]:
            if len(s_) > 6 and s_[6]:
                sig_status.setdefault(norm_ref(s_[6]), set()).add(s_[2])
        m["historical"] = {"expected": len(hist),
                           "retained": sum(1 for h in hist if h["status"] in sig_status.get(norm_ref(h["ref"]), set())),
                           "live": sum(1 for h in hist if norm_ref(h["ref"]) in found_live)}
    if "geography_conflict" in c.gold:
        m["geography_conflict_expected"] = bool(c.gold["geography_conflict"])
        m["geography_conflict_flagged"] = bool(r.get("geography_conflicts"))
    if c.gold.get("signal_expected"):
        m["signal_module_expected"] = c.gold["signal_expected"]
        m["signal_modules_found"] = sorted({s[0] for s in r["signals"]})
    if "publication_flag" in c.gold:
        # the publication-date flag the gold expects on the case's documents ('future', 'inconsistent' or None)
        m["publication_flag_expected"] = c.gold["publication_flag"]
        # psql drops a trailing empty column, so a row may be short: a missing flag column is no flag
        m["publication_flags_found"] = sorted({d[3] for d in r.get("document_dates", []) if len(d) > 3 and d[3]})
    return m


# ---------------------------------------------------------------- aggregation and report
def aggregate(results: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        vals = r[key] if isinstance(r[key], list) else [r[key]]
        for v in vals:
            groups[str(v)].append(r)
    out = {}
    for g, rs in sorted(groups.items()):
        gold = sum(x["metrics"]["opportunities_gold"] for x in rs)
        found = sum(x["metrics"]["opportunities_found"] for x in rs)
        tp = sum(x["metrics"]["opportunities_matched"] for x in rs)
        fa_c = sum(v["correct"] for x in rs for v in x["metrics"]["field_accuracy"].values())
        fa_t = sum(v["total"] for x in rs for v in x["metrics"]["field_accuracy"].values())
        neg = sum(1 for x in rs for f in x["fields"] if not f["gold_supported"])
        pos = sum(1 for x in rs for f in x["fields"] if f["gold_supported"])
        out[g] = {"cases": len(rs), "opportunities": {"gold": gold, "found": found, "matched": tp,
                                                       "precision": round(tp / found, 3) if found else None, "recall": round(tp / gold, 3) if gold else None},
                  "field_accuracy": {"correct": fa_c, "total": fa_t, "rate": round(fa_c / fa_t, 3) if fa_t else None},
                  "false_supported": {"count": sum(x["metrics"]["false_supported"] for x in rs), "of_gold_negative": neg},
                  "missed_supported": {"count": sum(x["metrics"]["missed_supported"] for x in rs), "of_gold_positive": pos},
                  "coverage": {"complete": sum(1 for x in rs if x["metrics"]["coverage"]["complete_after_final_run"]), "cases": len(rs)},
                  "excluded": {"expected": sum(x["metrics"].get("excluded_expected", 0) for x in rs),
                               "found": sum(x["metrics"].get("excluded_found", 0) for x in rs),
                               "leaked": sum(x["metrics"].get("excluded_leaked", 0) for x in rs)},
                  "relevance": {"correct": sum(x["metrics"].get("relevance", {}).get("correct", 0) for x in rs),
                                "total": sum(x["metrics"].get("relevance", {}).get("total", 0) for x in rs)},
                  "actionable": {k: sum(x["metrics"].get("actionable", {}).get(k, 0) for x in rs) for k in ("gold", "found", "matched")},
                  "historical": {k: sum(x["metrics"].get("historical", {}).get(k, 0) for x in rs) for k in ("expected", "retained", "live")},
                  "completeness": {"present": sum(x["metrics"].get("completeness", {}).get("present", 0) for x in rs),
                                   "expected": sum(x["metrics"].get("completeness", {}).get("expected", 0) for x in rs)},
                  "geography_conflicts": {"expected": sum(1 for x in rs if x["metrics"].get("geography_conflict_expected")),
                                          "flagged": sum(1 for x in rs if x["metrics"].get("geography_conflict_expected") and x["metrics"].get("geography_conflict_flagged")),
                                          "false": sum(1 for x in rs if "geography_conflict_expected" in x["metrics"] and not x["metrics"]["geography_conflict_expected"]
                                                       and x["metrics"].get("geography_conflict_flagged"))}}
    return out


def c_gold(r: dict[str, Any]) -> list[dict[str, Any]]:
    return r.get("gold_opportunities") or []


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else f"{n}/0 (n/a)"


def _provenance(split: str) -> list[str]:
    extractor = ("The extractor is SCRIPTED (it returns the case's proposals, correct and incorrect readings alike); no AI provider was called."
                 if EXTRACTOR == "scripted" else
                 f"The extractor is the CONFIGURED AI extractor ({SETTINGS.ai_model}); every call went to the provider and was charged to the run budget.")
    if split == "genuine":
        return ["**Provenance.** Every notice in this set is a GENUINE public notice, captured on the date recorded in "
                "`backend/evaluation/genuine_sources/` through the build session's web-fetch tool, which returns verbatim quotes and "
                "paraphrased structure: each document is therefore a RECONSTRUCTION of the notice in its original form (PDF, HTML page, "
                "table), not the original bytes. Expected results were checked by a person against the captured text. " + extractor +
                " These numbers measure the pipeline on real wording; the sample is small and they are not market coverage.", "",
                "**Protocol.** This set was not used for tuning. Run 1 found one safety bug (a reserved right to annul read as a cancellation), "
                "fixed with regression tests; run 2 is the reported result. Remaining failures are listed as findings in `BUILD_REPORT.md`.", ""]
    if split == "heldout7":
        return ["**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices. "
                "None is a genuine notice. " + extractor + " These numbers measure the status-chronology, terminal-record and contextual-evidence "
                "logic on authored notices (several documents per case); they are not real-world extraction quality.", "",
                "**Held-out protocol.** The `heldout7` cases were written on 27 Oct 2026 (fifth instruction) BEFORE any rule of that instruction "
                "was changed, and run once at the end; no rule was changed after seeing their results.", ""]
    if split == "heldout6":
        return ["**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices. "
                "None is a genuine notice. " + extractor + " These numbers measure the status-freshness, publication-date, classification and "
                "relevance logic on authored notices (several documents per case where the case needs them); they are not real-world "
                "extraction quality.", "",
                "**Held-out protocol.** The `heldout6` cases were written on 27 Oct 2026 (fourth instruction) BEFORE any rule of that instruction "
                "was changed, and run once at the end; no rule was changed after seeing their results.", ""]
    if split == "heldout5":
        return ["**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices. "
                "None is a genuine notice. " + extractor + " These numbers measure the validation, relevance, geography, status, "
                "contradiction and coverage logic on authored notices; they are not real-world extraction quality.", "",
                "**Held-out protocol.** The `heldout5` cases were written on 27 Oct 2026 (third instruction) BEFORE any rule of that instruction "
                "was changed, and run once at the end; no rule was changed after seeing their results.", ""]
    if split == "heldout4":
        return ["**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices. "
                "None is a genuine notice. " + extractor + " These numbers measure the validation, relevance, geography, status, "
                "contradiction and coverage logic on authored notices; they are not real-world extraction quality.", "",
                "**Held-out protocol.** The `heldout4` cases were written on 27 Oct 2026 after held-out set 3 had been run once and BEFORE any "
                "rule was changed in response to it; they were run once at the end; no rule was changed after seeing their results.", ""]
    if split == "heldout3":
        return ["**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices. "
                "None is a genuine notice. " + extractor + " These numbers measure the validation, relevance, geography, status, "
                "contradiction and coverage logic on authored notices; they are not real-world extraction quality.", "",
                "**Held-out protocol.** The `heldout3` cases were written on 27 Oct 2026 BEFORE the freight-relevance, geography-conflict, "
                "status/age and interpretation rules of the second instruction were tuned, and run once at the end; no rule was changed after "
                "seeing their results. Failures are reported below as limitations.", ""]
    if split == "heldout2":
        return ["**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices. "
                "None is a genuine notice. " + extractor + " These numbers measure the validation, identity, deadline, geography, "
                "contradiction and coverage logic on authored notices; they are not real-world extraction quality.", "",
                "**Held-out protocol.** The `heldout2` cases were written before the interpretation-gap rules of 27 Oct 2026 were tuned and run "
                "once at the end; no rule was changed after seeing their results. Failures are reported below as limitations.", ""]
    return ["**Provenance.** Every notice in this set was AUTHORED for this build in the form of real airline and procurement notices "
            "(RFP pages, corrigenda, award and cancellation notices, newsroom items, tabular tender listings, PDF notices; English, French, "
            "Spanish, Portuguese, German). None is a genuine notice (the genuine set is reported separately). " + extractor +
            " These numbers measure the validation, identity, deadline, geography, contradiction and coverage logic on authored notices. "
            "They are not real-world extraction quality and do not show market coverage.", "",
            "**Protocol.** Tuning cases (including the former held-out cases h01-h12, whose findings were fixed) were used while adjusting "
            "the rules; they are regression tests, not a measure of generalisation.", ""]


def report_md(results: list[dict[str, Any]], when: str, split: str = "all") -> str:
    lines = ["# Extraction-quality evaluation", "",
             f"Run at {when} on validation rules v{eligibility.VALIDATION_VERSION}, split `{split}`, extractor `{EXTRACTOR}`. {len(results)} cases "
             f"({sum(1 for r in results if r['split'] == 'tuning')} tuning, {sum(1 for r in results if r['split'].startswith('heldout'))} held-out, "
             f"{sum(1 for r in results if r['split'] == 'genuine')} genuine).", ""] + _provenance(split)
    for key, title in (("split", "By split"), ("notice_type", "By notice type"), ("categories", "By category"), ("language", "By language"),
                       ("module", "By capability area"), ("search_mode", "By search mode")):
        agg = aggregate(results, key)
        lines += [f"## {title}", "", "| Group | Cases | Relevance accuracy | Opportunity precision | Opportunity recall | Actionable precision | Actionable recall | Historical records retained (shown live) | Field accuracy | Field completeness | False 'supported' | Missed correct information | Complete coverage | Excluded as not freight (leaked) | Geography conflicts flagged (false) |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for g, a in agg.items():
            o = a["opportunities"]
            ac, hi = a["actionable"], a["historical"]
            lines.append(f"| {g} | {a['cases']} | {_pct(a['relevance']['correct'], a['relevance']['total'])} | {_pct(o['matched'], o['found'])} | {_pct(o['matched'], o['gold'])} | "
                         f"{_pct(ac['matched'], ac['found'])} | {_pct(ac['matched'], ac['gold'])} | {_pct(hi['retained'], hi['expected'])} ({hi['live']}) | "
                         f"{_pct(a['field_accuracy']['correct'], a['field_accuracy']['total'])} | {_pct(a['completeness']['present'], a['completeness']['expected'])} | "
                         f"{_pct(a['false_supported']['count'], a['false_supported']['of_gold_negative'])} | "
                         f"{_pct(a['missed_supported']['count'], a['missed_supported']['of_gold_positive'])} | {_pct(a['coverage']['complete'], a['coverage']['cases'])} | "
                         f"{_pct(a['excluded']['found'], a['excluded']['expected'])} ({a['excluded']['leaked']}) | "
                         f"{_pct(a['geography_conflicts']['flagged'], a['geography_conflicts']['expected'])} ({a['geography_conflicts']['false']}) |")
        lines.append("")
    lines += ["## Per case", "", "| Case | Split | Lang | Area | Found/gold | Missed | False opp. | Field acc. | False sup. | Missed sup. | Coverage | Notes |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        m = r["metrics"]
        fa = m["field_accuracy"]
        fac = sum(v["correct"] for v in fa.values())
        fat = sum(v["total"] for v in fa.values())
        cov = m["coverage"]
        cov_s = "complete" if cov["complete_after_final_run"] else "INCOMPLETE"
        if "long_first_run_marked_incomplete" in cov:
            cov_s += f"; first run flagged incomplete: {'yes' if cov['long_first_run_marked_incomplete'] else 'NO'}"
        extra = []
        if "contradiction_flagged" in m:
            extra.append(f"contradiction flagged: {'yes' if m['contradiction_flagged'] else 'NO'}")
        if "signal_module_expected" in m:
            extra.append(f"signal areas: {', '.join(m['signal_modules_found']) or 'none'} (expected {m['signal_module_expected']})")
        if "historical" in m:
            h = m["historical"]
            extra.append(f"historical records retained: {h['retained']}/{h['expected']}" + (f"; SHOWN LIVE: {h['live']}" if h["live"] else ""))
        if "publication_flag_expected" in m:
            extra.append(f"publication-date flag: {', '.join(m['publication_flags_found']) or 'none'} (expected {m['publication_flag_expected'] or 'none'})")
        if "excluded_expected" in m:
            extra.append(f"excluded (not freight / passenger): {m['excluded_found']}/{m['excluded_expected']}" + (f"; LEAKED into opportunities: {m['excluded_leaked']}" if m["excluded_leaked"] else ""))
        if "geography_conflict_expected" in m:
            extra.append(f"geography conflict flagged: {'yes' if m['geography_conflict_flagged'] else 'NO'} (expected {'yes' if m['geography_conflict_expected'] else 'no'})")
        scopes = [f"{o['title'][:40]}={o['freight_scope'] or '?'}" for o in r["found"] if o.get("freight_scope")]
        if scopes and any(g.get("freight_scope") for g in c_gold(r)):
            extra.append("freight scope: " + "; ".join(scopes))
        if m["false_supported_detail"]:
            extra.append("false supported: " + "; ".join(m["false_supported_detail"]))
        if m["missed_supported_detail"]:
            extra.append("missed: " + "; ".join(m["missed_supported_detail"]))
        lines.append(f"| {r['id']} | {r['split']} | {r['language']} | {r['module']} | {m['opportunities_matched']}/{m['opportunities_gold']} | "
                     f"{', '.join(m['missed_opportunities']) or '—'} | {m['false_opportunities']} | {_pct(fac, fat)} | {m['false_supported']} | "
                     f"{m['missed_supported']} | {cov_s} | {' · '.join(extra)} |")
    lines += ["", "## Reading the numbers (each denominator)", "",
              "- *Relevance accuracy* = correct freight-relevance judgements / every freight-relevance judgement the gold makes. The denominator "
              "counts each gold opportunity whose freight scope the gold asserts (cargo, mixed, unclear, conflicting) plus each record the gold "
              "expects to be EXCLUDED (passenger, not_freight). A gold opportunity the pipeline did not create counts as wrong.",
              "- *Opportunity precision* = matched opportunities / opportunities the pipeline created. *Recall* = matched / opportunities a "
              "reviewer finds in the notices (matched by tender reference, or by title where a notice has none). A cancelled, awarded, "
              "excluded or non-procurement notice has no gold opportunity, so anything created from it lowers precision.",
              "- *Actionable precision* = LIVE records (open or revised) the pipeline created whose reference is a live gold opportunity / live "
              "records created. *Actionable recall* = live gold opportunities found live / live gold opportunities. A terminal, announced, "
              "unverified or historical record never counts as actionable.",
              "- *Historical records retained (shown live)* = terminal notices (cancellation, award, closure) the gold expects to be KEPT as "
              "intelligence, found as a tender record with that terminal status / such notices; the bracket counts those wrongly shown live. "
              "Reported separately from actionable accuracy (fifth instruction of 27 Oct 2026, item 4).",
              "- *Field accuracy* = correct record values / record values the gold asserts on matched opportunities (status, deadline day, "
              "deadline precision, service, freight scope).",
              "- *Field completeness* = record values present / record values the gold expects to be present on matched opportunities "
              "(a stated deadline and its precision, the service, the freight scope); it says nothing about correctness.",
              "- *Excluded as not freight (leaked)*: records the gold excludes (passenger-only, cargo excluded, work outside the freight "
              "scope) that the pipeline kept as excluded evidence / records the gold excludes; 'leaked' counts those that became "
              "opportunities anyway.",
              "- *Geography conflicts flagged (false)*: documents whose title/territory definition and another passage disagree, flagged for "
              "review; 'false' counts conflicts flagged where the gold says there is none (a multi-country mandate, for example).",
              "- *False 'supported'* = proposed field values the notice does NOT state that were labelled supported / every proposed value the gold "
              "marks as not stated. The safety figure; the target is zero.",
              "- *Missed correct information* = proposed field values the notice DOES state that were not labelled supported / every proposed value "
              "the gold marks as stated (a stricter rule costs some of these; they go to review, never to 'supported'). A proposal rejected as a "
              "whole because another of its fields is wrong is not counted.",
              "- *Coverage*: whether every document was completely read by the end; long documents must first be flagged incomplete.",
              "- **These figures come from a SCRIPTED extractor** (it returns each case's prepared proposals). They measure the application's "
              "validation, relevance, identity, status and coverage rules; they are NOT evidence of AI extraction quality.",
              "- Capability areas fed by WFC's own records (account growth, forwarder sales, service and operations) have no discoverable "
              "opportunities by design; their cases check that no opportunity is invented from a public notice.", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["all", "tuning", "heldout", "heldout2", "heldout3", "heldout4", "heldout5", "heldout6", "heldout7", "genuine"])
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--only", default=None, help="run one case id")
    ap.add_argument("--extractor", default="scripted", choices=["scripted", "configured"],
                    help="scripted: the case's proposals (no provider call); configured: the AI extractor named by the environment")
    args = ap.parse_args()
    global EXTRACTOR, SETTINGS
    EXTRACTOR = args.extractor
    if EXTRACTOR == "configured":
        SETTINGS = configured_settings()
        print(f"[eval] extractor: configured ({SETTINGS.ai_model} at {SETTINGS.ai_api_base_url})", flush=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pool = (genuine_cases() if args.split == "genuine" else heldout3_cases() if args.split == "heldout3"
            else heldout4_cases() if args.split == "heldout4" else heldout5_cases() if args.split == "heldout5"
            else heldout6_cases() if args.split == "heldout6"
            else heldout7_cases() if args.split == "heldout7"
            else cases(None if args.split == "all" else args.split))
    selected = [c for c in pool if not args.only or c.id == args.only]
    results = []
    for c in selected:
        print(f"[eval] {c.id} ...", flush=True)
        r = run_case(c)
        m = r["metrics"]
        print(f"[eval]   found {m['opportunities_matched']}/{m['opportunities_gold']} false-opp {m['false_opportunities']} false-supported {m['false_supported']} "
              f"missed-supported {m['missed_supported']} coverage {'ok' if m['coverage']['complete_after_final_run'] else 'INCOMPLETE'}", flush=True)
        results.append(r)
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out / f"results-{args.split}.json").write_text(json.dumps({"run_at": when, "validation_version": eligibility.VALIDATION_VERSION,
                                                                 "extractor": EXTRACTOR, "split": args.split, "results": results}, indent=2, default=str))
    (out / f"report-{args.split}.md").write_text(report_md(results, when, args.split))
    print(f"[eval] wrote {out / f'report-{args.split}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
