"""Responsive and accessibility checks (directive §1, §13) at 1440, 1280, 1024,
768, 430, 390 and 360 px, in dark and light mode, on every main page, using
the data the journeys created. Runs after test_journeys.py (alphabetical).

axe-core could not be installed in the build environment (package registries
blocked), so the checks below are explicit, in-page WCAG 2.1 AA tests:
document language and title, one <main> and one <h1>, accessible names for
every form control, button and link, image alternatives, keyboard focus
visibility, text contrast (1.4.3) against the resolved background, no
horizontal page scroll (1.4.10), and the VECTA brand hierarchy present.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:3000")
USER = os.environ.get("E2E_USER", "ops@wfc.example")
PASSWORD = os.environ.get("E2E_PASSWORD", "Local-Verify-Pass-2026!")
ART = Path(os.environ.get("E2E_ARTIFACTS", "e2e-artifacts")).resolve()
WIDTHS = [1440, 1280, 1024, 768, 430, 390, 360]
BRAND = ("VECTA Connect", "ATLAS", "DYNAMIC MARKET INTELLIGENCE")

AUDIT_JS = r"""
() => {
  const out = { problems: [], contrast: [] };
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.closest('[hidden],[aria-hidden="true"]'); };
  const name = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const lb = el.getAttribute('aria-labelledby');
    if (lb) return lb.split(/\s+/).map((id) => document.getElementById(id)?.textContent || '').join(' ').trim();
    if (el.labels && el.labels.length) return Array.from(el.labels).map((l) => l.textContent).join(' ').trim();
    if (el.title) return el.title;
    if (['BUTTON','A','SUMMARY'].includes(el.tagName)) return (el.textContent || '').trim() || Array.from(el.querySelectorAll('img,svg')).map((i) => i.getAttribute('alt') || i.getAttribute('aria-label') || '').join('');
    return '';
  };
  if (!document.documentElement.lang) out.problems.push('html has no lang');
  if (!document.title.trim()) out.problems.push('empty <title>');
  if (document.querySelectorAll('main').length !== 1) out.problems.push(`main landmarks: ${document.querySelectorAll('main').length}`);
  const h1 = Array.from(document.querySelectorAll('h1')).filter(vis);
  if (h1.length !== 1) out.problems.push(`visible h1 count ${h1.length}`);
  for (const el of document.querySelectorAll('input:not([type=hidden]),select,textarea,button,a[href],summary')) {
    if (!vis(el)) continue;
    if (!name(el)) out.problems.push(`no accessible name: <${el.tagName.toLowerCase()} class="${el.className}"> ${el.outerHTML.slice(0, 120)}`);
  }
  for (const img of document.querySelectorAll('img')) if (!img.hasAttribute('alt')) out.problems.push(`img without alt: ${img.src}`);
  const ids = {}; for (const el of document.querySelectorAll('[id]')) { ids[el.id] = (ids[el.id] || 0) + 1; }
  for (const [k, n] of Object.entries(ids)) if (n > 1) out.problems.push(`duplicate id ${k}`);
  const doc = document.scrollingElement;
  if (doc.scrollWidth > window.innerWidth + 1) {
    const wide = Array.from(document.querySelectorAll('body *')).filter((e) => vis(e) && e.getBoundingClientRect().right > window.innerWidth + 1 && !e.closest('.table-wrap'))
      .slice(0, 3).map((e) => `${e.tagName.toLowerCase()}.${e.className}`);
    out.problems.push(`horizontal page scroll: ${doc.scrollWidth} > ${window.innerWidth} (${wide.join(', ')})`);
  }
  // Text contrast (WCAG 1.4.3) against the first opaque ancestor background.
  const rgb = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = (el) => { let stack = []; for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; } }
    let base = { r: 255, g: 255, b: 255 }; if (stack.length && stack[stack.length - 1].a >= 1) base = stack.pop();
    for (const c of stack.reverse()) base = { r: c.r * c.a + base.r * (1 - c.a), g: c.g * c.a + base.g * (1 - c.a), b: c.b * c.a + base.b * (1 - c.a) };
    return base; };
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement; if (!el || !n.textContent.trim() || seen.has(el) || !vis(el)) continue; seen.add(el);
    if (el.closest('[disabled],:disabled,.sr-only')) continue;
    const s = getComputedStyle(el); const fg = rgb(s.color); if (!fg) continue;
    const bg = bgOf(el); const f = { r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a) };
    const L1 = lum(f), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(s.fontSize); const bold = parseInt(s.fontWeight, 10) >= 700;
    const need = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;
    if (ratio < need) out.contrast.push(`${ratio.toFixed(2)} < ${need}: "${n.textContent.trim().slice(0, 40)}" (${el.tagName.toLowerCase()}.${el.className})`);
  }
  return out;
}
"""

PAGES = ["/", "/discovery", "/review", "/opportunities", "/opportunities/{opp}", "/areas", "/areas/forwarder-sales", "/sources",
         "/data-sources", "/settings", "/reports", "/service", "/network", "/capabilities", "/lanes", "/relationships",
         "/airlines-forwarders", "/discovery/runs/{run}"]


@pytest.fixture(scope="module")
def signed_in():
    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context(viewport={"width": 1440, "height": 900})
        page = c.new_page()
        page.goto(f"{BASE}/")
        page.get_by_label("Username").fill(USER)
        page.get_by_label("Password").fill(PASSWORD)
        page.get_by_role("button", name=re.compile("Sign in")).click()
        page.get_by_role("navigation", name="Sections").wait_for()
        ids = {"opp": page.request.get(f"{BASE}/api/opportunities?limit=1").json()["items"][0]["id"],
               "run": page.request.get(f"{BASE}/api/discovery/runs").json()["items"][0]["id"]}
        yield page, ids
        b.close()


def _audit(page: Page) -> dict:
    return page.evaluate(AUDIT_JS)


def test_login_page_all_widths():
    report = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in WIDTHS:
            page = b.new_page(viewport={"width": w, "height": 900})
            page.goto(f"{BASE}/")
            page.get_by_label("Username").wait_for()
            text = page.inner_text("body")
            missing = [x for x in BRAND if x not in text]
            res = _audit(page)
            report[w] = {"missing_brand": missing, **res}
            (ART / "responsive").mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(ART / "responsive" / f"login-{w}.png"), full_page=True)
            page.close()
        b.close()
    (ART / "responsive" / "login-report.json").write_text(json.dumps(report, indent=2))
    bad = {w: r for w, r in report.items() if r["missing_brand"] or r["problems"] or r["contrast"]}
    assert not bad, json.dumps(bad, indent=2)[:3000]


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_pages_all_widths(signed_in, theme):
    page, ids = signed_in
    out = ART / "responsive"
    out.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE}/")
    page.wait_for_load_state("networkidle")
    if theme == "light":
        page.get_by_role("button", name=re.compile("Light mode")).click()
    report: dict[str, dict] = {}
    for path in PAGES:
        url = path.format(**ids)
        for w in WIDTHS:
            page.set_viewport_size({"width": w, "height": 900})
            page.goto(f"{BASE}{url}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(150)
            res = _audit(page)
            chrome = page.inner_text("body")
            res["missing_brand"] = [x for x in BRAND if x not in chrome]
            key = f"{url} @{w}"
            report[key] = res
            if w in (1440, 768, 390) or res["problems"] or res["contrast"]:
                slug = (url.strip("/").replace("/", "-") or "briefing")[:40]
                page.screenshot(path=str(out / f"{theme}-{slug}-{w}.png"), full_page=w != 1440)
    (out / f"pages-{theme}-report.json").write_text(json.dumps(report, indent=2))
    bad = {k: v for k, v in report.items() if v["problems"] or v["contrast"] or v["missing_brand"]}
    assert not bad, f"{len(bad)} page/width combinations with problems:\n" + json.dumps(dict(list(bad.items())[:8]), indent=2)[:6000]


def test_keyboard_focus_is_visible(signed_in):
    page, _ = signed_in
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{BASE}/discovery")
    page.wait_for_load_state("networkidle")
    missing = []
    for _ in range(25):
        page.keyboard.press("Tab")
        info = page.evaluate("""() => { const e = document.activeElement; if (!e || e === document.body) return null;
            const s = getComputedStyle(e); return { tag: e.tagName, text: (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 30),
            outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0, shadow: s.boxShadow !== 'none' }; }""")
        if info and not (info["outline"] or info["shadow"]):
            missing.append(info)
    assert not missing, missing
