import type { Page } from "@playwright/test";

import type { Api } from "../support/api";
import { expect, test } from "../support/fixtures";

// RDM-125: list pages are fixed to the viewport. The title, filter band and
// pager must not move or wrap; the table body owns the only vertical scrollbar
// and the shell itself never scrolls.
async function seed(api: Api, projectKey: string, kind: "task" | "issue") {
  const stamp = Date.now();
  for (let index = 0; index < 20; index += 1) {
    await api.createItemIn(projectKey, {
      kind,
      title: `fixed-list-${kind}-${stamp}-${index}`,
    });
  }
}

async function expectFixedList(page: Page, route: string) {
  await page.goto(route);
  await expect(page.getByTestId("app-content")).toBeVisible();
  const body = page.getByTestId("work-item-table-scroll");
  await expect(body.locator("tbody tr").first()).toBeVisible();

  // The page shell does not scroll; the table body does.
  const content = page.getByTestId("app-content");
  expect(await content.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(false);
  expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);

  // Scrolling the list leaves the title, filter band and pager in place.
  const chrome = [
    page.getByTestId("backlog-header"),
    page.getByTestId("work-item-filters"),
    page.getByTestId("work-item-pager"),
  ];
  const before = await Promise.all(chrome.map((locator) => locator.boundingBox()));
  await body.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  expect(await body.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  const after = await Promise.all(chrome.map((locator) => locator.boundingBox()));
  for (let index = 0; index < chrome.length; index += 1) {
    expect(after[index]!.y).toBeCloseTo(before[index]!.y, 0);
  }
}

test("work item list keeps its title, filters and pager fixed", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  await seed(api, projectKey, "task");
  await expectFixedList(page, `${app.baseURL}/projects/${projectKey}/backlog?view=flat`);
});

test("issue list keeps its title, filters and pager fixed", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  await seed(api, projectKey, "issue");
  await expectFixedList(page, `${app.baseURL}/projects/${projectKey}/issues?view=flat`);
});
