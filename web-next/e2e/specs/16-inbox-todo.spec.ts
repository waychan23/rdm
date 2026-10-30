import { expect, test } from "../support/fixtures";

test.describe("inbox todo tab", () => {
  test("shows assigned/overdue items and pending approvals", async ({ api, app, asUser }) => {
    const overdue = await api.createItem({
      kind: "task",
      title: `overdue-${Date.now()}`,
      assignee: "alice",
    });
    // Seed an overdue planned end date through the REST API.
    const detail = await api.getItem(overdue.display_id);
    await api.request(
      "PATCH",
      `/work-items/${overdue.display_id}`,
      { row_version: detail.data.row_version, planned_end_date: "2020-01-01" },
      "owner",
    );

    const alicePage = await asUser("alice");
    await alicePage.goto(`${app.baseURL}/inbox`);
    await alicePage.getByTestId("inbox-tab-todo").click();
    await expect(alicePage.getByTestId("inbox-todo")).toBeVisible();
    await expect(
      alicePage.getByTestId("todo-assigned").getByText(overdue.display_id),
    ).toBeVisible();
    await expect(
      alicePage.getByTestId("todo-overdue").getByText(overdue.display_id),
    ).toBeVisible();

    // Bob has an approval step waiting; it appears under both pending/approval.
    const task = await api.createItem({
      kind: "task",
      title: `approve-${Date.now()}`,
      assignee: "alice",
    });
    const review = await api.advanceTo(task, "TO_REVIEW", "alice");
    const patched = (
      await api.request<typeof review>(
        "PATCH",
        `/work-items/${review.display_id}`,
        {
          row_version: review.row_version,
          reviewer: ["bob"],
          review_content_md: "ok",
        },
        "alice",
      )
    ).data;
    await api.post(
      `/work-items/${patched.display_id}/steps/CODE_REVIEW`,
      { row_version: patched.row_version, executors: ["bob"], note_md: null },
      "alice",
    );

    const bobPage = await asUser("bob");
    await bobPage.goto(`${app.baseURL}/inbox`);
    await bobPage.getByTestId("inbox-tab-todo").click();
    await expect(bobPage.getByTestId("todo-approvals")).toContainText("Code Review");
    await expect(bobPage.getByTestId("todo-approvals")).toContainText(task.display_id);
  });
});
