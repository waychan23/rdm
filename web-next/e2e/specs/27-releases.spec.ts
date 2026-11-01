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

  await page.getByTestId("release-detail").getByRole("combobox").click();
  await page.getByRole("option", { name: new RegExp(story.display_id) }).click();
  await page.getByTestId("release-item-add").click();
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

  await page.getByTestId("release-detail").getByRole("combobox").click();
  await page.getByRole("option", { name: new RegExp(story.display_id) }).click();
  await page.getByTestId("release-item-add").click();

  await expect(page.getByTestId(`release-item-row-${story.display_id}`)).toBeVisible();
  await expect(page.getByTestId("release-publish")).toBeDisabled();
});
