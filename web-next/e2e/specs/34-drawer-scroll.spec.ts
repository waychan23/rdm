import { expect, test } from "../support/fixtures";

// RDM-125: the sprint/release drawers keep a fixed shell. A too-tall header
// scrolls locally and the work item list owns the main scrollbar, so the
// drawer itself never scrolls as a whole.
const longBody = Array.from({ length: 120 }, (_, index) => `第 ${index + 1} 行`).join(
  "\n\n",
);

test("sprint drawer keeps a scrolling header and item list inside the shell", async ({
  api,
  app,
  page,
}) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  const sprint = (
    await api.post<{ id: string; name: string }>(`/projects/${projectKey}/sprints`, {
      name: `scroll-sprint-${stamp}`,
      goal_md: longBody,
    })
  ).data;
  for (let index = 0; index < 15; index += 1) {
    const item = await api.createItemIn(projectKey, {
      kind: "task",
      title: `sprint-item-${stamp}-${index}`,
    });
    await api.post(`/sprints/${sprint.id}/items`, { items: [item.display_id] });
  }

  await page.goto(`${app.baseURL}/projects/${projectKey}/sprints`);
  await page.getByTestId(`sprint-row-${sprint.id}`).click();
  await expect(page.getByTestId("sprint-detail")).toBeVisible();

  // The long goal is capped and scrolls inside the header.
  const header = page.getByTestId("sprint-detail-header");
  expect(await header.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await header.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  expect(await header.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);

  // The item list scrolls locally; the drawer shell as a whole does not.
  const shell = page.locator(".rdm-drawer-shell");
  expect(await shell.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(false);
  const list = page.getByTestId("sprint-detail-items-scroll");
  expect(await list.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await list.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  expect(await list.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
});

test("release drawer keeps a scrolling header and item list inside the shell", async ({
  api,
  app,
  page,
}) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  const release = (
    await api.post<{ id: string; name: string }>(`/projects/${projectKey}/releases`, {
      name: `scroll-release-${stamp}`,
      description_md: longBody,
    })
  ).data;
  for (let index = 0; index < 15; index += 1) {
    const item = await api.createItemIn(projectKey, {
      kind: "story",
      title: `release-item-${stamp}-${index}`,
    });
    await api.post(`/releases/${release.id}/items`, { items: [item.display_id] });
  }

  await page.goto(`${app.baseURL}/projects/${projectKey}/releases`);
  await page.getByText(`scroll-release-${stamp}`).click();
  await expect(page.getByTestId("release-detail")).toBeVisible();

  const header = page.getByTestId("release-detail-header");
  expect(await header.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await header.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  expect(await header.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);

  const shell = page.locator(".rdm-drawer-shell");
  expect(await shell.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(false);
  const list = page.getByTestId("release-detail-items-scroll");
  expect(await list.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await list.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  expect(await list.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
});
