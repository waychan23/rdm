import type { Item } from "../support/api";
import { expect, test } from "../support/fixtures";
import { openItem } from "../support/ui";

// 200×900 solid PNG; tall enough to exercise the drawer's image cap.
const TALL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAMgAAAOECAIAAABrSOlDAAAGKklEQVR42u3SQQkAAAwDscqpfz0TMw2DPQNRcFymhXeRAGNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjYSwJMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjIWxVMBYGAtjgbEwFsYCY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjAXGwlgYC2OpgLEwFsYCY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjAXGwlgYC4yFsTAWxpIAY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWBhLBYyFsTAWGAtjYSwwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWGAsjIWxMJYKGAtjYSwwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWGAsjIWxwFgYC2NhLAkwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAuMhbEwFhgLY2EsMBbGwlhgLIyFscBYGAtjgbEwFsYCY2EsjAXGwlgYC4yFsTAWGAtjYSwwFsbCWGAsjIWxwFgYC2OBsTAWxgJjYSyMhbFUwFgYC2OBsTAWxgJjYSyMBcbCWBgLjIWxMBYYC2NhLDAWxsJYYCyMhbHAWBgLY4GxMBbGAmNhLIwFxsJYGAtuFnbIKck2TUuiAAAAAElFTkSuQmCC",
  "base64",
);

