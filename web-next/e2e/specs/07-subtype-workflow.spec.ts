import { expect, test } from "../support/fixtures";
import {
  beginInlineEdit,
  boardPath,
  confirmStepExecution,
  expectStatus,
  openItem,
  stepButton,
} from "../support/ui";

test.describe("workflow: task subtype (code_review)", () => {
  test("uses the subtype state graph, fields, and custom fields", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `subtype-${Date.now()}`,
      task_type: "code_review",
      assignee: "alice",
      custom_fields: {
        review_scope: "src/api",
        risk_score: 3,
        observers: [api.userId("bob")],
      },
    });

    const page = await asUser("alice");
    await openItem(page, app, item);

    // Subtype steps replace the base task steps.
    await expect(stepButton(page, "START")).toContainText("开始评审");
    await expect(page.getByTestId("item-step-SUBMIT_REVIEW")).toHaveCount(0);
    await expect(stepButton(page, "SUBMIT")).toHaveCount(0);

    // Subtype fields: reviewer/review_content plus declared custom fields.
    await expect(page.getByTestId("item-field-reviewer")).toBeVisible();
    await expect(page.getByTestId("item-field-review-content")).toBeVisible();
    await expect(page.getByTestId("item-custom-review_scope")).toBeVisible();
    await expect(page.getByTestId("item-custom-risk_score")).toBeVisible();
    await expect(page.getByTestId("item-custom-observers")).toBeVisible();

    // Dynamic custom field editing persists through a reload.
    await beginInlineEdit(page, "item-custom-risk_score");
    const riskInput = page.getByTestId("item-custom-risk_score-input");
    // Type instead of fill: the inline-edit form mounts its final-form field
    // asynchronously, and a synthetic value-set can race that subscription.
    await riskInput.click();
    await riskInput.press("ControlOrMeta+a");
    await riskInput.pressSequentially("7", { delay: 20 });
    await expect(riskInput).toHaveValue("7");
    await page.getByTestId("item-custom-risk_score-save").click();
    await expect(
      page.getByTestId("notice-success").filter({ hasText: "保存成功" }).first(),
    ).toBeVisible();
    await expect
      .poll(async () => (await api.getItem(item.id)).data.custom_fields?.risk_score)
      .toBe(7);
    await page.reload();
    await expect(page.getByTestId("item-panel-loading")).toBeHidden();
    await expect(page.getByTestId("item-custom-risk_score")).toContainText("7");

    // Board shows the union of base + subtype states (IN_REVIEW comes from the subtype).
    await page.goto(`${app.baseURL}${boardPath(app)}`);
    await expect(page.getByTestId("page-board")).toBeVisible();
    await expect(page.getByTestId("board-column-IN_REVIEW")).toBeVisible();
    await expect(page.getByTestId(`board-card-${item.display_id}`)).toBeVisible();

    // Walk the subtype graph: TODO -> IN_PROGRESS -> IN_REVIEW -> DONE.
    await openItem(page, app, item);
    await stepButton(page, "START").click();
    await confirmStepExecution(page);
    await expectStatus(page, "IN_PROGRESS");

    await stepButton(page, "SUBMIT").click();
    await confirmStepExecution(page);
    await expectStatus(page, "IN_REVIEW");

    await stepButton(page, "APPROVE").click();
    await expect(page.getByTestId("step-execute-confirm")).toBeDisabled();
    await confirmStepExecution(page, "approved");
    await expectStatus(page, "DONE");
  });
});
