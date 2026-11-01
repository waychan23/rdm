import { expect, test } from "../support/fixtures";

test.describe("list/board display fields", () => {
  test("list shows sprint and planned dates; board card repeats them (RDM-59)", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const sprint = (
      await api.post<{ id: string; name: string }>(`/projects/${projectKey}/sprints`, {
        name: `S-${stamp}`,
      })
    ).data;
    const item = await api.createItemIn(projectKey, {
      kind: "task",
      title: `fields-${stamp}`,
      planned_start_date: "2026-03-01",
      planned_end_date: "2026-03-12",
    });
    const unplanned = await api.createItemIn(projectKey, {
      kind: "task",
      title: `unplanned-${stamp}`,
    });
    await api.post(`/sprints/${sprint.id}/items`, { items: [item.display_id] });

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog?kind=task`);
    await expect(page.getByTestId(`work-item-sprint-${item.display_id}`)).toHaveText(
      sprint.name,
    );
    await expect(page.getByTestId(`work-item-start-${item.display_id}`)).toHaveText(
      "2026-03-01",
    );
    await expect(page.getByTestId(`work-item-end-${item.display_id}`)).toHaveText(
      "2026-03-12",
    );
    // Items outside a sprint and without planned dates render a dash.
    await expect(page.getByTestId(`work-item-sprint-${unplanned.display_id}`)).toHaveText("—");
    await expect(page.getByTestId(`work-item-start-${unplanned.display_id}`)).toHaveText("—");

    await page.goto(`${app.baseURL}/projects/${projectKey}/board?kind=task`);
    const card = page.getByTestId(`board-card-${item.display_id}`);
    await expect(card).toContainText(`迭代：${sprint.name}`);
    await expect(card).toContainText("开始：2026-03-01");
    await expect(card).toContainText("结束：2026-03-12");
    // The unplanned card shows no extra rows at all.
    const plain = page.getByTestId(`board-card-${unplanned.display_id}`);
    await expect(plain).not.toContainText("迭代：");
    await expect(plain).not.toContainText("开始：");
  });
});
