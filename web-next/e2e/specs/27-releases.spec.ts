import { expect, test } from "../support/fixtures";
import { expectSuccessNotice, waitForItemStatus } from "../support/ui";

// Product release (version) page: create a release, add a completed story,
// publish it, and verify the workflow story becomes PUBLISHED.
test("release publishes its completed stories", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  const story = await api.createItemIn(projectKey, {
    kind: "story",
    // Long title: the detail drawer table must truncate instead of overflowing
    // its container (RDM-25).
    title: `release-story-${Date.now()}-${"长标题".repeat(20)}`,
    assignee: "alice",
    status: "DONE",
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/releases`);
  await expect(page.getByTestId("page-releases")).toBeVisible();

  await page.getByTestId("release-create-button").click();
  await page.getByTestId("release-form-name").fill("v1.0.0");
  await page.getByTestId("release-form-submit").click();
  await expect(page.getByTestId("release-table")).toContainText("v1.0.0");

  await page.getByTestId("release-table").getByText("v1.0.0").click();
  await expect(page.getByTestId("release-detail")).toBeVisible();

  await page.getByTestId("release-item-add").click();
  const picker = page.getByTestId("work-item-picker-dialog");
  await expect(picker).toBeVisible();
  await picker.getByTestId(`work-item-picker-row-${story.display_id}`).click();
  await picker.getByTestId("work-item-picker-confirm").click();
  await expect(page.getByTestId(`release-item-row-${story.display_id}`)).toBeVisible();
  // RDM-25: the items table stays inside the drawer instead of being clipped.
  expect(
    await page
      .getByTestId("release-detail-items")
      .evaluate((el) => el.scrollWidth - el.clientWidth),
  ).toBe(0);
  await expect(page.getByTestId("release-publish")).toBeEnabled();

  await page.getByTestId("release-publish").click();
  await page.getByTestId("release-publish-dialog-confirm").click();

  await expectSuccessNotice(page, "已发布");
  await expect(page.getByTestId("release-status-RELEASED").first()).toBeVisible();
  await waitForItemStatus(api, story, "PUBLISHED");
});

test("publish stays disabled while a story is unfinished", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  const story = await api.createItemIn(projectKey, {
    kind: "story",
    title: `open-story-${Date.now()}`,
    assignee: "alice",
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/releases`);
  await page.getByTestId("release-create-button").click();
  await page.getByTestId("release-form-name").fill("v0.9.0");
  await page.getByTestId("release-form-submit").click();
  await page.getByTestId("release-table").getByText("v0.9.0").click();
  await expect(page.getByTestId("release-detail")).toBeVisible();

  await page.getByTestId("release-item-add").click();
  const picker = page.getByTestId("work-item-picker-dialog");
  await expect(picker).toBeVisible();
  await picker.getByTestId(`work-item-picker-row-${story.display_id}`).click();
  await picker.getByTestId("work-item-picker-confirm").click();

  await expect(page.getByTestId(`release-item-row-${story.display_id}`)).toBeVisible();
  await expect(page.getByTestId("release-publish")).toBeDisabled();
});

test("release scope accepts issues (RDM-35)", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  const issue = await api.createItemIn(projectKey, {
    kind: "issue",
    title: `release-issue-${Date.now()}`,
    assignee: "alice",
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/releases`);
  await page.getByTestId("release-create-button").click();
  await page.getByTestId("release-form-name").fill("v1.1.0");
  await page.getByTestId("release-form-submit").click();
  await page.getByTestId("release-table").getByText("v1.1.0").click();
  await expect(page.getByTestId("release-detail")).toBeVisible();

  await page.getByTestId("release-item-add").click();
  const picker = page.getByTestId("work-item-picker-dialog");
  await expect(picker).toBeVisible();
  await picker.getByTestId(`work-item-picker-row-${issue.display_id}`).click();
  await picker.getByTestId("work-item-picker-confirm").click();

  await expect(page.getByTestId(`release-item-row-${issue.display_id}`)).toBeVisible();
  // The issue is still open, so the release is not ready to publish.
  await expect(page.getByTestId("release-publish")).toBeDisabled();
});

test("picker filters and keeps selections across filters", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  const stamp = Date.now();
  const urgent = await api.createItemIn(projectKey, {
    kind: "story",
    title: `urgent-${stamp}`,
    priority: 1,
  });
  const low = await api.createItemIn(projectKey, {
    kind: "story",
    title: `low-${stamp}`,
    priority: 4,
  });

  await page.goto(`${app.baseURL}/projects/${projectKey}/releases`);
  await page.getByTestId("release-create-button").click();
  await page.getByTestId("release-form-name").fill("v2.0.0");
  await page.getByTestId("release-form-submit").click();
  await page.getByTestId("release-table").getByText("v2.0.0").click();
  await page.getByTestId("release-item-add").click();

  const picker = page.getByTestId("work-item-picker-dialog");
  await expect(picker).toBeVisible();
  // RDM-39 feedback: half the viewport wide, 3/5 tall.
  const pickerBox = await picker.boundingBox();
  const viewport = page.viewportSize()!;
  expect(pickerBox!.width).toBeGreaterThanOrEqual(viewport.width * 0.45);
  expect(pickerBox!.height).toBeGreaterThanOrEqual(viewport.height * 0.55);
  await picker.getByTestId(`work-item-picker-row-${urgent.display_id}`).click();
  await expect(picker.getByTestId("work-item-picker-selected")).toContainText("1");

  // Search for the other item and add it as well.
  await picker.getByTestId("work-item-picker-search").fill(low.title);
  await picker.getByTestId("work-item-picker-search").press("Enter");
  await picker.getByTestId(`work-item-picker-row-${low.display_id}`).click();
  await expect(picker.getByTestId("work-item-picker-selected")).toContainText("2");

  // Clear the search and filter by priority: low disappears, but stays selected.
  await picker.getByTestId("work-item-picker-search").fill("");
  await picker.getByTestId("work-item-picker-search").press("Enter");
  await picker.getByTestId("work-item-picker-priority").getByRole("combobox").click();
  await page.getByRole("option", { name: "紧急", exact: true }).click();
  await expect(picker.getByTestId(`work-item-picker-row-${low.display_id}`)).toHaveCount(0);
  await expect(picker.getByTestId("work-item-picker-selected")).toContainText("2");
  await picker.getByTestId("work-item-picker-confirm").click();

  await expect(page.getByTestId(`release-item-row-${urgent.display_id}`)).toBeVisible();
  await expect(page.getByTestId(`release-item-row-${low.display_id}`)).toBeVisible();
});
