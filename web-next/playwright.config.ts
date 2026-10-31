import { defineConfig, devices } from "@playwright/test";

// Web e2e: global setup boots `rdm serve` on a temp data dir and seeds the
// project/identities; every spec then drives the built SPA in Chromium.
export default defineConfig({
  testDir: "./e2e/specs",
  globalSetup: "./e2e/global-setup.ts",
  outputDir: "./e2e/.results",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    ...devices["Desktop Chrome"],
    // Existing specs assert Chinese UI text; keep the browser on zh-CN so the
    // app's navigator.language detection does not switch to English.
    locale: "zh-CN",
    viewport: { width: 1600, height: 900 },
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium" }],
});
