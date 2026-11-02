import { expect, test } from "../support/fixtures";

// RDM-104/RDM-106: item lists outside the backlog show the work item type and
// their display ids open the work item drawer.
test.describe("work item type icons", () => {
  test("drawer child list shows the child type", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `child-type-story-${Date.now()}`,
    });
    const task = await api.createItemIn(projectKey, {
      kind: "task",
      title: `child-type-task-${Date.now()}`,
      parent: story.display_id,
    });

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
    await page.getByTestId(`work-item-row-${story.display_id}`).click();
    const children = page.getByTestId("item-panel-children");
    await expect(children).toBeVisible();
    await expect(children.getByTestId(`type-icon-${task.kind}`)).toBeVisible();
    await expect(children).toContainText(task.display_id);
  });

  test("sprint item rows show the type and open the drawer", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `sprint-type-story-${stamp}`,
    });
    const sprint = (
      await api.post<{ id: string }>(`/projects/${projectKey}/sprints`, {
        name: `type-sprint-${stamp}`,
      })
    ).data;
    await api.post(`/sprints/${sprint.id}/items`, { items: [story.display_id] });

    await page.goto(`${app.baseURL}/projects/${projectKey}/sprints`);
    await page.getByTestId(`sprint-row-${sprint.id}`).click();
    const row = page.getByTestId(`sprint-item-row-${story.display_id}`);
    await expect(row).toBeVisible();
    await expect(row.getByTestId("type-icon-story")).toBeVisible();

    await page.getByTestId(`sprint-item-open-${story.display_id}`).click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(story.display_id);
    // The sprint page stays behind the drawer (RDM-99 regression guard).
    await expect(page.getByTestId("page-sprints")).toBeVisible();
    await expect(page.getByTestId("page-backlog")).toHaveCount(0);
  });

  test("release item rows show the type and open the drawer", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `release-type-story-${stamp}`,
    });
    const release = (
      await api.post<{ id: string }>(`/projects/${projectKey}/releases`, {
        name: `type-release-${stamp}`,
      })
    ).data;
    await api.post(`/releases/${release.id}/items`, { items: [story.display_id] });

    await page.goto(`${app.baseURL}/projects/${projectKey}/releases`);
    await page.getByText(`type-release-${stamp}`).click();
    const row = page.getByTestId(`release-item-row-${story.display_id}`);
    await expect(row).toBeVisible();
    await expect(row.getByTestId("type-icon-story")).toBeVisible();

    await page.getByTestId(`release-item-open-${story.display_id}`).click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(story.display_id);
    await expect(page.getByTestId("page-releases")).toBeVisible();
    await expect(page.getByTestId("page-backlog")).toHaveCount(0);
  });

  test("work item filters use two rows with a clear sprint placeholder", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    await api.createItemIn(projectKey, {
      kind: "story",
      title: `filters-rows-${Date.now()}`,
    });

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
    const primary = page.getByTestId("work-item-filters");
    const secondary = page.getByTestId("work-item-filters-secondary");
    await expect(primary).toBeVisible();
    await expect(secondary).toBeVisible();

    // High-frequency controls sit in the first row…
    for (const testId of [
      "work-item-search",
      "work-item-filter-sprint",
      "work-item-filter-kind",
      "work-item-filter-view",
      "work-item-filter-order",
      "work-item-toolbar-actions",
    ]) {
      await expect(primary.getByTestId(testId)).toBeVisible();
    }

    // …and deep filters in the second one.
    for (const testId of [
      "work-item-filter-status",
      "work-item-filter-completed",
      "work-item-filter-subtype",
      "work-item-filter-assignee",
      "work-item-filter-participant",
      "work-item-filter-has-children",
    ]) {
      await expect(secondary.getByTestId(testId)).toBeVisible();
    }
    await expect(
      secondary.getByRole("checkbox", { name: "仅一级工作项" }),
    ).toBeVisible();

    await expect(
      page.getByTestId("work-item-filter-sprint").getByText("选择迭代"),
    ).toBeVisible();
  });
});
