import { expect, test } from "../support/fixtures";

// RDM-162: Escape only pops the work item drawer when no dialog is open above
// it. The child-create dialog ignores Escape itself, so the key must stop at
// the dialog instead of closing the drawer underneath.
test("Escape with a child-create dialog open keeps both layers", async ({
  api,
  app,
  page,
}) => {
  const projectKey = await api.createSandboxProject();
  const parent = await api.createItemIn(projectKey, {
    kind: "task",
    title: `esc-dialog-${Date.now()}`,
    assignee: "alice",
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
  await page.getByTestId(`work-item-row-${parent.display_id}`).click();
  const panel = page.getByTestId("item-panel");
  await expect(panel).toBeVisible();

  await page.getByTestId("item-child-create").click();
  const dialog = page.getByTestId("work-item-create-dialog");
  await expect(dialog).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  await expect(panel).toBeVisible();

  // Closing the dialog returns Escape to the drawer.
  await page.getByTestId("work-item-create-cancel").click();
  await expect(dialog).toBeHidden();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});

// A blank click with a dialog open is an accidental backdrop hit, not a
// request to dismiss the drawer: the drawer stays put (the dialog may close
// through its own backdrop behaviour).
test("blank click with a child-create dialog open keeps the drawer", async ({
  api,
  app,
  page,
}) => {
  const projectKey = await api.createSandboxProject();
  const parent = await api.createItemIn(projectKey, {
    kind: "task",
    title: `blank-dialog-${Date.now()}`,
    assignee: "alice",
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
  await page.getByTestId(`work-item-row-${parent.display_id}`).click();
  const panel = page.getByTestId("item-panel");
  await expect(panel).toBeVisible();

  await page.getByTestId("item-child-create").click();
  await expect(page.getByTestId("work-item-create-dialog")).toBeVisible();

  await page.mouse.click(700, 20);
  await expect(panel).toBeVisible();
});
