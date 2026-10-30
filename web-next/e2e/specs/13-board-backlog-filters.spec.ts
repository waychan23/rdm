import { expect, test } from "../support/fixtures";
import { boardPath } from "../support/ui";

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
