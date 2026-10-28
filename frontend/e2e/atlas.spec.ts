import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const USER = process.env.LOGIN_USERNAME ?? "ops@wfc.local";
const PASS = process.env.LOGIN_BOOTSTRAP_PASSWORD ?? "";
const VIEWPORTS = [1440, 1280, 1024, 768, 430, 390, 360];
const PAGES = ["/", "/opportunities", "/airlines-forwarders", "/lanes", "/service", "/capabilities", "/relationships",
               "/network", "/reports", "/data-sources", "/settings"];

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill(PASS);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: /Sections/ }).first()).toBeVisible();
}

test("browser metadata and three-line brand", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE");
  await expect(page.getByText("VECTA Connect", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("ATLAS", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("DYNAMIC MARKET INTELLIGENCE", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/sport/i)).toHaveCount(0);
});

test("unauthenticated API access is refused everywhere", async ({ request }) => {
  for (const p of ["/api/briefing", "/api/opportunities", "/api/search?q=ab", "/api/reports/opportunities.csv", "/api/settings", "/api/audit"]) {
    const r = await request.get(p);
    expect(r.status(), p).toBe(401);
    expect(r.headers()["cache-control"]).toBe("no-store");
  }
  expect((await request.post("/api/imports/bookings/commit")).status()).toBe(401);
});

test("wrong password shows an error, right password signs in", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill("definitely-wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText(/Incorrect/);
  await page.getByLabel("Password").fill(PASS);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("session survives reload; sign out ends it", async ({ page }) => {
  await signIn(page);
  await page.reload();
  await expect(page.getByRole("navigation", { name: /Sections/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Username")).toBeVisible();
});

for (const width of VIEWPORTS) {
  test(`every page renders without horizontal page scroll at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await signIn(page);
    for (const p of PAGES) {
      await page.goto(p);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.locator(".skeleton")).toHaveCount(0, { timeout: 15_000 });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${p} at ${width}px`).toBeLessThanOrEqual(1);
    }
  });
}

test("keyboard: skip link and focusable table regions", async ({ page }) => {
  await signIn(page);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});

async function importFile(page: Page, tab: RegExp, dataset: string, file: string) {
  await page.goto("/data-sources");
  await page.getByRole("tab", { name: tab }).click();
  await page.locator("label.field", { hasText: /^Dataset/ }).locator("select").selectOption(dataset);
  await page.getByLabel(/File \(\.csv/).setInputFiles(path.join(__dirname, "fixtures", file));
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  const commit = page.getByRole("button", { name: /^Commit \d+ change/ });
  await expect(commit).toBeVisible();
  return commit;
}

// Reference data first: on a fresh installation DXB and NBO exist only after the Setup airports import
// (the earlier spec imported bookings into an empty airport register).
test("journey: setup airports -> bookings preview (quarantine) -> commit -> lanes -> report", async ({ page }) => {
  await signIn(page);
  await (await importFile(page, /Setup/, "airports", "airports.csv")).click();
  await expect(page.getByText(/committed/i).first()).toBeVisible();
  const commit = await importFile(page, /Operational data/, "bookings", "bookings.csv");
  await expect(page.getByText("origin and destination must differ")).toBeVisible();
  await commit.click();
  await expect(page.getByText(/partial|quarantined/i).first()).toBeVisible();      // partial import disclosed
  await page.goto("/lanes");
  await page.getByLabel("From").fill("2026-10-01");
  await page.getByLabel("To").fill("2026-10-31");
  await expect(page.getByText("DXB → NBO")).toBeVisible();
  await expect(page.getByText("NBO → DXB")).toBeVisible();
  await page.getByRole("button", { name: "Details" }).first().click();
  await expect(page.getByText(/Not available: no capacity data/)).toBeVisible();   // no invented utilisation
  await page.goto("/reports");
  await expect(page.getByText("Retained contribution by currency")).toBeVisible();
});
