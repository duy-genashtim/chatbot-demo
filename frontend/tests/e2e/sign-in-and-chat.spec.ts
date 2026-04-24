/**
 * E2E: Stubbed auth path — sign-in then send a chat message.
 *
 * Uses FAKE_AUTH_EMAIL bypass (backend dev-only shortcut) combined with
 * a mocked NextAuth session response so the frontend treats the user as
 * signed in without a real Entra ID flow.
 *
 * Pre-requisites (dev environment only):
 *   - Backend env: FAKE_AUTH_EMAIL=dev@test.com, ENVIRONMENT=dev
 *   - Next.js server running at BASE_URL
 *
 * The spec mocks:
 *   - GET /api/auth/session → returns a fake session object
 *   - POST /api/internal/chat → returns a canned SSE stream
 *
 * So no real backend or Entra tenant is required.
 */

import { test, expect } from "@playwright/test";

const FAKE_SESSION = {
  user: {
    name: "Dev User",
    email: "dev@test.com",
    image: null,
  },
  expires: "2099-01-01T00:00:00.000Z",
};

const SSE_BODY = [
  'event: sources\ndata: [{"source":"hr.pdf","section":"leave"}]\n\n',
  'event: delta\ndata: {"text":"Annual leave is "}\n\n',
  'event: delta\ndata: {"text":"20 days."}\n\n',
  'event: done\ndata: {"session_id":"fake-sid-001","latency_ms":200}\n\n',
].join("");

test.describe("Sign-in and internal chat (stubbed)", () => {
  test.beforeEach(async ({ page }) => {
    // Stub NextAuth session as authenticated
    await page.route("**/api/auth/session", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FAKE_SESSION),
      });
    });

    // Stub backend internal chat SSE
    await page.route("**/api/internal/chat", (route) => {
      route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
        },
        body: SSE_BODY,
      });
    });
  });

  test("authenticated user sees chat interface at /chat", async ({ page }) => {
    await page.goto("/chat");

    // Chat input should be present for authenticated users
    await expect(
      page.getByRole("textbox").or(page.locator("textarea")).first()
    ).toBeVisible({ timeout: 8000 });
  });

  test("sending message shows user text in conversation", async ({ page }) => {
    await page.goto("/chat");

    const input = page
      .getByRole("textbox")
      .or(page.locator("textarea"))
      .first();
    await input.waitFor({ state: "visible", timeout: 8000 });
    await input.fill("How many leave days do I get?");

    const sendBtn = page
      .getByRole("button", { name: /send/i })
      .or(page.locator("button[type=submit]"))
      .first();

    if (await sendBtn.isVisible()) {
      await sendBtn.click();
    } else {
      await input.press("Enter");
    }

    await expect(
      page.getByText("How many leave days do I get?")
    ).toBeVisible({ timeout: 5000 });
  });

  test("assistant response appears after done event", async ({ page }) => {
    await page.goto("/chat");

    const input = page
      .getByRole("textbox")
      .or(page.locator("textarea"))
      .first();
    await input.waitFor({ state: "visible", timeout: 8000 });
    await input.fill("leave question");

    const sendBtn = page
      .getByRole("button", { name: /send/i })
      .or(page.locator("button[type=submit]"))
      .first();

    if (await sendBtn.isVisible()) {
      await sendBtn.click();
    } else {
      await input.press("Enter");
    }

    // SSE mock yields "Annual leave is " + "20 days."
    await expect(
      page.getByText(/Annual leave is.*20 days/i)
    ).toBeVisible({ timeout: 5000 });
  });
});
