import { expect, test } from "../support/fixtures";
import { beginInlineEdit, openItem } from "../support/ui";

// RDM-174: Escape inside an inline field editor must not cancel the edit.
// IME candidate windows swallow Escape, and treating it as "cancel" discarded
// the draft. The drawer underneath must stay open as well.
test("Escape keeps the inline editor and the drawer open", async ({
  api,
  app,
  page,
}) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  const task = await api.createItemIn(projectKey, {
    kind: "task",
    title: `esc-inline-${Date.now()}`,
    assignee: "alice",
  });

  await openItem(page, app, task, projectKey);
  await beginInlineEdit(page, "item-est-work-hours");

  const input = page.getByTestId("item-est-work-hours-input");
  await expect(input).toBeVisible();
  await input.fill("1.5");

  await page.keyboard.press("Escape");

  await expect(input).toBeVisible();
  await expect(input).toHaveValue("1.5");
  await expect(page.getByTestId("item-est-work-hours-save")).toBeVisible();
  await expect(page.getByTestId("item-panel")).toBeVisible();

  // Explicit cancel still exits, and the escape above saved nothing.
  await page.getByTestId("item-est-work-hours-cancel").click();
  await expect(input).toBeHidden();
  await expect(page.getByTestId("item-est-work-hours")).not.toContainText("1.5");
});
