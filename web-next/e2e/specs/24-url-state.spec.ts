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

    const kindFilter = page.getByTestId("work-item-filter-kind");
    for (const name of ["缺陷", "任务"]) {
      await kindFilter.getByRole("combobox").click();
      await page.getByRole("option", { name, exact: true }).click();
    }
    await expect(page).toHaveURL(/kind=story/);

    await page.getByTestId(`work-item-row-${story.display_id}`).click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(story.display_id);
    await page.goBack();

    await expect(page).toHaveURL(/kind=story/);
    await expect(page.getByTestId("work-item-filter-kind")).toContainText("需求");
    await expect(page.getByTestId("work-item-filter-kind")).not.toContainText("缺陷");
    await expect(page.getByTestId("work-item-search")).toHaveValue(story.title);
    await expect(page.getByTestId("work-item-filter-kind")).not.toContainText("任务");
  });

  test("search box accepts a work item display id (RDM-88)", async ({
    api,
    app,
    page,
  }) => {
    const story = await api.createItem({
      kind: "story",
      title: `id-search-${Date.now()}`,
    });
    const bareId = story.display_id.split("-").pop()!;
    await page.goto(`${app.baseURL}/projects/${app.projectKey}/backlog`);

    await page.getByTestId("work-item-search").fill(story.display_id);
    await page.getByTestId("work-item-search").press("Enter");
    await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toBeVisible();

    await page.getByTestId("work-item-search").fill(bareId);
    await page.getByTestId("work-item-search").press("Enter");
    await expect(page.getByTestId(`work-item-row-${story.display_id}`)).toBeVisible();
  });

  test("the list behind an open drawer keeps its filters (RDM-51)", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `drawer-filter-${stamp}`,
    });
    await api.createItemIn(projectKey, { kind: "issue", title: `drawer-filter-issue-${stamp}` });

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
    await page.getByTestId("work-item-search").fill(story.title);
    await page.getByTestId("work-item-search").press("Enter");
    // Story only: issue and task go unchecked in the kind multi-select.
    const kindFilter = page.getByTestId("work-item-filter-kind");
    for (const name of ["缺陷", "任务"]) {
      await kindFilter.getByRole("combobox").click();
      await page.getByRole("option", { name, exact: true }).click();
    }
    await expect(page).toHaveURL(/kind=story/);
    const row = page.getByTestId(`work-item-row-${story.display_id}`);
    await expect(row).toBeVisible();

    await row.click();
    await expect(page.getByTestId("item-panel")).toBeVisible();

    // The list still rendered behind the drawer keeps the query and filters.
    await expect(page.getByTestId("work-item-search")).toHaveValue(story.title);
    await expect(page.getByTestId("work-item-filter-kind")).toContainText("需求");
    await expect(page.getByTestId("work-item-filter-kind")).not.toContainText("缺陷");
    await expect(row).toBeVisible();

    await page.getByTestId("item-backdrop").click({ position: { x: 12, y: 12 } });
    await expect(page.getByTestId("item-panel")).toHaveCount(0);
    await expect(page).toHaveURL(/kind=story/);
    await expect(page.getByTestId("work-item-search")).toHaveValue(story.title);
  });

  test("board, mailbox and inbox read their controls from the URL", async ({
    app,
    page,
  }) => {
    await page.goto(`${app.baseURL}/projects/${app.projectKey}/board`);
    // Kinds are a multi-select; leaving only story writes kind=story.
    const kindFilter = page.getByTestId("work-item-filter-kind");
    await kindFilter.getByRole("combobox").click();
    await page.getByRole("option", { name: "缺陷", exact: true }).click();
    // Atlaskit closes the multi menu after each pick.
    await kindFilter.getByRole("combobox").click();
    await page.getByRole("option", { name: "任务", exact: true }).click();
    await expect(page).toHaveURL(/kind=story/);
    await page.reload();
    await expect(page).toHaveURL(/kind=story/);
    await expect(page.getByTestId("work-item-filter-kind")).toContainText("需求");
    await expect(page.getByTestId("work-item-filter-kind")).not.toContainText("缺陷");

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
