import { expect, test } from "../support/fixtures";

test.describe("work item drawer sprint section", () => {
  test("add, change and remove an item's sprint (RDM-44)", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `sprint-drawer-${stamp}`,
    });
    const sprint = (
      await api.post<{ id: string; name: string }>(`/projects/${projectKey}/sprints`, {
        name: `S-${stamp}`,
      })
    ).data;

    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);
    await page.getByTestId(`work-item-row-${story.display_id}`).click();
    const section = page.getByTestId("item-field-sprint");
    await expect(section).toBeVisible();
    await expect(section).toContainText("未加入迭代");

    // Join the sprint from the drawer.
    await section.getByTestId("item-sprint-change").click();
    await section.getByRole("combobox").click();
    await page.getByRole("option", { name: sprint.name, exact: true }).click();
    await expect(section).toContainText(sprint.name);
    await expect(section.getByTestId("item-sprint-remove")).toBeVisible();

    // Leave it again.
    await section.getByTestId("item-sprint-remove").click();
    await expect(section).toContainText("未加入迭代");
    await expect(section.getByTestId("item-sprint-remove")).toHaveCount(0);
  });

  test("kinds that cannot join a sprint hide the section", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const epic = await api.createItemIn(projectKey, {
      kind: "epic",
      title: `epic-${Date.now()}`,
    });

    // The list's default kinds are story+issue+task (RDM-63); ask for epics.
    await page.goto(`${app.baseURL}/projects/${projectKey}/backlog?kind=epic`);
    await page.getByTestId(`work-item-row-${epic.display_id}`).click();
    await expect(page.getByTestId("item-panel")).toBeVisible();
    await expect(page.getByTestId("item-section-metadata")).toBeVisible();
    await expect(page.getByTestId("item-field-sprint")).toHaveCount(0);
  });
});
