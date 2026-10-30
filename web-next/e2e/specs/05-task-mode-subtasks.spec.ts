import { expect, test } from "../support/fixtures";
import {
  activeStep,
  confirmStepExecution,
  expectStatus,
  openItem,
  startStepThroughDialog,
  stepButton,
  waitForItemStatus,
} from "../support/ui";

test.describe("workflow: task-mode step", () => {
  test("creates one subtype subtask per executor and completes the parent when the subtask is done", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `task-mode-${Date.now()}`,
      assignee: "alice",
      reviewer: ["bob"],
      review_content_md: "parent content",
      status: "TO_REVIEW",
    });

    const page = await asUser("alice");
    await openItem(page, app, item);
    await startStepThroughDialog(page, "CODE_REVIEW_TASKS", ["alice"]);

    const card = await activeStep(page);
    await expect(card).toContainText("执行进度 0/1");
    await expect(card).toContainText("任务式步骤");

    const subtaskLink = card.getByRole("button", { name: /子任务：/ });
    await expect(subtaskLink).toBeVisible();
    await expect(subtaskLink).toContainText(`Code Review: ${item.display_id}`);
    await subtaskLink.click();

    // The panel swapped to the generated code_review subtask (subtype workflow).
    await expect(page).toHaveURL(new RegExp(`/items/[^/]+$`));
    await expect(page.getByTestId("item-panel-loading")).toBeHidden();
    await expect(stepButton(page, "START")).toContainText("开始评审");
    await expect(page.getByTestId("item-custom-review_scope")).toBeVisible();

    // Drive the subtask through its subtype state graph to DONE.
    await stepButton(page, "START").click();
    await expect(page.getByTestId("step-execute-dialog")).toBeVisible();
    await confirmStepExecution(page);

    await expectStatus(page, "IN_PROGRESS");
    await stepButton(page, "SUBMIT").click();
    await confirmStepExecution(page);
    await expectStatus(page, "IN_REVIEW");

    await stepButton(page, "APPROVE").click();
    await expect(page.getByTestId("step-execute-dialog")).toBeVisible();
    await expect(page.getByTestId("step-execute-confirm")).toBeDisabled();
    await confirmStepExecution(page, "subtask approved");
    await expectStatus(page, "DONE");

    // The child reaching complete_on marks the parent executor DONE and the
    // parent step auto-completes (and passes the children_all_terminal gate).
    await openItem(page, app, item);
    await expectStatus(page, "DONE");
    await expect(page.getByTestId("active-step-card")).toHaveCount(0);
    await waitForItemStatus(api, item, "DONE");

    const detail = await api.getItem(item.id);
    expect(detail.data.status).toBe("DONE");
  });
});
