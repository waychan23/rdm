import { expect, test } from "../support/fixtures";

test.describe("org-level mailbox", () => {
  test("opens outside a project, filters projects and groups threads", async ({
    api,
    app,
    asUser,
  }) => {
    const stamp = Date.now();
    await api.createProject("MAILX", "Mail X");
    await api.post(
      "/projects/MAILX/members",
      { user_id: api.userId("alice"), roles: ["worker"] },
      "owner",
    );
    const firstSubject = `A-DEMO-${stamp}`;
    const secondSubject = `B-MAILX-${stamp}`;
    const first = (
      await api.post(
        "/projects/WFE2E/messages",
        { to: ["alice"], subject: firstSubject, body_md: "第一个项目的信" },
        "owner",
      )
    ).data as { message_id: string };
    await api.post(
      "/projects/MAILX/messages",
      { to: ["alice"], subject: secondSubject, body_md: "第二个项目的信" },
      "owner",
    );
    await api.post(
      "/projects/WFE2E/messages",
      {
        to: ["alice"],
        subject: `Re: ${firstSubject}`,
        body_md: "回复",
        reply_to: first.message_id,
      },
      "owner",
    );

    const page = await asUser("alice");
    await page.goto(`${app.baseURL}/projects`);
    await page.getByTestId("topbar-mailbox").click();
    await expect(page).toHaveURL(/\/mailbox$/);
    await expect(page.getByTestId("page-mailbox")).toBeVisible();
    await expect(page.getByText(firstSubject, { exact: true })).toBeVisible();
    await expect(page.getByText(secondSubject)).toBeVisible();
    // No project filter: each row carries its project name.
    await expect(page.getByText("Workflow E2E").first()).toBeVisible();
    await expect(page.getByText("Mail X").first()).toBeVisible();

    // Filter to one project.
    await page.locator("#mailbox-project-filter").click();
    await page.locator("#mailbox-project-filter").fill("MAILX");
    await page.locator("#mailbox-project-filter").press("Enter");
    await expect(page.getByText(secondSubject)).toBeVisible();
    await expect(page.getByText(firstSubject, { exact: true })).toHaveCount(0);

    // Switch back to the first project and use thread view.
    await page.locator("#mailbox-project-filter").click();
    await page.locator("#mailbox-project-filter").fill("WFE2E");
    await page.locator("#mailbox-project-filter").press("Enter");
    await expect(page.getByText(firstSubject, { exact: true })).toBeVisible();
    await page.getByTestId("mailbox-view-thread").click();
    const thread = page
      .locator('[data-testid^="mailbox-thread-"]')
      .filter({ hasText: firstSubject })
      .first();
    await expect(thread).toContainText(firstSubject);
    await expect(thread).toContainText(`Re: ${firstSubject}`);
    const toggle = thread.locator('[data-testid^="mailbox-thread-toggle-"]');
    await toggle.click();
    await expect(toggle).toContainText("展开");
    await expect(thread.locator('[data-testid^="mailbox-item-"]')).toHaveCount(0);

    // Ascending/descending options are available and switchable.
    await page.getByTestId("mailbox-view-flat").click();
    await page.locator("#mailbox-sort").click();
    await page.locator("#mailbox-sort").fill("最早在前");
    await page.locator("#mailbox-sort").press("Enter");
    await expect(page.getByText(firstSubject, { exact: true })).toBeVisible();
  });
});
