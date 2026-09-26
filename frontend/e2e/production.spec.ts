import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

// Checks that only show up in production: the Caddy CSP and a phone-sized viewport.
// Dev and the e2e stack serve the app without the CSP header, so the document response is
// re-served here with the exact policy from deploy/caddy/Caddyfile and the browser enforces it.

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CADDYFILE = path.resolve(__dirname, "../../deploy/caddy/Caddyfile");
const CSP = /Content-Security-Policy "([^"]+)"/.exec(fs.readFileSync(CADDYFILE, "utf8"))?.[1];

declare global {
  interface Window {
    __cspViolations?: string[];
  }
}

async function enforceProductionCsp(page: Page) {
  expect(CSP, "CSP header not found in deploy/caddy/Caddyfile").toBeTruthy();
  const requested: string[] = [];
  page.on("request", (request) => requested.push(request.url()));
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      (window.__cspViolations ??= []).push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  await page.route("**/*", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    await route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": CSP! } });
  });
  return {
    foreignRequests: () => {
      const origin = new URL(page.url()).origin;
      return requested.filter((u) => u.startsWith("http") && new URL(u).origin !== origin);
    },
    violations: () => page.evaluate(() => window.__cspViolations ?? []),
  };
}

// The SVAR icon font must come from our own origin (self-hosted) and actually be used.
async function iconFontLoaded(page: Page) {
  return page.evaluate(async () => {
    await document.fonts.ready;
    const face = [...document.fonts].find((f) => f.family.replace(/["']/g, "") === "wx-icons");
    return face?.status ?? "missing";
  });
}

test("production CSP: no violations, no third-party requests, icon font renders", async ({ page }) => {
  const csp = await enforceProductionCsp(page);
  await page.goto("/");
  await expect(page.getByText("Сбор требований и приоритизация").last()).toBeVisible();

  // The grid/timeline resizer's expand icons (the SVAR grid toggle) use the wx-icons font.
  const toggle = page.locator(".wx-resizer .wxi-menu-right").first();
  await expect(toggle).toBeAttached();
  const glyph = await toggle.evaluate((el) => {
    const before = getComputedStyle(el, "::before");
    return { font: before.fontFamily, content: before.content };
  });
  expect(glyph.font).toContain("wx-icons");
  expect(glyph.content).not.toBe("none");
  await expect.poll(() => iconFontLoaded(page)).toBe("loaded");

  expect(await csp.violations()).toEqual([]);
  expect(csp.foreignRequests()).toEqual([]);
});
