import type { Page } from "@playwright/test";

import { expect, test } from "../support/fixtures";

test.describe("work item drawer dismissal", () => {
  test("blank backdrop clicks close the panel without flashing the list", async ({
    api,
    app,
    page,
  }) => {
    // Isolated project: the shared WFE2E list accumulates items across specs
    // and would push this test's rows off page 1.
    const projectKey = await api.createSandboxProject();
    const first = await api.createItemIn(projectKey, {
      kind: "task",
      title: `dismiss-a-${Date.now()}`,
      assignee: "alice",
    });
    const second = await api.createItemIn(projectKey, {
      kind: "task",
      title: `dismiss-b-${Date.now()}`,
      assignee: "alice",
    });

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
    await expect(page.getByTestId("page-backlog")).toBeVisible();
    const firstRow = page.getByTestId(`work-item-row-${first.display_id}`);
    const secondRow = page.getByTestId(`work-item-row-${second.display_id}`);
    await expect(firstRow).toBeVisible();
    await watchLoading(page, "work-item-loading");

    // Opening the panel must not remount the list into its spinner.
    await firstRow.click();
    await expect(page.getByTestId("item-panel")).toBeVisible();
    await expect(page.getByTestId("item-panel-title")).toContainText(first.title);
    expect(await listingLoading(page)).toBe(false);

    // Closing returns to the same rows without a loading flash.
    await dismissByBlankClick(page);
    await expect(page.getByTestId("item-panel")).toHaveCount(0);
    await expect(page.getByTestId("page-backlog")).toBeVisible();
    await expect(firstRow).toBeVisible();
    expect(await listingLoading(page)).toBe(false);

    // Interactive list rows must not be swallowed by the dismiss handler:
    // opening another item swaps the panel instead of closing it.
    await firstRow.click();
    await expect(page.getByTestId("item-panel-title")).toContainText(first.title);
    await secondRow.click({ position: { x: 60, y: 12 } });
    await expect(page.getByTestId("item-panel")).toBeVisible();
    await expect(page.getByTestId("item-panel-title")).toContainText(second.title);

    // Clicks inside the panel itself never dismiss it.
    await page.getByTestId("item-panel-display-id").click();
    await expect(page.getByTestId("item-panel")).toBeVisible();
  });

  test("the board keeps its cards across open and close", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const item = await api.createItemIn(projectKey, {
      kind: "task",
      title: `dismiss-board-${Date.now()}`,
      assignee: "alice",
    });

    await page.goto(`${app.baseURL}/projects/${projectKey}/board`);
    await expect(page.getByTestId("page-board")).toBeVisible();
    const card = page.getByTestId(`board-card-${item.display_id}`);
    await expect(card).toBeVisible();
    await watchLoading(page, "board-loading");

    await card.click();
    await expect(page.getByTestId("item-panel")).toBeVisible();
    expect(await listingLoading(page)).toBe(false);

    await dismissByBlankClick(page);
    await expect(page.getByTestId("item-panel")).toHaveCount(0);
    await expect(page.getByTestId("page-board")).toBeVisible();
    await expect(card).toBeVisible();
    expect(await listingLoading(page)).toBe(false);
  });
});

test.describe("scroll restoration", () => {
  // Short viewport so the list overflows without creating a big fixture.
  test.use({ viewport: { width: 1600, height: 500 } });

  test("closing the drawer returns to the same list scroll offset", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    for (let index = 0; index < 10; index += 1) {
      await api.createItemIn(projectKey, {
        kind: "task",
        title: `scroll-${index}-${Date.now()}`,
        assignee: "alice",
      });
    }

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
    await expect(page.getByTestId("page-backlog")).toBeVisible();
    const rows = page.locator('[data-testid^="work-item-row-"]');
    await expect(rows.first()).toBeVisible();

    // RDM-125: the list body is the page's scroller, not the shell.
    const scroller = page.getByTestId("work-item-table-scroll");
    const target = rows.last();
    await target.scrollIntoViewIfNeeded();
    const before = await scroller.evaluate((el) => el.scrollTop);
    expect(before).toBeGreaterThan(0);

    await target.click();
    await expect(page.getByTestId("item-panel")).toBeVisible();
    await dismissByBlankClick(page);
    await expect(page.getByTestId("item-panel")).toHaveCount(0);

    await expect(rows.last()).toBeVisible();
    await expect.poll(() => scroller.evaluate((el) => el.scrollTop)).toBe(before);
  });
});

/**
 * The in-page drawer overlays the live page (no separate backdrop element);
 * a click on blank chrome (topbar centre) dismisses it.
 */
async function dismissByBlankClick(page: Page) {
  await page.mouse.click(700, 20);
  await expect(page.getByTestId("item-panel")).toHaveCount(0);
}

/** Record whether the list/board loading node is ever mounted from now on. */
async function watchLoading(page: Page, loadingTestId: string) {
  await page.evaluate((testId) => {
    const w = window as typeof window & {
      __listLoadingSeen?: boolean;
      __listObserver?: MutationObserver;
    };
    w.__listLoadingSeen = false;
    const check = () => {
      if (document.querySelector(`[data-testid="${testId}"]`)) {
        w.__listLoadingSeen = true;
      }
    };
    check();
    w.__listObserver = new MutationObserver(check);
    w.__listObserver.observe(document.body, { childList: true, subtree: true });
  }, loadingTestId);
}

async function listingLoading(page: Page): Promise<boolean> {
  return page.evaluate(
    () => (window as typeof window & { __listLoadingSeen?: boolean }).__listLoadingSeen ?? false,
  );
}
