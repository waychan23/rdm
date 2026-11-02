import { expect, test } from "../support/fixtures";

// RDM-99: opening a work item from inbox/mailbox must keep that page as the
// drawer backdrop instead of replacing it with the backlog.
test.describe("drawer backdrop follows the opening page", () => {
  test("inbox stays behind the drawer", async ({ api, app, asUser }) => {
    const item = await api.createItem({
      kind: "task",
      title: `backdrop-inbox-${Date.now()}`,
    });
    await api.post(`/work-items/${item.display_id}/assign`, {
      member: api.userId("alice"),
    });

    const page = await asUser("alice");
    await page.goto(`${app.baseURL}/inbox`);
    await expect(page.getByTestId("page-inbox")).toBeVisible();

    await page.getByText(`你被指派了 ${item.display_id}`).click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(item.display_id);

    // The inbox, not the backlog, is rendered behind the drawer.
    await expect(page.getByTestId("page-inbox")).toBeVisible();
    await expect(page.getByTestId("page-backlog")).toHaveCount(0);

    await page.getByTestId("item-backdrop").click({ position: { x: 12, y: 12 } });
    await expect(page.getByTestId("item-panel")).toHaveCount(0);
    await expect(page).toHaveURL(`${app.baseURL}/inbox`);
  });

  test("project mailbox stays behind the drawer", async ({ api, app, asUser }) => {
    const item = await api.createItem({
      kind: "task",
      title: `backdrop-mailbox-${Date.now()}`,
    });
    await api.post(
      `/projects/${app.projectKey}/messages`,
      {
        to: ["alice"],
        subject: `backdrop-mail-${Date.now()}`,
        body_md: "请查看相关工作项",
        refs: [item.display_id],
      },
      "owner",
    );

    const page = await asUser("alice");
    await page.goto(`${app.baseURL}/projects/${app.projectKey}/mailbox`);
    await expect(page.getByTestId("page-mailbox")).toBeVisible();

    await page.getByTestId(`mailbox-item-ref-${item.display_id}`).click();
    await expect(page.getByTestId("item-panel-display-id")).toHaveText(item.display_id);

    await expect(page.getByTestId("page-mailbox")).toBeVisible();
    await expect(page.getByTestId("page-backlog")).toHaveCount(0);

    await page.getByTestId("item-backdrop").click({ position: { x: 12, y: 12 } });
    await expect(page.getByTestId("item-panel")).toHaveCount(0);
    await expect(page).toHaveURL(
      `${app.baseURL}/projects/${app.projectKey}/mailbox`,
    );
  });
});
