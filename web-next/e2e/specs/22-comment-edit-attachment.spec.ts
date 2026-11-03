import { expect, test } from "../support/fixtures";
import { openItem } from "../support/ui";

test.describe("comments and attachments", () => {
  test("edit a comment and preview a text attachment", async ({ api, app, page }) => {
    const item = await api.createItem({
      kind: "task",
      title: `comment-edit-${Date.now()}`,
    });
    const comment = (
      await api.post(
        `/work-items/${item.display_id}/comments`,
        { body_md: "原始评论" },
        "owner",
      )
    ).data as { id: string };

    await openItem(page, app, item);
    await expect(page.getByText("原始评论")).toBeVisible();
    await page.getByTestId(`item-comment-edit-${comment.id}`).click();
    await page.getByTestId(`item-comment-edit-input-${comment.id}`).fill("修改后的评论");
    await page.getByTestId(`item-comment-edit-save-${comment.id}`).click();
    await expect(page.getByText("修改后的评论")).toBeVisible();
    await expect(page.getByText("已编辑")).toBeVisible();
    await expect(page.getByText("原始评论")).toHaveCount(0);

    await page.getByTestId("item-attachment-input").setInputFiles({
      name: "note.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("hello preview"),
    });
    const attachmentRow = page
      .locator('[data-testid^="item-attachment-"]')
      .filter({ hasText: "note.txt" });
    await expect(attachmentRow).toBeVisible();
    await attachmentRow.getByText("预览", { exact: true }).click();
    await expect(page.getByTestId("attachment-preview-dialog")).toBeVisible();
    await expect(page.getByTestId("attachment-preview-body")).toContainText("hello preview");
  });

  test("preview a docx attachment", async ({ api, app, page }) => {
    const item = await api.createItem({
      kind: "task",
      title: `docx-preview-${Date.now()}`,
    });

    await openItem(page, app, item);
    await page.getByTestId("item-attachment-input").setInputFiles("e2e/fixtures/sample.docx");
    const attachmentRow = page
      .locator('[data-testid^="item-attachment-"]')
      .filter({ hasText: "sample.docx" });
    await expect(attachmentRow).toBeVisible();
    await attachmentRow.getByText("预览", { exact: true }).click();
    await expect(page.getByTestId("attachment-preview-body")).toContainText(
      "hello office preview",
      { timeout: 20_000 },
    );
  });

  test("preview a pdf attachment", async ({ api, app, page }) => {
    const item = await api.createItem({
      kind: "task",
      title: `pdf-preview-${Date.now()}`,
    });

    await openItem(page, app, item);
    await page.getByTestId("item-attachment-input").setInputFiles("e2e/fixtures/sample.pdf");
    const attachmentRow = page
      .locator('[data-testid^="item-attachment-"]')
      .filter({ hasText: "sample.pdf" });
    await expect(attachmentRow).toBeVisible();
    await attachmentRow.getByText("预览", { exact: true }).click();
    await expect(page.getByTestId("attachment-preview-body").locator("canvas")).toBeVisible({
      timeout: 20_000,
    });
  });
});
