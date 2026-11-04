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

      // No token: router guard -> /login -> /api/oauth/authorize -> login ticket form.
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

  test("an expired login ticket is renewed silently and the typed credentials are replayed", async ({
    browser,
    app,
  }) => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    let authorizeRequests = 0;
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === "/api/oauth/authorize") {
        authorizeRequests += 1;
      }
    });
    // Force the first submit to look like an expired ticket; the retry must go
    // through untouched. RDM-165.
    let rejectedOnce = false;
    await page.route("**/api/v1/auth/login", async (route) => {
      if (rejectedOnce) {
        await route.continue();
        return;
      }
      rejectedOnce = true;
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "VALIDATION_ERROR",
            message: "登录会话已过期，请重新登录",
            details: { field: "auth_key" },
          },
        }),
      });
    });
    try {
      await page.goto(`${app.baseURL}/projects`);

      await expect(page.getByTestId("page-login")).toBeVisible({ timeout: 20_000 });
      await page.getByTestId("login-username").fill("owner");
      await page.getByTestId("login-password").fill(OWNER_PASSWORD);
      await page.getByTestId("login-submit").click();

      // The form renewed the ticket itself; no second credential entry.
      await expect(page.getByTestId("page-projects")).toBeVisible({ timeout: 20_000 });
      expect(rejectedOnce).toBe(true);
      expect(authorizeRequests).toBeGreaterThanOrEqual(2);
      expect(await page.evaluate(() => localStorage.getItem("rdm.access"))).toBeTruthy();
    } finally {
      await context.close();
    }
  });
});
