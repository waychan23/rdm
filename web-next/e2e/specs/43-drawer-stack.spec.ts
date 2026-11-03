import { expect, test } from "../support/fixtures";

/**
 * RDM-136: the in-page work item drawer keeps a stack of layers. Opening an
 * item from a panel pushes a layer; a duplicate open promotes the existing
 * layer instead of duplicating it; back/close and Escape act on one layer at a
 * time; deleting the current item must not close the panels below it.
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
  const first = await api.createItemIn(projectKey, {
    kind: "task",
    title: `stack-task-a-${stamp}`,
    parent: story.display_id,
    assignee: "alice",
  });
  const second = await api.createItemIn(projectKey, {
    kind: "task",
    title: `stack-task-b-${stamp}`,
    parent: story.display_id,
    assignee: "alice",
  });

  const visibleDisplayId = page.locator('[data-testid="item-panel-display-id"]:visible');
  const visibleChildren = page.locator('[data-testid="item-panel-children"]:visible');
  const visibleBack = page.locator('[data-testid="item-panel-back"]:visible');
  const visibleClose = page.locator('[data-testid="item-panel-close"]:visible');
  const openChild = (id: string) =>
    visibleChildren.getByText(id, { exact: true }).click();

  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
  await page.getByTestId(`work-item-row-${story.display_id}`).click();
  await expect(visibleDisplayId).toHaveText(story.display_id);

  // First layer: X closes the whole drawer.
  await expect(visibleClose).toBeVisible();
  await expect(visibleBack).toHaveCount(0);

  // Opening a child keeps the parent mounted underneath and shows a back arrow.
  await openChild(first.display_id);
  await expect(visibleDisplayId).toHaveText(first.display_id);
  await expect(page.getByTestId("item-panel")).toHaveCount(2);
  await expect(visibleBack).toBeVisible();
  await expect(visibleClose).toHaveCount(0);

  // Escape pops only the top layer (one press per layer).
  await page.keyboard.press("Escape");
  await expect(visibleDisplayId).toHaveText(story.display_id);
  await expect(page.getByTestId("item-panel")).toHaveCount(1);
  await expect(visibleClose).toBeVisible();

  // Re-open a child, then open an ancestor already in the stack: it is
  // promoted to the top instead of producing a duplicate layer.
  await openChild(second.display_id);
  await expect(visibleDisplayId).toHaveText(second.display_id);
  await page
    .locator(`[data-testid="item-panel-ancestor-${story.display_id}"]:visible`)
    .click();
  await expect(visibleDisplayId).toHaveText(story.display_id);
  await expect(page.getByTestId("item-panel")).toHaveCount(2);
  // Going back reveals the layer that was below after promotion (the child).
  await visibleBack.click();
  await expect(visibleDisplayId).toHaveText(second.display_id);

  // Copy is its own icon: clicking the ID text itself does not copy.
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.evaluate(() => navigator.clipboard.writeText("sentinel"));
  await visibleDisplayId.click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(
    "sentinel",
  );
  await page.locator('[data-testid="item-panel-copy-id"]:visible').click();
  await expect(page.getByTestId("notice-success")).toContainText(second.display_id);
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe(second.display_id);

  // Reopen the parent, then delete the other child: only its layer closes and
  // the parent stays open (and refreshes its children list).
  await visibleClose.click();
  await expect(page.getByTestId("item-panel")).toHaveCount(0);
  await page.getByTestId(`work-item-row-${story.display_id}`).click();
  await expect(visibleDisplayId).toHaveText(story.display_id);
  await openChild(first.display_id);
  await expect(visibleDisplayId).toHaveText(first.display_id);
  await page.locator('[data-testid="item-panel-delete"]:visible').click();
  const dialog = page.getByTestId("item-delete-dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("item-delete-dialog-confirm").click();

  await expect(visibleDisplayId).toHaveText(story.display_id);
  await expect(page.getByTestId("item-panel")).toHaveCount(1);
  await expect(visibleClose).toBeVisible();
  await expect(visibleChildren.getByText(first.display_id, { exact: true })).toHaveCount(0);
});
