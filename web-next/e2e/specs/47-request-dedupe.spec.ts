import type { Page } from "@playwright/test";

import { expect, test } from "../support/fixtures";

/**
 * Confirmed duplicate-request bugs (StrictMode dev double-invoke excluded):
 * - /whoami was fetched by the router loader and again by AppShell on mount;
 * - a warm board visit loaded every column twice (cached workflow replaced by
 *   an identical server payload);
 * - member lists were fetched independently by every consumer, so reopening a
 *   form dialog re-requested the same project members.
 */
function requestCounts(page: Page): Map<string, number> {
  const counts = new Map<string, number>();
  page.on("request", (request) => {
    if (request.method() !== "GET") return;
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/v1/")) return;
    const key = `${url.pathname}${url.search}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  });
  return counts;
}

function matching(counts: Map<string, number>, pathname: string): number[] {
  return [...counts.entries()]
    .filter(([key]) => key.split("?")[0] === pathname)
    .map(([, count]) => count);
}

test("hard load fetches /whoami once", async ({ app, page }) => {
  const counts = requestCounts(page);
  await page.goto(`${app.baseURL}/projects/${app.projectKey}/backlog`);
  await expect(page.getByTestId("page-backlog")).toBeVisible();
  await page.waitForTimeout(500);

  expect(matching(counts, "/api/v1/whoami")).toEqual([1]);
});

test("returning to a warm board loads each column once", async ({ app, page }) => {
  await page.goto(`${app.baseURL}/projects/${app.projectKey}/board`);
  await expect(page.getByTestId("page-board")).toBeVisible();

  // Warm the pageCache snapshot, then leave and come back client-side.
  await page.getByTestId("rail-item-project-backlog").click();
  await expect(page.getByTestId("page-backlog")).toBeVisible();

  const counts = requestCounts(page);
  await page.getByTestId("rail-item-project-board").click();
  await expect(page.getByTestId("page-board")).toBeVisible();
  await page.waitForTimeout(1_000);

  const columnRequests = [...counts.entries()].filter(
    ([key]) =>
      key.split("?")[0] === `/api/v1/projects/${app.projectKey}/work-items` &&
      key.includes("status="),
  );
  expect(columnRequests.length).toBeGreaterThan(0);
  for (const [key, count] of columnRequests) {
    expect(count, key).toBe(1);
  }
});

test("sprint/release dialogs share one members fetch per project", async ({
  app,
  page,
}) => {
  await page.goto(`${app.baseURL}/projects/${app.projectKey}/sprints`);
  await expect(page.getByTestId("page-sprints")).toBeVisible();

  const membersPath = `/api/v1/projects/${app.projectKey}/members`;
  const counts = requestCounts(page);

  await page.getByTestId("sprint-create-button").click();
  await expect(page.getByTestId("sprint-form-dialog")).toBeVisible();
  await page.waitForTimeout(300);
  expect(matching(counts, membersPath)).toEqual([1]);

  // Reopen within the TTL: the shared loader serves the cached list.
  await page.getByTestId("sprint-form-cancel").click();
  await expect(page.getByTestId("sprint-form-dialog")).toBeHidden();
  await page.getByTestId("sprint-create-button").click();
  await expect(page.getByTestId("sprint-form-dialog")).toBeVisible();
  await page.waitForTimeout(300);
  expect(matching(counts, membersPath)).toEqual([1]);

  // The release dialog on another page reuses the same project cache.
  await page.getByTestId("sprint-form-cancel").click();
  await expect(page.getByTestId("sprint-form-dialog")).toBeHidden();
  await page.getByTestId("rail-item-project-releases").click();
  await expect(page.getByTestId("page-releases")).toBeVisible();
  await page.getByTestId("release-create-button").click();
  await expect(page.getByTestId("release-form-dialog")).toBeVisible();
  await page.waitForTimeout(300);
  expect(matching(counts, membersPath)).toEqual([1]);
});
