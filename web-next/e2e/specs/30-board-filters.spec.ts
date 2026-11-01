import { expect, test } from "../support/fixtures";

test.describe("board filters", () => {
  test("board filters by sprint (RDM-38)", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const sprint = (
      await api.post<{ id: string; name: string }>(`/projects/${projectKey}/sprints`, {
        name: `S-${stamp}`,
      })
    ).data;
    const inside = await api.createItemIn(projectKey, {
      kind: "story",
      title: `in-sprint-${stamp}`,
    });
    const outside = await api.createItemIn(projectKey, {
      kind: "story",
      title: `out-sprint-${stamp}`,
    });
    await api.post(`/sprints/${sprint.id}/items`, { items: [inside.display_id] });

    await page.goto(`${app.baseURL}/projects/${projectKey}/board?kind=story`);
    const insideCard = page.getByTestId(`board-card-${inside.display_id}`);
    const outsideCard = page.getByTestId(`board-card-${outside.display_id}`);
    await expect(insideCard).toBeVisible();
    await expect(outsideCard).toBeVisible();

    await page.getByTestId("board-sprint-filter").getByRole("combobox").click();
    await page.getByRole("option", { name: sprint.name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`sprint=${sprint.id}`));
    await expect(insideCard).toBeVisible();
    await expect(outsideCard).toHaveCount(0);
  });

  test("board shows the selected kinds only (RDM-40)", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const story = await api.createItemIn(projectKey, { kind: "story", title: `s-${stamp}` });
    const issue = await api.createItemIn(projectKey, { kind: "issue", title: `i-${stamp}` });
    const task = await api.createItemIn(projectKey, { kind: "task", title: `t-${stamp}` });

    await page.goto(`${app.baseURL}/projects/${projectKey}/board?kind=story,issue`);
    await expect(page.getByTestId(`board-card-${story.display_id}`)).toBeVisible();
    await expect(page.getByTestId(`board-card-${issue.display_id}`)).toBeVisible();
    await expect(page.getByTestId(`board-card-${task.display_id}`)).toHaveCount(0);
    await expect(page.getByTestId("board-kind-filter")).toContainText("需求");
    await expect(page.getByTestId("board-kind-filter")).toContainText("缺陷");
    await expect(page.getByTestId("board-kind-filter")).not.toContainText("任务");
  });

  test("board hides child items unless top-level-only is off (RDM-40)", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `parent-${stamp}`,
    });
    const child = await api.createItemIn(projectKey, {
      kind: "task",
      title: `child-${stamp}`,
      parent: story.display_id,
    });

    await page.goto(`${app.baseURL}/projects/${projectKey}/board?kind=story,task`);
    const childCard = page.getByTestId(`board-card-${child.display_id}`);
    await expect(page.getByTestId(`board-card-${story.display_id}`)).toBeVisible();
    await expect(childCard).toHaveCount(0);

    await page.getByRole("checkbox", { name: "仅展示一级工作项" }).click();
    await expect(page).toHaveURL(/rootOnly=false/);
    await expect(childCard).toBeVisible();
  });

  test("a filtered sprint shows its info and opens the sprint drawer (RDM-40)", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const sprint = (
      await api.post<{ id: string; name: string }>(`/projects/${projectKey}/sprints`, {
        name: `S-${stamp}`,
        start_date: "2026-01-01",
        end_date: "2026-01-14",
      })
    ).data;

    await page.goto(
      `${app.baseURL}/projects/${projectKey}/board?kind=story&sprint=${sprint.id}`,
    );
    const info = page.getByTestId("board-sprint-info");
    await expect(info).toContainText(sprint.name);
    await expect(info).toContainText("2026-01-01 ~ 2026-01-14");

    await info.getByTestId("board-sprint-open").click();
    await expect(page.getByTestId("sprint-detail")).toContainText(sprint.name);
  });
});
