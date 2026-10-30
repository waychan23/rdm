import { expect, test } from "../support/fixtures";
import { expectStatus, openItem } from "../support/ui";

test.describe("approval step rejection", () => {
  test("rejecting keeps the item status and notifies the assignee", async ({
    api,
    app,
    asUser,
  }) => {
    const task = await api.createItem({
      kind: "task",
      title: `reject-${Date.now()}`,
      assignee: "alice",
    });
    const review = await api.advanceTo(task, "TO_REVIEW", "alice");
    const patched = (
      await api.request<typeof review>(
        "PATCH",
        `/work-items/${review.display_id}`,
        { row_version: review.row_version, reviewer: ["bob"], review_content_md: "ok" },
        "alice",
      )
    ).data;
    await api.post(
      `/work-items/${patched.display_id}/steps/CODE_REVIEW`,
      { row_version: patched.row_version, executors: ["bob"], note_md: null },
      "alice",
    );

    const page = await asUser("bob");
    await openItem(page, app, patched);
    await expectStatus(page, "TO_REVIEW");
    await page.getByTestId("active-step-card").getByTestId("step-active-reject").click();
    await expect(page.getByTestId("step-reject-dialog")).toBeVisible();
    await page.getByTestId("step-reject-reason").fill("验收标准不满足");
    await page.getByTestId("step-reject-confirm").click();

    await expect(page.getByTestId("step-reject-dialog")).toBeHidden();
    await expect(page.getByTestId("active-step-card")).toHaveCount(0);
    await expectStatus(page, "TO_REVIEW");

    // The assignee sees a step rejection notification in their inbox.
    const alicePage = await asUser("alice");
    await alicePage.goto(`${app.baseURL}/inbox`);
    await expect(alicePage.getByText(`步骤「Code Review」被拒绝：${task.display_id}`)).toBeVisible();
  });
});
