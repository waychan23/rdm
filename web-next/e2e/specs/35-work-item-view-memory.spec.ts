import { expect, test } from "../support/fixtures";

// RDM-80: the board and the work item list share their filter state, and the
// sidebar re-opens each page with its remembered filters/pagination.
test("board and list sync filters across menu switches", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  const story = await api.createItemIn(projectKey, {
    kind: "story",
    title: `sync-parent-${stamp}`,
  });
  const child = await api.createItemIn(projectKey, {
    kind: "task",
    title: `sync-child-${stamp}`,
    parent: story.display_id,
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
  await expect(page.getByTestId("page-backlog")).toBeVisible();

  // Filter on the list.
  const listFilter = page.getByTestId("work-item-filter-has-children");
  await listFilter.getByRole("combobox").click();
  await page.getByRole("option", { name: "有子项", exact: true }).click();
  await expect(page).toHaveURL(/hasChildren=true/);

  // Switch to the board: it opens with the same filter applied.
  await page.getByTestId("rail-item-project-board").click();
  await expect(page).toHaveURL(/\/board\?hasChildren=true/);
  await expect(page.getByTestId("page-board")).toBeVisible();
  await expect(page.getByTestId("work-item-filter-has-children")).toContainText("有子项");

  // Change the filter on the board; the list inherits it on the way back.
  const boardFilter = page.getByTestId("work-item-filter-has-children");
  await boardFilter.getByRole("combobox").click();
  await page.getByRole("option", { name: "无子项", exact: true }).click();
  await expect(page).toHaveURL(/hasChildren=false/);

  await page.getByTestId("rail-item-project-backlog").click();
  await expect(page).toHaveURL(/\/backlog\?hasChildren=false/);
  await expect(page.getByTestId(`work-item-row-${child.display_id}`)).toBeVisible();
  await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toHaveCount(0);

  // Returning to the board re-applies its remembered query too.
  await page.getByTestId("rail-item-project-board").click();
  await expect(page).toHaveURL(/\/board\?hasChildren=false/);
  await expect(page.getByTestId("work-item-filter-has-children")).toContainText("无子项");

  // A deep link (no remembered query) still works and becomes the new state.
  await page.goto(`${app.baseURL}/projects/${projectKey}/board?hasChildren=true`);
  await expect(page.getByTestId("work-item-filter-has-children")).toContainText("有子项");
});

test("returning from another menu restores the list scroll position", async ({
  api,
  app,
  page,
}) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  for (let index = 0; index < 30; index += 1) {
    await api.createItemIn(projectKey, {
      kind: "task",
      title: `scroll-${stamp}-${index}`,
    });
  }

  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog?view=flat`);
  await expect(page.getByTestId("page-backlog")).toBeVisible();
  await expect(page.locator('[data-testid^="work-item-row-"]').first()).toBeVisible();
  const content = page.getByTestId("app-content");
  await content.evaluate((el) => {
    el.scrollTop = 200;
  });
  await expect
    .poll(() => content.evaluate((el) => el.scrollTop))
    .toBeGreaterThan(150);

  await page.getByTestId("rail-item-project-board").click();
  await expect(page.getByTestId("page-board")).toBeVisible();
  await page.getByTestId("rail-item-project-backlog").click();
  await expect(page.getByTestId("page-backlog")).toBeVisible();
  await expect(page.locator('[data-testid^="work-item-row-"]').first()).toBeVisible();
  // The menu target carries the remembered view mode; the data comes from the
  // page snapshot, so the restored offset is not clamped away by a spinner.
  await expect(page).toHaveURL(/view=flat/);
  await expect
    .poll(() => content.evaluate((el) => el.scrollTop))
    .toBeGreaterThan(150);
});
