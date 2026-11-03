import { expect, test } from "../support/fixtures";

// Escape must not discard a half-filled create form; the explicit Cancel
// action is the way out (CreateWorkItemDialog sets shouldCloseOnEscapePress=false).
test("create dialog ignores Escape and closes with Cancel", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
  await page.getByTestId("work-item-create-button").click();

  const dialog = page.getByTestId("work-item-create-dialog");
  await expect(dialog).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();

  await page.getByTestId("work-item-create-cancel").click();
  await expect(dialog).toBeHidden();
});
