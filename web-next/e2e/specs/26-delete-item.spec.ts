import { expect, test } from "../support/fixtures";
import { openItem } from "../support/ui";

test.describe("work item delete", () => {
  test("owner deletes an item and its subtree from the drawer", async ({ api, app, page }) => {
    const projectKey = await api.createSandboxProject();
    const stamp = Date.now();
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `story-${stamp}`,
    });
    const child = await api.createItemIn(projectKey, {
      kind: "task",
      title: `child-${stamp}`,
      parent: story.display_id,
    });

    await openItem(page, app, story, projectKey);
    await page.getByTestId("item-panel-delete").click();

    const dialog = page.getByTestId("item-delete-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(story.display_id);
    await dialog.getByRole("button", { name: "删除工作项" }).click();

    await expect(page.getByTestId("item-panel")).toBeHidden();

    // Soft delete cascades to the subtree and remains queryable by admins.
    const storyRow = await api.get<{ deleted_at?: string | null }>(
      `/work-items/${story.display_id}?include_deleted=true`,
    );
    expect(storyRow.data.deleted_at).toBeTruthy();
    const childRow = await api.get<{ deleted_at?: string | null }>(
      `/work-items/${child.display_id}?include_deleted=true`,
    );
    expect(childRow.data.deleted_at).toBeTruthy();
  });
});
