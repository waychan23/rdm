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

    // The click marks it read, so the unread-only inbox is empty again.
    await page.goto(`${app.baseURL}/inbox`);
    await expect(page.getByTestId("inbox-empty")).toBeVisible();

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
    await expect(page.getByTestId("inbox-empty")).toBeVisible();
  });
});
