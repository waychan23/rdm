import { expect, test } from "../support/fixtures";

test.describe("inbox notifications", () => {
  test("assignment notification opens the item and can be marked read", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `inbox-${Date.now()}`,
    });
    await api.post(`/work-items/${item.display_id}/assign`, {
      member: api.userId("alice"),
    });

    const page = await asUser("alice");
    await page.goto(`${app.baseURL}/inbox`);
    await expect(page.getByTestId("page-inbox")).toBeVisible();
    const title = `你被指派了 ${item.display_id}`;
    await expect(page.getByText(title)).toBeVisible();

    await page.getByText(title).click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(item.display_id);

    // The click marks it read, so it leaves the unread-only inbox.
    await page.goto(`${app.baseURL}/inbox`);
    await expect(page.getByText(title)).toHaveCount(0);

    // A second assignment can be cleared with "mark all".
    const item2 = await api.createItem({
      kind: "task",
      title: `inbox-2-${Date.now()}`,
    });
    await api.post(`/work-items/${item2.display_id}/assign`, {
      member: api.userId("alice"),
    });
    await page.reload();
    await expect(page.getByText(`你被指派了 ${item2.display_id}`)).toBeVisible();
    await page.getByTestId("inbox-mark-all").click();
    await expect(page.getByText(`你被指派了 ${item2.display_id}`)).toHaveCount(0);
  });
});

test.describe("step notifications", () => {
  test("starting an approval step notifies its executor", async ({ api, app, asUser }) => {
    const task = await api.createItem({
      kind: "task",
      title: `step-notify-${Date.now()}`,
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
    const started = await api.post<typeof review>(
      `/work-items/${patched.display_id}/steps/CODE_REVIEW`,
      { row_version: patched.row_version, executors: ["bob"], note_md: null },
      "alice",
    );
    expect(started.data.status).toBe("TO_REVIEW");

    const page = await asUser("bob");
    await page.goto(`${app.baseURL}/inbox`);
    await expect(
      page.getByText(`步骤「Code Review」待你执行：${task.display_id}`),
    ).toBeVisible();
    await expect(page.getByText(task.title)).toBeVisible();
  });
});
