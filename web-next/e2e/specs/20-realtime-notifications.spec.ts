import { expect, test } from "../support/fixtures";

test.describe("realtime notifications", () => {
  test("an assignment appears in the inbox without reloading", async ({
    api,
    app,
    asUser,
  }) => {
    const alice = await asUser("alice");
    const streamRequest = alice.waitForRequest(/\/api\/v1\/stream/);
    await alice.goto(`${app.baseURL}/inbox`);
    await expect(alice.getByTestId("page-inbox")).toBeVisible();
    await streamRequest;

    const item = await api.createItem({
      kind: "task",
      title: `sse-${Date.now()}`,
    });
    await api.post(`/work-items/${item.display_id}/assign`, {
      member: api.userId("alice"),
    });

    await expect(alice.getByText(`你被指派了 ${item.display_id}`)).toBeVisible({
      timeout: 10_000,
    });
  });
});
