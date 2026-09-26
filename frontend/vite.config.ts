import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import type { Plugin } from "vite";
import { configDefaults, defineConfig } from "vitest/config";

// SVAR's bundled CSS declares its Open Sans / Roboto webfonts with @font-face rules that load from
// https://cdn.svar.dev. The app never uses those families (see gantt.css), the production CSP
// would block them, and a third-party request leaks visitors' IPs — so drop the rules from the
// build entirely rather than ship dead references to a CDN.
function dropSvarCdnFonts(): Plugin {
  return {
    name: "drop-svar-cdn-fonts",
    enforce: "pre",
    transform(code, id) {
      const file = id.split("?")[0];
      if (!file.includes("@svar-ui") || !file.endsWith(".css")) return null;
      return { code: code.replace(/@font-face\s*\{[^}]*cdn\.svar\.dev[^}]*\}/g, ""), map: null };
    },
  };
}

export default defineConfig({
  plugins: [dropSvarCdnFonts(), react(), tailwindcss()],
  // Fonts are always emitted as files: a data: URI font would be blocked by the production CSP
  // (font-src falls back to default-src 'self').
  build: { assetsInlineLimit: (file) => (file.endsWith(".woff2") ? false : undefined) },
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: { proxy: { "/api": "http://localhost:8000", "/healthz": "http://localhost:8000" } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    // `e2e/` holds Playwright specs (its own test() from @playwright/test, run separately via
    // `npx playwright test`) — Vitest's default include glob would otherwise pick them up too
    // and fail with "did not expect test() to be called here".
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
