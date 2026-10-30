import { expect, test } from "../support/fixtures";
import { openItem } from "../support/ui";

test.describe("work item parent change", () => {
  test("a story moves (with its subtree) from one epic to another via the drawer", async ({
    api,
    app,
    asUser,
  }) => {
    const projectKey = await api.createSandboxProject(["alice"]);
    const stamp = Date.now();
    const epicA = await api.createItemIn(projectKey, {
      kind: "epic",
      title: `epic-a-${stamp}`,
    });
    const epicB = await api.createItemIn(projectKey, {
      kind: "epic",
      title: `epic-b-${stamp}`,
    });
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `story-${stamp}`,
      parent: epicA.display_id,
      assignee: "alice",
    });
    const child = await api.createItemIn(projectKey, {
      kind: "task",
      title: `child-${stamp}`,
      parent: story.display_id,
      assignee: "alice",
    });

    const page = await asUser("alice");
    await openItem(page, app, story, projectKey);
    const parentField = page.getByTestId("item-field-parent");
    await expect(parentField).toContainText(epicA.display_id);

    await page.getByTestId("item-parent-change").click();
    const picker = parentField.getByRole("combobox");
    await picker.click();
    await page.getByRole("option", { name: new RegExp(epicB.display_id) }).click();

    await expect(parentField).toContainText(epicB.display_id);
    await expect(
      page.getByTestId("notice-success").filter({ hasText: "已改为" }).first(),
    ).toBeVisible();

    // The story's own subtree follows it; both epics' children lists reflect
    // the move on the server.
    const storyDetail = await api.getItem(story.id, "alice");
    expect(storyDetail.meta.parent?.display_id).toBe(epicB.display_id);
    const childDetail = await api.getItem(child.id, "alice");
    expect(childDetail.meta.parent?.display_id).toBe(story.display_id);
    const oldEpic = await api.getItem(epicA.id, "alice");
    expect(oldEpic.meta.children?.some((c) => c.id === story.id)).toBe(false);
    const newEpic = await api.getItem(epicB.id, "alice");
    expect(newEpic.meta.children?.some((c) => c.id === story.id)).toBe(true);

    await page.getByTestId("item-history-toggle").click();
    await expect(page.getByTestId("item-history-list")).toContainText("修改了父项");
  });
});
