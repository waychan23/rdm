import { expect, test } from "../support/fixtures";
import {
  activeStep,
  expectStatus,
  expectSuccessNotice,
  openItem,
  startStepThroughDialog,
  stepButton,
} from "../support/ui";

test.describe("workflow: cancel an active step", () => {
  test("cancelling keeps the item in place and lets the assignee start again", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `cancel-${Date.now()}`,
      assignee: "alice",
      reviewer: ["bob"],
      review_content_md: "ready",
      status: "TO_REVIEW",
    });

    const page = await asUser("alice");
    await openItem(page, app, item);
    await startStepThroughDialog(page, "CODE_REVIEW", ["alice"]);
    await activeStep(page);

    await page.getByTestId("step-active-cancel").click();
    await expect(page.getByTestId("step-cancel-dialog")).toBeVisible();
    await page.getByTestId("step-cancel-dialog-confirm").click();

    await expectSuccessNotice(page, "步骤已取消");
    await expectStatus(page, "TO_REVIEW");
    await expect(page.getByTestId("active-step-card")).toHaveCount(0);

    // The named step is offered again, and history records the cancellation.
    await expect(stepButton(page, "CODE_REVIEW")).toBeVisible();
    await page.getByTestId("item-history-toggle").click();
    await expect(page.getByTestId("item-history-list")).toContainText(
      "取消了步骤「Code Review」",
    );
  });
});
