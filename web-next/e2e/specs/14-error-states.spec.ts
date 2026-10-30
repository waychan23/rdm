import { expect, test } from "../support/fixtures";

test.describe("load failure surfaces a retryable error state", () => {
  test("overview and board show the API message instead of a blank/spinner", async ({
    app,
    page,
  }) => {
    const fail = (route: import("@playwright/test").Route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "INTERNAL_ERROR", message: "服务暂时不可用", details: {} },
        }),
      });

    await page.route("**/api/v1/projects/*/overview", fail);
    await page.goto(`${app.baseURL}/projects/${app.projectKey}`);
    await expect(page.getByTestId("overview-error")).toBeVisible();
    await expect(page.getByText("服务暂时不可用")).toBeVisible();
    await expect(page.getByRole("button", { name: "重试" })).toBeVisible();

    await page.unroute("**/api/v1/projects/*/overview");
    await page.route("**/api/v1/projects/*/work-items?*", fail);
    await page.goto(`${app.baseURL}/projects/${app.projectKey}/board`);
    await expect(page.getByTestId("board-error")).toBeVisible();
    await expect(page.getByText("服务暂时不可用")).toBeVisible();
  });
});
