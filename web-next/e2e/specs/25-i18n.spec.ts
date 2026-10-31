import { expect, test } from "../support/fixtures";

test.describe("i18n", () => {
  test("topbar language switch re-renders and persists", async ({ app, page }) => {
    await page.goto(`${app.baseURL}/projects`);
    await expect(page.getByTestId("page-projects")).toBeVisible();
    await expect(page.getByTestId("rail-item-projects")).toContainText("项目");

    await page.getByText("简体中文", { exact: true }).click();
    await page.getByRole("option", { name: "English" }).click();

    await expect(page.getByTestId("rail-item-projects")).toContainText("Projects");
    await expect(page.getByRole("button", { name: "Search" })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("rdm.locale"))).toBe("en");
    expect(await page.evaluate(() => document.documentElement.lang)).toBe("en");

    await page.reload();
    await expect(page.getByTestId("rail-item-projects")).toContainText("Projects");

    await page.getByText("English", { exact: true }).click();
    await page.getByRole("option", { name: "简体中文" }).click();
    await expect(page.getByTestId("rail-item-projects")).toContainText("项目");
    expect(await page.evaluate(() => localStorage.getItem("rdm.locale"))).toBe("zh-CN");
  });

  test("members page title interpolates the project key", async ({ app, page }) => {
    await page.goto(`${app.baseURL}/projects/WFE2E/members`);
    const header = page.getByTestId("members-header");
    await expect(header).toBeVisible();
    await expect(header).toContainText("WFE2E");
    await expect(header).not.toContainText("{projectKey}");
  });
});
