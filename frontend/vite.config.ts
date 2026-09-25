import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
