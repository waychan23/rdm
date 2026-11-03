import { expect, test } from "../support/fixtures";

/**
 * RDM-153: the filter band scrolls horizontally and clips vertically, so a
 * react-select menu rendered inline was cut off (some filters looked like they
 * had no options at all). Every filter menu must portal to <body> instead.
 */
test("filter dropdowns escape the clipped toolbar", async ({ app, page }) => {
  await page.goto(`${app.baseURL}/projects/${app.projectKey}/backlog`);
  await expect(page.getByTestId("page-backlog")).toBeVisible();

  for (const testId of [
    "work-item-filter-status",
    "work-item-filter-completed",
    "work-item-filter-assignee",
  ]) {
    const filter = page.getByTestId(testId);
    await filter.getByRole("combobox").click();

    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    expect(
      await listbox.evaluate(
        (element) => !element.closest('[data-testid="work-item-filters"]'),
      ),
    ).toBe(true);

    const box = await listbox.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(
      page.viewportSize()!.height,
    );

    await page.keyboard.press("Escape");
    await expect(listbox).toHaveCount(0);
  }
});
