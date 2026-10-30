import { expect, test } from "../support/fixtures";
import {
  confirmStepExecution,
  expectStatus,
  expectSuccessNotice,
  openItem,
  stepButton,
  waitForItemStatus,
} from "../support/ui";

test.describe("workflow: direct step", () => {
  test("assignee executes the named START step and the item advances", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `direct-step-${Date.now()}`,
      assignee: "alice",
    });
    const page = await asUser("alice");
    await openItem(page, app, item);

    await expectStatus(page, "TODO");
    const start = stepButton(page, "START");
    await expect(start).toContainText("开始");
    await expect(start).toBeEnabled();
    await start.click();

    // direct mode executes immediately, so the note dialog (not the
    // executor-picker dialog) is shown.
    await expect(page.getByTestId("step-execute-dialog")).toBeVisible();
    await expect(page.getByTestId("step-start-dialog")).toBeHidden();
    await confirmStepExecution(page);

    await expectSuccessNotice(page, "步骤已执行");
    await expectStatus(page, "IN_PROGRESS");
    await waitForItemStatus(api, item, "IN_PROGRESS");

    // Audit trail is visible in the panel.
    await page.getByTestId("item-history-toggle").click();
    await expect(page.getByTestId("item-history-list")).toContainText(
      "步骤「开始」完成并流转",
    );
  });
});
