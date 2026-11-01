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
});
