import { expect, test } from "../support/fixtures";
import {
  activeStep,
  confirmStepExecution,
  expectStatus,
  expectSuccessNotice,
  openItem,
  selectExecutors,
  startStepThroughDialog,
  waitForItemStatus,
} from "../support/ui";

test.describe("workflow: reassign executors", () => {
  test("the assignee can replace a pending executor before anyone executes", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `reassign-${Date.now()}`,
      assignee: "alice",
      reviewer: ["bob", "carol"],
      review_content_md: "ready",
      status: "TO_REVIEW",
    });

    const alice = await asUser("alice");
    await openItem(alice, app, item);
    await startStepThroughDialog(alice, "CODE_REVIEW", ["alice"]);

    const card = await activeStep(alice);
    await expect(card).toContainText("PENDING");

    // Reassignment is a PENDING-only action of the current assignee.
    await alice.getByTestId("step-active-reassign").click();
    await expect(alice.getByTestId("step-start-dialog")).toContainText("改派执行人");
    await selectExecutors(alice, ["bob"]);
    await alice.getByTestId("step-start-confirm").click();

    await expectSuccessNotice(alice, "执行人已更新");
    await expect(card).toContainText("bob");
    await expect(card).toContainText("CANCELLED");
    await expect(card).toContainText("PENDING");
    // The removed executor loses the execute button.
    await expect(alice.getByTestId("step-active-execute")).toHaveCount(0);

    // The new executor can finish the step and transition the item.
    const bob = await asUser("bob");
    await openItem(bob, app, item);
    await bob.getByTestId("step-active-execute").click();
    await confirmStepExecution(bob, "bob approves after reassignment");

    await expectStatus(bob, "DONE");
    await waitForItemStatus(api, item, "DONE");
  });
});
