import { expect, test } from "../support/fixtures";

// RDM-64: people in the drawer show display_name (falling back to name).
test("drawer people fields use display names", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  const aliceId = api.userId("alice");
  await api.request("PATCH", `/users/${aliceId}`, { display_name: "爱丽丝" });
  const task = await api.createItemIn(projectKey, {
    kind: "task",
    title: `display-name-${Date.now()}`,
    assignee: "alice",
    participants: ["alice"],
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/items/${task.id}`);
  await expect(page.getByTestId("item-panel")).toBeVisible();
  await expect(page.getByTestId("item-field-assignee")).toContainText("爱丽丝");
  await expect(page.getByTestId("item-field-assignee")).not.toContainText("alice");
  await expect(page.getByTestId("item-field-participants")).toContainText("爱丽丝");
});
