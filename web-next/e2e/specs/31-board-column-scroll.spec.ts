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

  // RDM-73: bottom padding keeps the end marker clear of the column edge.
  // The appended page changed the scroll height, so scroll to the new bottom.
  await body.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(page.getByTestId("board-column-end-TODO")).toBeVisible();
  const endBox = await page.getByTestId("board-column-end-TODO").boundingBox();
  const bodyBox = await body.boundingBox();
  expect(endBox!.y + endBox!.height).toBeLessThanOrEqual(
    bodyBox!.y + bodyBox!.height - 8,
  );
  // RDM-78: the end marker is horizontally centered within the column body.
  expect(
    Math.abs(
      endBox!.x + endBox!.width / 2 - (bodyBox!.x + bodyBox!.width / 2),
    ),
  ).toBeLessThanOrEqual(2);

  // RDM-73: horizontal trackpad/wheel scrolling over a column must chain to
  // the board's horizontal scroller instead of dying in the column body.
  await page.setViewportSize({ width: 900, height: 800 });
  await page.reload();
  await expect(page.getByTestId("board-column-TODO")).toBeVisible();
  const board = page.getByTestId("board-columns");
  expect(
    await board.evaluate((el) => el.scrollWidth > el.clientWidth),
  ).toBe(true);
  await page.getByTestId("board-column-body-TODO").hover();
  await page.mouse.wheel(400, 0);
  await expect
    .poll(() => board.evaluate((el) => el.scrollLeft))
    .toBeGreaterThan(0);
});
