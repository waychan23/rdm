import { expect, test } from "../support/fixtures";

// RDM-58: every board column scrolls (and pages) independently; the column
// header stays put while the cards scroll.
test("board columns scroll and paginate independently", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject();
  const stamp = Date.now();
  for (let index = 0; index < 25; index += 1) {
    await api.createItemIn(projectKey, {
      kind: "task",
      title: `column-${stamp}-${index}`,
    });
  }

  await page.goto(`${app.baseURL}/projects/${projectKey}/board?kind=task`);
  await expect(page.getByTestId("page-board")).toBeVisible();
  const todo = page.getByTestId("board-column-TODO");
  await expect(todo).toBeVisible();
  await expect(page.getByTestId("board-column-count-TODO")).toHaveText("25");

  const body = page.getByTestId("board-column-body-TODO");
  // Only the first page is rendered until the column is scrolled down.
  await expect(todo.locator('[data-testid^="board-card-"]')).toHaveCount(20);
  await expect(page.getByTestId("board-column-end-TODO")).toHaveCount(0);
  expect(
    await body.evaluate((el) => el.scrollHeight > el.clientHeight),
  ).toBe(true);

  await body.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(todo.locator('[data-testid^="board-card-"]')).toHaveCount(25);
  await expect(page.getByTestId("board-column-end-TODO")).toContainText("没有更多数据");

  // The header (status + count) is outside the scroll body and stays visible.
  await expect(page.getByTestId("board-column-count-TODO")).toBeVisible();
  await expect(todo).toContainText("待办");
});
