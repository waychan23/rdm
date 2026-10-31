import { expect, test } from "../support/fixtures";

test.describe("URL-backed filter state", () => {
  test("backlog filters survive opening an item and going back", async ({
    api,
    app,
    page,
  }) => {
    const story = await api.createItem({
      kind: "story",
      title: `url-state-${Date.now()}`,
    });
    await page.goto(`${app.baseURL}/projects/${app.projectKey}/backlog`);
    await page.getByTestId("work-item-search").fill(story.title);
    await page.getByTestId("work-item-search").press("Enter");
    await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toBeVisible();

    await page.getByRole("checkbox", { name: "Epic" }).click();
    await page.getByRole("checkbox", { name: "缺陷" }).click();
    await page.getByRole("checkbox", { name: "任务" }).click();
    await expect(page).toHaveURL(/kind=story/);

    await page.getByTestId(`work-item-row-${story.display_id}`).click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(story.display_id);
    await page.goBack();

    await expect(page).toHaveURL(/kind=story/);
    await expect(page.getByRole("checkbox", { name: "需求" })).toBeChecked();
    await expect(page.getByRole("checkbox", { name: "Epic" })).not.toBeChecked();
    await expect(page.getByTestId("work-item-search")).toHaveValue(story.title);
    await expect(page.getByRole("checkbox", { name: "任务" })).not.toBeChecked();
  });

  test("board, mailbox and inbox read their controls from the URL", async ({
    app,
    page,
  }) => {
    await page.goto(`${app.baseURL}/projects/${app.projectKey}/board`);
    await page.getByTestId("board-kind-story").click();
    await page.getByRole("checkbox", { name: "显示终态列" }).click();
    await expect(page).toHaveURL(/kind=story/);
    await expect(page).toHaveURL(/showTerminal=false/);
    await page.reload();
    await expect(page).toHaveURL(/kind=story/);
    await expect(page.getByRole("checkbox", { name: "显示终态列" })).not.toBeChecked();

    await page.goto(`${app.baseURL}/projects/${app.projectKey}/mailbox`);
    await page.getByTestId("mailbox-folder-archived").click();
    await page.locator("#mailbox-sort").click();
    await page.locator("#mailbox-sort").fill("最早在前");
    await page.locator("#mailbox-sort").press("Enter");
    await page.getByTestId("mailbox-view-thread").click();
    await expect(page).toHaveURL(/folder=archived/);
    await expect(page).toHaveURL(/order=asc/);
    await expect(page).toHaveURL(/view=thread/);
    await page.reload();
    await expect(page).toHaveURL(/folder=archived/);
    await expect(page).toHaveURL(/order=asc/);

    await page.goto(`${app.baseURL}/inbox`);
    await page.getByRole("checkbox", { name: "只看未读" }).click();
    await page.getByTestId("inbox-tab-todo").click();
    await expect(page).toHaveURL(/tab=todo/);
    await expect(page).toHaveURL(/unread=false/);
    await page.reload();
    await expect(page.getByTestId("inbox-todo")).toBeVisible();
    await page.getByTestId("inbox-tab-notifications").click();
    await expect(page.getByRole("checkbox", { name: "只看未读" })).not.toBeChecked();
  });
});
