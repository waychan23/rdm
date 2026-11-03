import { expect, test } from "../support/fixtures";
import { confirmStepExecution } from "../support/ui";

/**
 * RDM-150: a covered drawer keeps update events queued; revealing it
 * batch-processes them, and closing the last layer refreshes the list behind.
 */
test("queued work item updates refresh the revealed drawer and the list", async ({
  api,
  app,
  asUser,
}) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  const story = await api.createItemIn(projectKey, {
    kind: "story",
    title: `event-story-${stamp}`,
    assignee: "alice",
  });
  const child = await api.createItemIn(projectKey, {
    kind: "task",
    task_type: "testing",
    title: `event-child-${stamp}`,
    parent: story.display_id,
    assignee: "alice",
  });

  const page = await asUser("alice");
  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
  await page.getByTestId(`work-item-row-${story.display_id}`).click();

  const visibleChildren = page.locator('[data-testid="item-panel-children"]:visible');
  await expect(
    visibleChildren.getByText(child.display_id, { exact: true }),
  ).toBeVisible();
  await expect(visibleChildren.getByTestId("status-lozenge-TODO")).toBeVisible();

  // Drill into the child and advance it; the parent is covered meanwhile.
  await visibleChildren.getByText(child.display_id, { exact: true }).click();
  const visiblePanel = page.locator('[data-testid="item-panel"]:visible');
  await expect(visiblePanel.getByTestId("item-panel-display-id")).toHaveText(
    child.display_id,
  );
  await visiblePanel.getByTestId("item-field-steps").getByTestId("item-step-START").click();
  await confirmStepExecution(page);
  await expect(visiblePanel.getByTestId("status-lozenge-IN_PROGRESS")).toBeVisible();

  // Going back reveals the parent, which drains the queued event and reloads.
  await page.locator('[data-testid="item-panel-back"]:visible').click();
  await expect(page.locator('[data-testid="item-panel-display-id"]:visible')).toHaveText(
    story.display_id,
  );
  await expect(visibleChildren.getByTestId("status-lozenge-IN_PROGRESS")).toBeVisible();

  // Closing the last layer makes the list drain its queue and revalidate.
  await page.locator('[data-testid="item-panel-close"]:visible').click();
  await expect(page.getByTestId("item-panel")).toHaveCount(0);
  const childRow = page.getByTestId(`work-item-row-${child.display_id}`);
  await expect(childRow).toBeVisible();
  await expect(childRow.getByTestId("status-lozenge-IN_PROGRESS")).toBeVisible();
});
