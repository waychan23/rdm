import { expect, test } from "../support/fixtures";

// RDM-61: the drawer header shows the ancestor chain; ancestors are clickable,
// the current item is static.
test("drawer header breadcrumb navigates to ancestors", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  const epic = await api.createItemIn(projectKey, {
    kind: "epic",
    title: `breadcrumb-epic-${stamp}`,
  });
  const story = await api.createItemIn(projectKey, {
    kind: "story",
    title: `breadcrumb-story-${stamp}`,
    parent: epic.display_id,
  });
  const task = await api.createItemIn(projectKey, {
    kind: "task",
    title: `breadcrumb-task-${stamp}`,
    parent: story.display_id,
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/items/${task.id}`);
  await expect(page.getByTestId("item-panel")).toBeVisible();
  await expect(page.getByTestId("item-panel-display-id")).toHaveText(task.display_id);
  await expect(page.getByTestId(`item-panel-ancestor-${epic.display_id}`)).toBeVisible();
  await expect(page.getByTestId(`item-panel-ancestor-${story.display_id}`)).toBeVisible();

  // Ancestors open in the same panel; the current level becomes static.
  await page.getByTestId(`item-panel-ancestor-${story.display_id}`).click();
  await expect(page.getByTestId("item-panel-display-id")).toHaveText(story.display_id);
  await expect(page.getByTestId(`item-panel-ancestor-${story.display_id}`)).toHaveCount(0);
  await expect(page.getByTestId(`item-panel-ancestor-${epic.display_id}`)).toBeVisible();

  await page.getByTestId(`item-panel-ancestor-${epic.display_id}`).click();
  await expect(page.getByTestId("item-panel-display-id")).toHaveText(epic.display_id);
  await expect(page.getByTestId(`item-panel-ancestor-${epic.display_id}`)).toHaveCount(0);
});
