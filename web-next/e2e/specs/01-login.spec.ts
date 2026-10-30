import { expect, test } from "../support/fixtures";
import { OWNER_PASSWORD } from "../support/api";

test.describe("browser authentication", () => {
  test("full OAuth login stores a browser token and lands on projects", async ({
    browser,
    app,
  }) => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    try {
      await page.goto(`${app.baseURL}/projects`);

      // No token: router guard -> /login -> /authorize -> login ticket form.
      await expect(page.getByTestId("page-login")).toBeVisible({ timeout: 20_000 });
      await page.getByTestId("login-username").fill("owner");
      await page.getByTestId("login-password").fill(OWNER_PASSWORD);
      await page.getByTestId("login-submit").click();

      // First-party client auto-approves; callback exchanges the code.
      await expect(page.getByTestId("page-projects")).toBeVisible({ timeout: 20_000 });
      await expect(page.getByTestId(`project-card-${app.projectKey}`)).toBeVisible();

      const access = await page.evaluate(() => localStorage.getItem("rdm.access"));
      expect(access).toBeTruthy();
      const me = await page.request.get(`${app.baseURL}/api/v1/whoami`, {
        headers: { Authorization: `Bearer ${access}` },
      });
      expect(me.ok()).toBe(true);
    } finally {
      await context.close();
    }
  });
});
