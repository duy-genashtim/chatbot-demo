/**
 * Playwright configuration for chatbotv2 frontend E2E tests.
 *
 * Targets a locally-running Next.js dev server (or built production server).
 * Set BASE_URL env var to override the default http://localhost:3000.
 *
 * Specs live in tests/e2e/.
 * Run: npx playwright test
 * List: npx playwright test --list
 */

import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { open: "never" }]],
  timeout: 30_000,

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Uncomment to auto-start Next.js dev server before tests:
  // webServer: {
  //   command: "npm run dev",
  //   url: BASE_URL,
  //   reuseExistingServer: !process.env.CI,
  //   timeout: 60_000,
  // },
});
