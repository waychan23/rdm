import { expect, test } from "../support/fixtures";
import { openItem } from "../support/ui";

test.describe("enum labels", () => {
  test("roles and statuses are shown in Chinese", async ({ api, app, page }) => {
    const item = await api.createItem({ kind: "task", title: `labels-${Date.now()}` });

    await page.goto(`${app.baseURL}/projects/${app.projectKey}/members`);
    await expect(page.getByTestId("page-members")).toBeVisible();
    await expect(page.getByText("项目经理").first()).toBeVisible();
    await expect(page.getByText("worker", { exact: true })).toHaveCount(0);

    await openItem(page, app, item);
    await expect(
      page.getByTestId("item-field-status").getByTestId("status-lozenge-TODO"),
    ).toHaveText("待办");
    await expect(page.getByTestId("item-section-metadata")).not.toContainText("task ·");
  });
});
