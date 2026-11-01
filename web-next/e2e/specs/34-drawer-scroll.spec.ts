import { expect, test } from "../support/fixtures";

// RDM-74: sprint and release drawers scroll when their content overflows.
const longBody = Array.from({ length: 120 }, (_, index) => `第 ${index + 1} 行`).join(
  "\n\n",
);

test("sprint drawer scrolls overflowing content", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  const sprint = (
    await api.post<{ id: string; name: string }>(`/projects/${projectKey}/sprints`, {
      name: `scroll-sprint-${stamp}`,
      goal_md: longBody,
    })
  ).data;

  await page.goto(`${app.baseURL}/projects/${projectKey}/sprints`);
  await page.getByTestId(`sprint-row-${sprint.id}`).click();
  await expect(page.getByTestId("sprint-detail")).toBeVisible();

  const scroll = page.locator(".rdm-drawer-scroll");
  await expect(scroll).toHaveCount(1);
  expect(await scroll.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await scroll.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  expect(await scroll.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
});

test("release drawer scrolls overflowing content", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  await api.post(`/projects/${projectKey}/releases`, {
    name: `scroll-release-${stamp}`,
    description_md: longBody,
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/releases`);
  await page.getByText(`scroll-release-${stamp}`).click();
  await expect(page.getByTestId("release-detail")).toBeVisible();

  const scroll = page.locator(".rdm-drawer-scroll");
  await expect(scroll).toHaveCount(1);
  expect(await scroll.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await scroll.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  expect(await scroll.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
});
