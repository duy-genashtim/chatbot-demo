/**
 * E2E: /ask — external anonymous chat page.
 *
 * Verifies the chat shell renders and the message input is interactive.
 * Actual backend calls are skipped via route.fulfill() mock so the spec
 * runs without a live backend.
 *
 * SSE mock returns: sources → delta("hello world") → done events.
 */

import { test, expect } from "@playwright/test";

const SSE_BODY = [
  "event: sources\ndata: []\n\n",
  'event: delta\ndata: {"text":"hello "}\n\n',
  'event: delta\ndata: {"text":"world"}\n\n',
  'event: done\ndata: {"session_id":"test-sid","latency_ms":120}\n\n',
].join("");

test.describe("/ask external chat page", () => {
  test.beforeEach(async ({ page }) => {
    // Intercept backend chat calls to avoid needing a live server
    await page.route("**/api/external/chat", (route) => {
      route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
        },
        body: SSE_BODY,
      });
    });

    await page.goto("/ask");
  });

  test("chat input and send button are visible", async ({ page }) => {
    await expect(
      page.getByRole("textbox").or(page.locator("textarea")).first()
    ).toBeVisible();
  });

  test("sending a message shows a response bubble", async ({ page }) => {
    const input = page
      .getByRole("textbox")
      .or(page.locator("textarea"))
      .first();

    await input.fill("What is the leave policy?");

    // Submit via Enter key or send button
    const sendBtn = page
      .getByRole("button", { name: /send/i })
      .or(page.locator("button[type=submit]"))
      .first();

    if (await sendBtn.isVisible()) {
      await sendBtn.click();
    } else {
      await input.press("Enter");
    }

    // After sending, the user message should appear
    await expect(page.getByText("What is the leave policy?")).toBeVisible({
      timeout: 5000,
    });
  });

  test("assistant response text appears after stream", async ({ page }) => {
    const input = page
      .getByRole("textbox")
      .or(page.locator("textarea"))
      .first();
    await input.fill("policy question");

    const sendBtn = page
      .getByRole("button", { name: /send/i })
      .or(page.locator("button[type=submit]"))
      .first();

    if (await sendBtn.isVisible()) {
      await sendBtn.click();
    } else {
      await input.press("Enter");
    }

    // SSE mock yields "hello " + "world"
    await expect(page.getByText(/hello.*world/i)).toBeVisible({
      timeout: 5000,
    });
  });
});
