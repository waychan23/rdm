import { expect, test } from "../support/fixtures";
import { boardPath } from "../support/ui";
import type { Api, Item } from "../support/api";

/** A plain task (task_standard) reaches DONE through two direct steps. */
async function completeTask(api: Api, item: Item): Promise<void> {
  for (const to of ["IN_PROGRESS", "DONE"]) {
    const fresh = await api.getItem(item.display_id, "alice");
    await api.post(
      `/work-items/${item.display_id}/transition`,
      { to, row_version: fresh.data.row_version },
      "alice",
    );
  }
}

test.describe("backlog filters and board terminal columns", () => {
  test("multi-kind filter shows only the selected kinds", async ({ api, app, page }) => {
    const stamp = Date.now();
    const story = await api.createItem({ kind: "story", title: `filter-story-${stamp}` });
    const issue = await api.createItem({ kind: "issue", title: `filter-issue-${stamp}` });

    await page.goto(`${app.baseURL}/projects/${app.projectKey}/backlog`);
    await expect(page.getByTestId("page-backlog")).toBeVisible();
    await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toBeVisible();
    await expect(page.getByTestId(`work-item-row-${issue.display_id}`)).toBeVisible();

    // Only story: the issue row must disappear.
    await page.getByRole("checkbox", { name: "Epic" }).click();
    await page.getByRole("checkbox", { name: "缺陷" }).click();
    await page.getByRole("checkbox", { name: "任务" }).click();
    await expect(page.getByRole("checkbox", { name: "需求" })).toBeChecked();
    await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toBeVisible();
    await expect(page.getByTestId(`work-item-row-${issue.display_id}`)).toHaveCount(0);

    // Story + issue: both kinds travel in one request (kind=story,issue).
    await page.getByRole("checkbox", { name: "缺陷" }).click();
    await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toBeVisible();
    await expect(page.getByTestId(`work-item-row-${issue.display_id}`)).toBeVisible();
  });

  test("completed filter narrows the list to terminal states (RDM-45)", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const done = await api.createItemIn(projectKey, {
      kind: "task",
      title: `completed-${stamp}`,
      assignee: "alice",
    });
    const open = await api.createItemIn(projectKey, {
      kind: "task",
      title: `open-${stamp}`,
      assignee: "alice",
    });
    await completeTask(api, done);

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
    const doneRow = page.getByTestId(`work-item-row-${done.display_id}`);
    const openRow = page.getByTestId(`work-item-row-${open.display_id}`);
    await expect(doneRow).toBeVisible();
    await expect(openRow).toBeVisible();

    const filter = page.getByTestId("work-item-filter-completed");
    await filter.getByRole("combobox").click();
    await page.getByRole("option", { name: "已完结", exact: true }).click();
    await expect(page).toHaveURL(/completed=true/);
    await expect(doneRow).toBeVisible();
    await expect(openRow).toHaveCount(0);

    await filter.getByRole("combobox").click();
    await page.getByRole("option", { name: "未完结", exact: true }).click();
    await expect(page).toHaveURL(/completed=false/);
    await expect(openRow).toBeVisible();
    await expect(doneRow).toHaveCount(0);
  });

  test("list sorts by creation time, newest first by default (RDM-46)", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const older = await api.createItemIn(projectKey, { kind: "task", title: `older-${stamp}` });
    const newer = await api.createItemIn(projectKey, { kind: "task", title: `newer-${stamp}` });

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
    const rows = page.locator('[data-testid^="work-item-row-"]');
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0)).toHaveAttribute(
      "data-testid",
      `work-item-row-${newer.display_id}`,
    );

    const sort = page.getByTestId("work-item-filter-order");
    await sort.getByRole("combobox").click();
    await page.getByRole("option", { name: "创建时间（旧→新）", exact: true }).click();
    await expect(page).toHaveURL(/order=created_asc/);
    await expect(rows.nth(0)).toHaveAttribute(
      "data-testid",
      `work-item-row-${older.display_id}`,
    );
  });

  test("the issues entry pins the list to issue kind (RDM-47)", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const story = await api.createItemIn(projectKey, { kind: "story", title: `s-${stamp}` });
    const issue = await api.createItemIn(projectKey, { kind: "issue", title: `i-${stamp}` });

    await page.goto(`${app.baseURL}/projects/${projectKey}/issues`);
    await expect(page.getByTestId("page-backlog")).toBeVisible();
    await expect(page.getByRole("heading", { name: "缺陷" })).toBeVisible();
    await expect(page.getByTestId(`work-item-row-${issue.display_id}`)).toBeVisible();
    await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toHaveCount(0);
    // The kind filter is hidden on the issues page.
    await expect(page.getByTestId("work-item-filter-kind-issue")).toHaveCount(0);
    await expect(page.getByTestId("rail-item-project-issues")).toHaveAttribute(
      "aria-current",
      "page",
    );

    // Opening an item keeps the issue-only background list.
    await page.getByTestId(`work-item-row-${issue.display_id}`).click();
    await expect(page.getByTestId("item-panel")).toBeVisible();
    await expect(page.getByTestId(`work-item-row-${issue.display_id}`)).toBeVisible();
    await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toHaveCount(0);
  });

  test("board terminal-column toggle actually hides terminal columns", async ({ app, page }) => {
    await page.goto(`${app.baseURL}${boardPath(app)}`);
    await expect(page.getByTestId("page-board")).toBeVisible();
    await expect(page.getByTestId("board-column-DONE")).toBeVisible();

    await page.getByRole("checkbox", { name: "显示终态列" }).click();
    await expect(page.getByTestId("board-column-DONE")).toHaveCount(0);

    await page.getByRole("checkbox", { name: "显示终态列" }).click();
    await expect(page.getByTestId("board-column-DONE")).toBeVisible();
  });
});
