import { expect, test } from "../support/fixtures";
import {
  boardPath,
  dragCardToColumn,
  expectErrorNotice,
  expectSuccessNotice,
  waitForItemStatus,
} from "../support/ui";

test.use({ viewport: { width: 1920, height: 900 } });

test.describe("workflow: board drag obeys step rules", () => {
  test("direct steps move cards; approval steps require the item detail", async ({
    api,
    app,
    asUser,
  }) => {
    const item = await api.createItem({
      kind: "task",
      title: `board-${Date.now()}`,
      assignee: "alice",
    });

    // Drag executes the named step as the actor, so it must be the assignee.
    const page = await asUser("alice");
    // Narrow the board to task columns so source and target both fit on screen
    // (the multi-kind board puts TO_REVIEW beyond a horizontal scroll).
    await page.goto(`${app.baseURL}${boardPath(app)}?kind=task`);
    await expect(page.getByTestId("page-board")).toBeVisible();
    await expect(page.getByTestId("board-column-TODO")).toBeVisible();
    const card = page.getByTestId(`board-card-${item.display_id}`);
    await expect(card).toBeVisible();

    // TODO -> IN_PROGRESS is a single direct step with an optional note.
    await dragCardToColumn(
      page,
      card,
      page.getByTestId("board-column-IN_PROGRESS"),
    );
    await expectSuccessNotice(page, "→ IN_PROGRESS");
    await expect(
      page.getByTestId("board-column-IN_PROGRESS").getByTestId(`board-card-${item.display_id}`),
    ).toBeVisible();

    // IN_PROGRESS -> TO_REVIEW (SUBMIT_REVIEW) is also a direct step.
    await dragCardToColumn(
      page,
      page.getByTestId(`board-card-${item.display_id}`),
      page.getByTestId("board-column-TO_REVIEW"),
    );
    await expectSuccessNotice(page, "→ TO_REVIEW");
    await expect(
      page.getByTestId("board-column-TO_REVIEW").getByTestId(`board-card-${item.display_id}`),
    ).toBeVisible();

    // TO_REVIEW -> DONE is an approval (or task) step, never a drag.
    await dragCardToColumn(
      page,
      page.getByTestId(`board-card-${item.display_id}`),
      page.getByTestId("board-column-DONE"),
    );
    await expectErrorNotice(page, "请在工作项详情中执行步骤");
    await expect(
      page.getByTestId("board-column-TO_REVIEW").getByTestId(`board-card-${item.display_id}`),
    ).toBeVisible();
    await waitForItemStatus(api, item, "TO_REVIEW");
  });
});
