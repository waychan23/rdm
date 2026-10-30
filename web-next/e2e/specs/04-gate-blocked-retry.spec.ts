import type { Page } from "@playwright/test";

import { expect, test } from "../support/fixtures";
import {
  activeStep,
  beginInlineEdit,
  confirmStepExecution,
  expectStatus,
  openItem,
  startStepThroughDialog,
  waitForItemStatus,
} from "../support/ui";

test.describe("workflow: required-field gate", () => {
  test("prechecks on start, blocks on completion, and retry succeeds after the field is filled", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `gate-${Date.now()}`,
      assignee: "alice",
      reviewer: ["bob"],
      review_content_md: null,
      status: "TO_REVIEW",
    });

    const page = await asUser("alice");
    await openItem(page, app, item);

    // Starting with an empty required field is rejected before an active step
    // exists (WorkflowGateBlocked from the precheck).
    await startStepThroughDialog(page, "CODE_REVIEW", ["alice"]);
    await expect(page.getByTestId("item-panel-fields")).toContainText(
      "缺少必填字段：评审意见",
    );
    await expect(page.getByTestId("active-step-card")).toHaveCount(0);
    await expectStatus(page, "TO_REVIEW");

    await fillReviewContent(page, "first content");
    await startStepThroughDialog(page, "CODE_REVIEW", ["alice"]);
    const card = await activeStep(page);
    await expect(card).toContainText("执行进度 0/1");

    // Remove the field after the step started: the final executor now hits the
    // completion gate, which freezes the step as BLOCKED instead of DONE.
    await fillReviewContent(page, "");
    await card.getByTestId("step-active-execute").click();
    await confirmStepExecution(page, "approve without content");

    await expectStatus(page, "TO_REVIEW");
    await expect(card).toContainText("BLOCKED");
    await expect(page.getByTestId("item-panel-fields")).toContainText(
      "缺少必填字段：评审意见",
    );
    await expect(page.getByTestId("step-active-retry")).toBeVisible();
    expect((await api.getItem(item.id)).data.status).toBe("TO_REVIEW");

    // Fill the gated field again and retry: the same executor row is reused.
    await fillReviewContent(page, "reviewed in e2e");
    await page.getByTestId("step-active-retry").click();

    await expectStatus(page, "DONE");
    await expect(page.getByTestId("active-step-card")).toHaveCount(0);
    await waitForItemStatus(api, item, "DONE");
  });
});

async function fillReviewContent(page: Page, value: string) {
  await beginInlineEdit(page, "item-review-content");
  const editor = page.getByTestId("item-review-content-input");
  await expect(editor).toBeVisible();
  await editor.fill(value);
  await page.getByTestId("item-review-content-save").click();
  await expect(page.getByTestId("notice-success").filter({ hasText: "保存成功" }).first()).toBeVisible();
  await expect(page.getByTestId("item-review-content-input")).toBeHidden();
}
