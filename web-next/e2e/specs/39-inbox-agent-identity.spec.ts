import { expect, test } from "../support/fixtures";

// RDM-96: the inbox identity selector shows a managed agent's notifications
// and to-dos, mirroring the mailbox identity filter.
test("inbox can be scoped to a managed agent", async ({ api, app, asUser }) => {
  const stamp = Date.now();
  const agentName = `inbox-agent-${stamp}`;
  const agent = (
    await api.post<{ id: string }>("/me/agents", { name: agentName }, "alice")
  ).data;

  const humanItem = await api.createItem({
    kind: "task",
    title: `human-todo-${stamp}`,
    assignee: "alice",
  });
  const agentItem = await api.createItem({
    kind: "task",
    title: `agent-todo-${stamp}`,
  });
  await api.post(`/work-items/${agentItem.display_id}/assign`, {
    member: agent.id,
  });

  const page = await asUser("alice");
  await page.goto(`${app.baseURL}/inbox`);
  await expect(page.getByTestId("page-inbox")).toBeVisible();

  // The manager sees an identity selector listing their agent.
  const identity = page.getByTestId("inbox-identity");
  await expect(identity).toBeVisible();
  await identity.getByRole("combobox").click();
  await page.getByRole("option", { name: new RegExp(agentName) }).click();

  // The agent's assignment notification is visible under that identity.
  await expect(page.getByText(`你被指派了 ${agentItem.display_id}`)).toBeVisible();

  // To-dos follow the same identity: only the agent's items.
  await page.getByTestId("inbox-tab-todo").click();
  const todo = page.getByTestId("inbox-todo");
  await expect(todo).toContainText(agentItem.display_id);
  await expect(todo).not.toContainText(humanItem.display_id);
});
