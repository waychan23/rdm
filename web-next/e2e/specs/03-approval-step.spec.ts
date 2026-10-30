import { expect, test } from "../support/fixtures";
import {
  activeStep,
  confirmStepExecution,
  expectStatus,
  expectSuccessNotice,
  fillStepNote,
  openItem,
  startStepThroughDialog,
  waitForItemStatus,
} from "../support/ui";

test.describe("workflow: multi-executor approval step", () => {
  test("all assigned humans must submit before the item reaches DONE", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `approval-${Date.now()}`,
      assignee: "alice",
      reviewer: ["bob", "carol"],
      review_content_md: "e2e review content",
      status: "TO_REVIEW",
    });

    const alice = await asUser("alice");
    await openItem(alice, app, item);
    await expectStatus(alice, "TO_REVIEW");

    // assignee + 2 reviewers = 3 candidates; min/max does not auto-select,
    // so the initiator picks alice and bob.
    await startStepThroughDialog(alice, "CODE_REVIEW", ["alice", "bob"]);
    await expectSuccessNotice(alice, "已发起步骤「Code Review」");

    const card = await activeStep(alice);
    await expect(card).toContainText("执行进度 0/2");
    await expect(card).toContainText("alice");
    await expect(card).toContainText("bob");

    // First executor: the note is required by the workflow config.
    await alice.getByTestId("step-active-execute").click();
    await expect(alice.getByTestId("step-execute-dialog")).toBeVisible();
    const confirm = alice.getByTestId("step-execute-confirm");
    await expect(confirm).toBeDisabled();
    await fillStepNote(alice, "alice approves");
    await expect(confirm).toBeEnabled();
    await confirm.click();

    await expect(alice.getByTestId("step-execute-dialog")).toBeHidden();
    await expect(card).toContainText("执行进度 1/2");
    // Partial completion keeps the item in place.
    await expectStatus(alice, "TO_REVIEW");

    // A reviewer who was not assigned is not allowed to execute.
    const carol = await asUser("carol");
    await openItem(carol, app, item);
    await expect(carol.getByTestId("active-step-card")).toBeVisible();
    await expect(carol.getByTestId("step-active-execute")).toHaveCount(0);

    // Second executor completes the step and auto-transitions to DONE.
    const bob = await asUser("bob");
    await openItem(bob, app, item);
    await expect(bob.getByTestId("step-active-execute")).toBeVisible();
    await bob.getByTestId("step-active-execute").click();
    await confirmStepExecution(bob, "bob approves");

    await expectStatus(bob, "DONE");
    await expect(bob.getByTestId("active-step-card")).toHaveCount(0);
    await waitForItemStatus(api, item, "DONE");

    // Both notes land as step comments and are visible in the active card
    // history before it disappears; assert server state instead.
    const detail = await api.getItem(item.id);
    expect(detail.data.status).toBe("DONE");
  });
});
