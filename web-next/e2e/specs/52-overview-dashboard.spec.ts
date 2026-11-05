import { expect, test } from "../support/fixtures";

// RDM-185: the project landing page is a dashboard. Counters, "my work",
// overdue risk, sprint progress and activity must all come from the overview
// aggregation rather than a client-side reshuffle of the backlog.
test.describe("project overview dashboard", () => {
  test("counters, my work, risk, sprint and activity reflect real data", async ({
    app,
    api,
    page,
  }) => {
    const key = await api.createSandboxProject(["alice"]);
    const overdue = await api.createItemIn(key, {
      kind: "task",
      title: "逾期任务",
      assignee: "owner",
      priority: 1,
      planned_end_date: "2000-01-01",
    });
    const mine = await api.createItemIn(key, {
      kind: "story",
      title: "我的进行中工作",
      assignee: "owner",
      status: "IN_PROGRESS",
    });
    await api.createItemIn(key, {
      kind: "issue",
      title: "最近更新的缺陷",
      priority: 2,
    });

    const today = new Date();
    const end = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000);
    const iso = (d: Date) => d.toLocaleDateString("en-CA");
    const sprint = (
      await api.post<{ id: string }>(`/projects/${key}/sprints`, {
        name: "E2E 概览迭代",
        start_date: iso(today),
        end_date: iso(end),
      })
    ).data;
    await api.post(`/sprints/${sprint.id}/items`, { items: [mine.display_id] });
    await api.post(`/sprints/${sprint.id}/start`);

    await page.goto(`${app.baseURL}/projects/${key}`);
    await expect(page.getByTestId("page-project-overview")).toBeVisible();

    // The project rail exposes Overview, and only the landing route marks it active.
    const overviewRail = page.getByTestId("rail-item-project-overview");
    await expect(overviewRail).toBeVisible();
    await expect(overviewRail).toHaveAttribute("aria-current", "page");
    await page.getByTestId("rail-item-project-board").click();
    await expect(page.getByTestId("page-board")).toBeVisible();
    await expect(overviewRail).not.toHaveAttribute("aria-current", "page");
    await overviewRail.click();
    await expect(page.getByTestId("page-project-overview")).toBeVisible();

    // Counters: three items, two assigned to the owner, one overdue.
    await expect(page.getByTestId("overview-stat-total")).toContainText("3");
    await expect(page.getByTestId("overview-stat-mine")).toContainText("2");
    await expect(page.getByTestId("overview-stat-overdue")).toContainText("1");

    // Actionable lists.
    await expect(page.getByTestId("overview-my-items")).toContainText("我的进行中工作");
    await expect(page.getByTestId("overview-my-items")).toContainText("逾期任务");
    await expect(page.getByTestId("overview-risk")).toContainText("1");
    await expect(page.getByTestId("overview-risk")).toContainText("逾期任务");
    await expect(page.getByTestId("overview-recent-items")).toContainText("最近更新的缺陷");

    // Sprint progress panel.
    await expect(page.getByTestId("overview-active-sprint")).toContainText("E2E 概览迭代");
    await expect(page.getByTestId("overview-active-sprint")).toContainText("0 / 1 已完成");
    await expect(page.getByTestId("overview-sprint-progress")).toBeVisible();

    // Distributions group statuses into semantic tones.
    await expect(page.getByTestId("overview-status-tone-doing")).toContainText("1");
    await expect(page.getByTestId("overview-status-tone-todo")).toContainText("2");
    await expect(page.getByTestId("overview-kind-distribution")).toContainText("需求");
    await expect(page.getByTestId("overview-priority-distribution")).toBeVisible();

    // Rows open the work item overlay without leaving the overview page.
    await page
      .getByTestId("overview-my-items")
      .getByTestId(`overview-item-${overdue.display_id}`)
      .click();
    await expect(page.getByTestId("item-panel")).toBeVisible();
    await expect(page.getByTestId("item-panel")).toContainText(overdue.display_id);
  });
});
