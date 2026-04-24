/**
 * E2E: Landing page mode-picker.
 *
 * Verifies:
 *   - Both mode cards (Employees / General) are visible
 *   - Privacy notice banner is visible
 *   - "Continue as guest" navigates to /ask
 *
 * Requires the Next.js dev server running at BASE_URL (default localhost:3000).
 * Requires FAKE_AUTH_EMAIL set in backend .env for auth-related flows — not
 * needed for this spec (purely frontend navigation).
 */

import { test, expect } from "@playwright/test";

test.describe("Landing mode-picker", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("both mode cards are visible", async ({ page }) => {
    // Employees / internal card
    await expect(
      page.getByRole("heading", { name: /employees/i }).or(
        page.getByText(/employees/i).first()
      )
    ).toBeVisible();

    // General / external card
    await expect(
      page.getByRole("heading", { name: /general/i }).or(
        page.getByText(/general/i).first()
      )
    ).toBeVisible();
  });

  test("privacy notice banner is visible", async ({ page }) => {
    await expect(
      page.getByText(/chat messages are logged/i).or(
        page.getByText(/privacy/i).first()
      )
    ).toBeVisible();
  });

  test("continue as guest button navigates to /ask", async ({ page }) => {
    const guestButton = page
      .getByRole("button", { name: /guest/i })
      .or(page.getByRole("link", { name: /guest/i }))
      .first();

    await expect(guestButton).toBeVisible();
    await guestButton.click();

    await expect(page).toHaveURL(/\/ask/);
  });
});
