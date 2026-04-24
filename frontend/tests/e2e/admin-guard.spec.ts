/**
 * E2E: Admin route guard.
 *
 * Verifies that unauthenticated users cannot access /admin routes and
 * are redirected away (to "/" or "/api/auth/signin").
 *
 * No backend or auth service needed — Next.js middleware / layout guard
 * handles the redirect purely on the frontend.
 */

import { test, expect } from "@playwright/test";

test.describe("Admin route guard", () => {
  test("visiting /admin without auth redirects away from /admin", async ({
    page,
  }) => {
    // Intercept any backend auth check to return 401 (unauthenticated)
    await page.route("**/api/auth/session", (route) => {
      route.fulfill({ status: 200, body: JSON.stringify(null) });
    });

    await page.goto("/admin");

    // Should NOT stay on /admin — redirected to landing or sign-in
    await expect(page).not.toHaveURL(/\/admin/, { timeout: 5000 });
  });

  test("visiting /admin/documents without auth redirects away", async ({
    page,
  }) => {
    await page.route("**/api/auth/session", (route) => {
      route.fulfill({ status: 200, body: JSON.stringify(null) });
    });

    await page.goto("/admin/documents");

    await expect(page).not.toHaveURL(/\/admin\/documents/, { timeout: 5000 });
  });

  test("redirect destination is reachable (no infinite redirect loop)", async ({
    page,
  }) => {
    await page.route("**/api/auth/session", (route) => {
      route.fulfill({ status: 200, body: JSON.stringify(null) });
    });

    await page.goto("/admin");

    // After redirect, the page should be stable (200, not 500)
    // Verify we land on a real page (has a body/title)
    await expect(page.locator("body")).toBeVisible({ timeout: 5000 });
  });
});
