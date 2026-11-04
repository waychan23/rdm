import type { Browser, Page } from "@playwright/test";

import type { Api } from "../support/api";
import { storageStateFor } from "../support/context";
import { expect, test } from "../support/fixtures";

// RDM-130: with permission granted, a notification that arrives while the tab
// is hidden/unfocused opens a browser-native Notification. The real API cannot
// be inspected from the test, so the init script replaces it with a recorder.
async function openAlice(
  browser: Browser,
  baseURL: string,
  { hidden }: { hidden: boolean },
): Promise<Page> {
  const context = await browser.newContext({ storageState: storageStateFor("alice") });
  await context.addInitScript(`
    window.__rdmDesktopNotifications = [];
    class FakeNotification {
      static permission = "granted";
      static requestPermission = async () => "granted";
      onclick = null;
      constructor(title, options) {
        window.__rdmDesktopNotifications.push({ title, ...options });
      }
      close() {}
    }
    Object.defineProperty(window, "Notification", {
      value: FakeNotification,
      configurable: true,
    });
    Object.defineProperty(Document.prototype, "visibilityState", {
      get: () => "${hidden ? "hidden" : "visible"}",
      configurable: true,
    });
    Object.defineProperty(Document.prototype, "hasFocus", {
      value: () => ${hidden ? "false" : "true"},
      configurable: true,
    });
  `);
  const page = await context.newPage();
  const streamRequest = page.waitForRequest(/\/api\/v1\/stream/);
  await page.goto(`${baseURL}/inbox`);
  await expect(page.getByTestId("page-inbox")).toBeVisible();
  await streamRequest;
  return page;
}

function recordedTitles(page: Page): Promise<string[]> {
  return page.evaluate(
    () =>
      (window as unknown as { __rdmDesktopNotifications: { title: string }[] })
        .__rdmDesktopNotifications.map((n) => n.title),
  );
}

async function assignToAlice(api: Api): Promise<{ display_id: string }> {
  const item = await api.createItem({ kind: "task", title: `native-${Date.now()}` });
  await api.post(`/work-items/${item.display_id}/assign`, {
    member: api.userId("alice"),
  });
  return item;
}

test("a hidden tab raises a native notification for a new assignment", async ({
  api,
  app,
  browser,
}) => {
  const page = await openAlice(browser, app.baseURL, { hidden: true });
  const item = await assignToAlice(api);

  await expect
    .poll(() => recordedTitles(page), { timeout: 10_000 })
    .toContain(`你被指派了 ${item.display_id}`);
});

test("a focused tab leaves the native notification to the in-app bell", async ({
  api,
  app,
  browser,
}) => {
  const page = await openAlice(browser, app.baseURL, { hidden: false });
  const item = await assignToAlice(api);

  // The event arrived (the inbox updates), but no system notification fired.
  await expect(page.getByText(`你被指派了 ${item.display_id}`)).toBeVisible({
    timeout: 10_000,
  });
  expect(await recordedTitles(page)).toEqual([]);
});
