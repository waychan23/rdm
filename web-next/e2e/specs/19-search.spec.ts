import { expect, test } from "../support/fixtures";

test.describe("global search", () => {
  test("finds work items and comments and navigates to the item", async ({ api, app, page }) => {
    const stamp = Date.now();
    const item = await api.createItem({
      kind: "task",
      title: `搜索验收-${stamp}`,
      description_md: "支付网关超时",
    });
    await api.post(
      `/work-items/${item.display_id}/comments`,
      { body_md: "评论关键词 " + `支付网关-${stamp}` },
      "owner",
    );

    await page.goto(`${app.baseURL}/search`);
    await expect(page.getByTestId("page-search")).toBeVisible();
    await page.getByTestId("search-input").fill(`搜索验收-${stamp}`);
    await page.getByTestId("search-submit").click();
    await expect(page.getByTestId("search-results")).toContainText(item.display_id);
    await expect(page.getByTestId("search-results")).toContainText(`搜索验收-${stamp}`);

    await page.locator('[data-testid^="search-hit-work_item-"]').first().click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(item.display_id);

    // Comment body is searchable too.
    await page.goto(`${app.baseURL}/search?q=${encodeURIComponent(`支付网关-${stamp}`)}`);
    await expect(page.getByTestId("search-results")).toContainText("评论");
    await page.getByTestId("search-results").getByText(item.display_id).first().click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(item.display_id);

    await page.goto(`${app.baseURL}/search?q=${encodeURIComponent("绝对不存在-" + stamp)}`);
    await expect(page.getByTestId("search-empty")).toBeVisible();
  });
});
