import { expect, test } from "../support/fixtures";

// RDM-168: the drawer header offers a refresh action that reloads this
// drawer's data without closing the panel or touching the list behind it.
test("header refresh reloads this drawer's data", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  const item = await api.createItemIn(projectKey, {
    kind: "task",
    title: `refresh-${Date.now()}`,
    assignee: "alice",
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
  await page.getByTestId(`work-item-row-${item.display_id}`).click();
  const panel = page.getByTestId("item-panel");
  const title = page.getByTestId("item-panel-title");
  await expect(panel).toBeVisible();
  await expect(title).toContainText(item.title);

  // Out-of-band edit: nothing in the drawer pushes it, so only the explicit
  // refresh can surface the new title.
  const updated = `${item.title} (updated)`;
  await api.request("PATCH", `/work-items/${item.id}`, {
    row_version: item.row_version,
    title: updated,
  });
  await expect(title).toContainText(item.title);

  await page.getByTestId("item-panel-refresh").click();
  await expect(title).toContainText(updated);
  await expect(panel).toBeVisible();
});
