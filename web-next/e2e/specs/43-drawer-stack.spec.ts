import { expect, test } from "../support/fixtures";

/**
 * RDM-136: the in-page work item drawer keeps a stack of layers. Opening an
 * item from a panel pushes a layer; a duplicate open promotes the existing
 * layer instead of duplicating it; the header shows back vs close depending on
 * whether more layers remain.
 */
test("drawer stack: drill in, go back, promote duplicates, copy display id", async ({
  api,
  app,
  page,
}) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  const epic = await api.createItemIn(projectKey, {
    kind: "epic",
    title: `stack-epic-${stamp}`,
  });
  const story = await api.createItemIn(projectKey, {
    kind: "story",
    title: `stack-story-${stamp}`,
    parent: epic.display_id,
  });
  const task = await api.createItemIn(projectKey, {
    kind: "task",
    title: `stack-task-${stamp}`,
    parent: story.display_id,
    assignee: "alice",
  });

  const visibleDisplayId = page.locator('[data-testid="item-panel-display-id"]:visible');
  const visibleChildren = page.locator('[data-testid="item-panel-children"]:visible');
  const visibleBack = page.locator('[data-testid="item-panel-back"]:visible');
  const visibleClose = page.locator('[data-testid="item-panel-close"]:visible');

  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
  await page.getByTestId(`work-item-row-${story.display_id}`).click();
  await expect(visibleDisplayId).toHaveText(story.display_id);

  // First layer: X closes the whole drawer.
  await expect(visibleClose).toBeVisible();
  await expect(visibleBack).toHaveCount(0);

  // Opening a child keeps the parent mounted underneath and shows a back arrow.
  await visibleChildren.getByText(task.display_id, { exact: true }).click();
  await expect(visibleDisplayId).toHaveText(task.display_id);
  await expect(page.getByTestId("item-panel")).toHaveCount(2);
  await expect(visibleBack).toBeVisible();
  await expect(visibleClose).toHaveCount(0);

  // Back pops only the top layer and restores the parent instantly.
  await visibleBack.click();
  await expect(visibleDisplayId).toHaveText(story.display_id);
  await expect(page.getByTestId("item-panel")).toHaveCount(1);
  await expect(visibleClose).toBeVisible();
  await expect(visibleBack).toHaveCount(0);

  // Re-open the child, then open an ancestor already in the stack: it is
  // promoted to the top instead of producing a duplicate layer.
  await visibleChildren.getByText(task.display_id, { exact: true }).click();
  await expect(visibleDisplayId).toHaveText(task.display_id);
  await page
    .locator(`[data-testid="item-panel-ancestor-${story.display_id}"]:visible`)
    .click();
  await expect(visibleDisplayId).toHaveText(story.display_id);
  await expect(page.getByTestId("item-panel")).toHaveCount(2);
  // Going back reveals the layer that was below after promotion (the child).
  await visibleBack.click();
  await expect(visibleDisplayId).toHaveText(task.display_id);

  // The current display id is a copy affordance.
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.locator('[data-testid="item-panel-copy-id"]:visible').click();
  await expect(page.getByTestId("notice-success")).toContainText(task.display_id);
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe(task.display_id);
});
