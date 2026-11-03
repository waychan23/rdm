import { expect, test } from "../support/fixtures";

/** RDM-142: every bottom-start notice (success or error) auto-dismisses in 5s. */
test("error notice auto-dismisses without a manual click", async ({ browser, app }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  try {
    await page.goto(`${app.baseURL}/projects`);
    await expect(page.getByTestId("page-login")).toBeVisible({ timeout: 20_000 });

    await page.getByTestId("login-username").fill("owner");
    await page.getByTestId("login-password").fill("definitely-wrong");
    const started = Date.now();
    await page.getByTestId("login-submit").click();

    const notice = page.getByTestId("notice-error");
    await expect(notice).toBeVisible();
    await expect(notice).toBeHidden({ timeout: 8_000 });
    // Give the old (never-dismiss) behaviour no room to pass this test.
    expect(Date.now() - started).toBeGreaterThan(4_000);
  } finally {
    await context.close();
  }
});
