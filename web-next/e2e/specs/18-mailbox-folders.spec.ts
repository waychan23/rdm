import { expect, test } from "../support/fixtures";

test.describe("mailbox folders, search and groups", () => {
  test("archive/unarchive, sent view and group mailbox management", async ({
    api,
    app,
    asUser,
  }) => {
    const subject = `预算确认-${Date.now()}`;
    await api.post(
      "/projects/WFE2E/messages",
      { to: ["alice"], subject, body_md: "请确认 Q4 预算" },
      "owner",
    );

    const alice = await asUser("alice");
    await alice.goto(`${app.baseURL}/projects/${app.projectKey}/mailbox`);
    await expect(alice.getByText(subject)).toBeVisible();

    // Search narrows the inbox.
    await alice.getByTestId("mailbox-search").fill("不存在的关键字");
    await alice.getByTestId("mailbox-search").press("Enter");
    await expect(alice.getByText(subject)).toHaveCount(0);
    await alice.getByTestId("mailbox-search").fill("预算");
    await alice.getByTestId("mailbox-search").press("Enter");
    await expect(alice.getByText(subject)).toBeVisible();

    // Archive moves it out of the inbox and into the archived folder.
    const row = alice
      .locator('[data-testid^="mailbox-item-"]')
      .filter({ hasText: subject });
    await alice.getByTestId("mailbox-search").fill("");
    await alice.getByTestId("mailbox-search").press("Enter");
    await expect(row).toBeVisible();
    await row.getByText("归档", { exact: true }).click();
    await expect(alice.getByText(subject)).toHaveCount(0);
    await alice.getByTestId("mailbox-folder-archived").click();
    await expect(alice.getByText(subject)).toBeVisible();
    await alice.getByText("移回收件箱", { exact: true }).click();
    await expect(alice.getByText(subject)).toHaveCount(0);
    await alice.getByTestId("mailbox-folder-inbox").click();
    await expect(alice.getByText(subject)).toBeVisible();

    // The sender's sent folder lists the recipient.
    const ownerPage = await asUser("owner");
    await ownerPage.goto(`${app.baseURL}/projects/${app.projectKey}/mailbox`);
    await ownerPage.getByTestId("mailbox-folder-sent").click();
    await expect(ownerPage.getByText(subject)).toBeVisible();
    await expect(ownerPage.getByText(/收件人：alice/)).toBeVisible();

    // Group mailbox management.
    await alice.getByTestId("mailbox-groups-button").click();
    await expect(alice.getByTestId("mailbox-groups-dialog")).toBeVisible();
    const groupName = `qa-group-${Date.now()}`;
    await alice.getByTestId("mailbox-group-name").fill(groupName);
    await alice.getByTestId("mailbox-group-create").click();
    await expect(alice.getByTestId("mailbox-group-list")).toContainText(groupName);
  });
});