test.describe("work item drawer layout", () => {
  test("sections, dividers, labels, priority swatch, children and images", async ({
    api,
    app,
    page,
    request,
  }) => {
    const projectKey = await api.createSandboxProject(["alice", "bob"]);
    const stamp = Date.now();
    const epic = await api.createItemIn(projectKey, {
      kind: "epic",
      title: `layout-epic-${stamp}`,
    });
    const story = await api.createItemIn(projectKey, {
      kind: "story",
      title: `layout-story-${stamp}`,
      parent: epic.display_id,
      assignee: "alice",
    });
    await api.createItemIn(projectKey, {
      kind: "task",
      title: `layout-child-${stamp}`,
      parent: story.display_id,
      assignee: "bob",
    });
    const task = await api.createItemIn(projectKey, {
      kind: "task",
      title: `layout-task-${stamp}`,
      task_type: "frontend",
      parent: story.display_id,
      assignee: "alice",
    });
    const gated = await api.createItemIn(projectKey, {
      kind: "task",
      title: `layout-gated-${stamp}`,
      assignee: "alice",
      reviewer: ["bob"],
      review_content_md: "ready",
      status: "TO_REVIEW",
    });
    const priorityItems: Item[] = [];
    for (const priority of [1, 2, 3, 4]) {
      priorityItems.push(
        await api.createItemIn(projectKey, {
          kind: "task",
          title: `layout-priority-${priority}-${stamp}`,
          assignee: "alice",
          priority,
        }),
      );
    }

    // Story: parent section first + divider; left sections separated; base,
    // kind, children and comments blocks all present.
    await openItem(page, app, story, projectKey);
    const fields = page.getByTestId("item-panel-fields");
    const content = page.getByTestId("item-panel-content");
    expect(
      await fields.evaluate((el) => el.firstElementChild?.getAttribute("data-testid")),
    ).toBe("item-field-parent");
    await expect(fields.locator("hr.rdm-item-divider").first()).toBeVisible();
    for (const id of [
      "item-section-base",
      "item-section-kind",
      "item-section-children",
      "item-section-comments",
    ]) {
      await expect(page.getByTestId(id)).toBeVisible();
    }
    await expect(content).not.toContainText("特型字段");
    expect(
      await content.locator("hr.rdm-item-divider").count(),
    ).toBeGreaterThanOrEqual(3);

    // Attachments/artifacts moved to the left column.
    for (const id of ["item-field-attachments", "item-field-artifacts"]) {
      expect(
        await page.getByTestId(id).evaluate((el) =>
          Boolean(el.closest('[data-testid="item-panel-content"]')),
        ),
      ).toBe(true);
      await expect(fields.getByTestId(id)).toHaveCount(0);
    }

    // Child rows show status/assignee and no detach action.
    const children = page.getByTestId("item-panel-children");
    const childRow = children
      .locator(".rdm-item-child")
      .filter({ hasText: `layout-child-${stamp}` });
    await expect(childRow.getByTestId("status-lozenge-TODO")).toBeVisible();
    await expect(childRow.locator(".rdm-item-child-assignee")).toContainText("bob");
    await expect(children.getByText("解除")).toHaveCount(0);

    // Composer is hidden until "添加评论"; when shown it stays in the left
    // column, and cancelling with content asks for confirmation first.
    const addComment = page.getByTestId("item-comment-add");
    const bar = page.getByTestId("item-comment-bar");
    await expect(bar).toHaveCount(0);
    await addComment.click();
    await expect(bar).toBeVisible();
    await expect(addComment).toHaveCount(0);
    expect(
      await bar.evaluate((el) => Boolean(el.closest('[data-testid="item-panel-content"]'))),
    ).toBe(true);
    const barBox = await bar.boundingBox();
    const fieldsBox = await fields.boundingBox();
    expect(barBox!.x + barBox!.width).toBeLessThanOrEqual(fieldsBox!.x + 1);

    // Empty cancel closes immediately.
    await page.getByTestId("item-comment-cancel").click();
    await expect(bar).toHaveCount(0);
    await expect(addComment).toBeVisible();

    // Non-empty cancel requires confirmation and discards the draft.
    await addComment.click();
    await page.getByTestId("item-comment").fill("draft to discard");
    await page.getByTestId("item-comment-cancel").click();
    await expect(page.getByTestId("comment-cancel-dialog")).toBeVisible();
    await page.getByTestId("comment-cancel-dialog-confirm").click();
    await expect(bar).toHaveCount(0);
    await expect(addComment).toBeVisible();

    // Posting hides the composer again and appends the comment.
    await addComment.click();
    await page.getByTestId("item-comment").fill("a real comment");
    await page.getByTestId("item-comment-submit").click();
    await expect(bar).toHaveCount(0);
    await expect(addComment).toBeVisible();
    await expect(page.getByTestId("item-panel-comments")).toContainText("a real comment");

    // Labels get a thick blue left rule.
    const descLabel = page
      .getByTestId("item-panel-description")
      .locator(".rdm-item-section-label");
    expect(
      await descLabel.evaluate((el) => getComputedStyle(el).borderLeftWidth),
    ).toBe("3px");

    // Priority moved above status, with a square swatch aligned to the select.
    const priority = page.getByTestId("item-field-priority");
    const status = page.getByTestId("item-field-status");
    expect((await priority.boundingBox())!.y).toBeLessThan((await status.boundingBox())!.y);
    // No "unset" value: newly created items default to 中.
    await expect(page.getByTestId("priority-select")).toContainText("中");
    const selectBox = await page.getByTestId("priority-select").boundingBox();
    const swatchBox = await page.getByTestId("priority-swatch").boundingBox();
    expect(Math.abs(swatchBox!.height - selectBox!.height)).toBeLessThan(2);
    expect(Math.abs(swatchBox!.width - swatchBox!.height)).toBeLessThan(2);
    expect(
      Math.abs(
        swatchBox!.y + swatchBox!.height / 2 - (selectBox!.y + selectBox!.height / 2),
      ),
    ).toBeLessThan(2);
    await expect(fields.getByTestId("priority-mark")).toHaveCount(0);

    // Right column groups are separated and metadata wraps the history.
    expect(await fields.locator("hr.rdm-item-divider").count()).toBeGreaterThanOrEqual(4);
    await expect(page.getByTestId("item-field-assignee")).toBeVisible();
    await expect(page.getByTestId("item-field-participants")).toBeVisible();
    await expect(page.getByTestId("item-field-reviewer")).toBeVisible();
    await expect(
      page.getByTestId("item-section-metadata").getByTestId("item-history"),
    ).toBeVisible();

    // Priority swatch colors: unset/P4 grey, P1 red, P2 yellow, P3 blue.
    const tokenColors = await page.evaluate(() => {
      const probe = (name: string) => {
        const el = document.createElement("span");
        el.style.color = `var(--ds-${name})`;
        document.body.appendChild(el);
        const color = getComputedStyle(el).color;
        el.remove();
        return color;
      };
      return {
        danger: probe("icon-danger"),
        warning: probe("icon-warning"),
        information: probe("icon-information"),
        disabled: probe("icon-disabled"),
      };
    });
    const expected = [
      { color: tokenColors.danger, label: "紧急" },
      { color: tokenColors.warning, label: "高" },
      { color: tokenColors.information, label: "中" },
      { color: tokenColors.disabled, label: "低" },
    ];
    for (let index = 0; index < priorityItems.length; index += 1) {
      await openItem(page, app, priorityItems[index], projectKey);
      const swatch = page.getByTestId("priority-swatch");
      await expect(swatch).toHaveAttribute("data-priority", String(index + 1));
      expect(
        await swatch.evaluate((el) => getComputedStyle(el).backgroundColor),
      ).toBe(expected[index].color);
      await expect(page.getByTestId("priority-select")).toContainText(
        expected[index].label,
      );
    }

    // Task type: value only, centered with the title on the same row.
    await openItem(page, app, task, projectKey);
    const taskType = page.getByTestId("item-task-type");
    await expect(taskType).toContainText("前端开发");
    await expect(taskType).not.toContainText("任务类型");
    const typeBox = await taskType.boundingBox();
    const titleBox = await page.getByTestId("item-panel-title").boundingBox();
    expect(typeBox!.x).toBeLessThan(titleBox!.x);
    expect(
      Math.abs(typeBox!.y + typeBox!.height / 2 - (titleBox!.y + titleBox!.height / 2)),
    ).toBeLessThan(3);

    // Epic: no parent section/divider and no kind-field section.
    await openItem(page, app, epic, projectKey);
    await expect(page.getByTestId("item-field-parent")).toHaveCount(0);
    await expect(page.getByTestId("item-panel-fields-json")).toHaveCount(0);
    await expect(content).not.toContainText("特型字段");
    expect(
      await fields.evaluate((el) => el.firstElementChild?.getAttribute("data-testid")),
    ).toBe("item-field-priority");

    // Gated field labels carry a red required mark.
    await openItem(page, app, gated, projectKey);
    const reviewLabel = page
      .getByTestId("item-review-content")
      .locator(".rdm-item-section-label");
    await expect(reviewLabel).toContainText("评审意见");
    await expect(reviewLabel.locator(".rdm-required-mark")).toBeVisible();
    expect(
      await reviewLabel.evaluate((el) => getComputedStyle(el).borderLeftWidth),
    ).toBe("3px");

    // Markdown image is capped at 1/3 of the drawer height, keeping 200:900.
    const upload = await request.post(
      `${app.baseURL}/api/v1/projects/${projectKey}/attachments`,
      {
        headers: { Authorization: `Bearer ${app.owner.accessToken}` },
        multipart: {
          owner_type: "work_item",
          owner_ref: story.id,
          file: { name: "tall.png", mimeType: "image/png", buffer: TALL_PNG },
        },
      },
    );
    expect(upload.ok()).toBeTruthy();
    const attachment = (await upload.json()).data;
    const detail = await api.getItem(story.id);
    await api.request(
      "PATCH",
      `/work-items/${story.id}`,
      {
        row_version: detail.data.row_version,
        description_md: `![tall](/api/v1/attachments/${attachment.id}/download)`,
      },
      "owner",
    );

    await openItem(page, app, story, projectKey);
    const image = page.getByTestId("item-panel-description").locator("img");
    await expect(image).toBeVisible();
    await expect
      .poll(() => image.evaluate((el) => (el as HTMLImageElement).naturalWidth))
      .toBe(200);
    const measured = await image.evaluate((el) => {
      const img = el as HTMLImageElement;
      const panel = document.querySelector<HTMLElement>('[data-testid="item-panel"]');
      return {
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight,
        width: img.clientWidth,
        height: img.clientHeight,
        panelHeight: panel?.clientHeight ?? 0,
      };
    });
    expect(measured.height).toBeLessThanOrEqual(measured.panelHeight / 3 + 2);
    expect(
      Math.abs(measured.width / measured.height - measured.naturalWidth / measured.naturalHeight),
    ).toBeLessThan(0.02);
  });
});
