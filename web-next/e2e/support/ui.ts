// Locator-level helpers for the workflow UI. Built-in ADS test ids are used
// wherever they exist so assertions stay about behaviour, not CSS.
import type { Locator, Page } from "@playwright/test";

import type { Api, Item } from "./api";
import { expect } from "./fixtures";
import type { E2EContext } from "./context";

export function itemPath(app: E2EContext, item: Pick<Item, "id">): string {
  return `/projects/${app.projectKey}/items/${item.id}`;
}

export function boardPath(app: E2EContext): string {
  return `/projects/${app.projectKey}/board`;
}

export async function openItem(page: Page, app: E2EContext, item: Pick<Item, "id">) {
  await page.goto(`${app.baseURL}${itemPath(app, item)}`);
  await expect(page.getByTestId("item-panel")).toBeVisible();
  await expect(page.getByTestId("item-panel-loading")).toBeHidden();
}

export async function expectStatus(page: Page, status: string) {
  await expect(
    page.getByTestId("item-field-status").getByTestId(`status-lozenge-${status}`),
  ).toBeVisible();
}

/** The item panel's "可执行步骤" area, scoped to avoid history/board duplicates. */
export function stepButton(page: Page, key: string): Locator {
  return page.getByTestId("item-field-steps").getByTestId(`item-step-${key}`);
}

export async function selectExecutors(page: Page, names: string[]) {
  const dialog = page.getByTestId("step-start-dialog");
  // Atlaskit Select puts `testId` on its portal/menu, not on the control, so
  // scope the combobox through the dialog instead.
  for (const name of names) {
    // Atlaskit closes the menu after each pick even for multi-select.
    await dialog.getByRole("combobox").click();
    const option = page.getByRole("option", { name, exact: true });
    if ((await option.count()) > 0) await option.click();
  }
  // Close the (multi-)menu without risking Escape bubbling to the modal.
  await dialog.getByRole("heading").click();
}

/**
 * ADS InlineEdit's edit button is a zero-size hit area; the read view itself is
 * the clickable affordance that opens the editor.
 */
export async function beginInlineEdit(page: Page, testId: string) {
  const field = page.getByTestId(testId);
  await field.locator("[data-read-view-fit-container-width]").click();
}

/** Fill the step note editor (the MarkdownEditor textarea carries the testId). */
export async function fillStepNote(page: Page, text: string) {
  const editor = page.getByTestId("step-execute-note");
  await editor.click();
  await editor.fill(text);
}

export async function confirmStepExecution(page: Page, note?: string) {
  if (note) await fillStepNote(page, note);
  const confirm = page.getByTestId("step-execute-confirm");
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByTestId("step-execute-dialog")).toBeHidden();
}

export async function startStepThroughDialog(
  page: Page,
  key: string,
  executors: string[],
) {
  await stepButton(page, key).click();
  await expect(page.getByTestId("step-start-dialog")).toBeVisible();
  if (executors.length > 0) await selectExecutors(page, executors);
  const confirm = page.getByTestId("step-start-confirm");
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByTestId("step-start-dialog")).toBeHidden();
}

export async function expectSuccessNotice(page: Page, title: string) {
  // Notices stack (e.g. "step started" then "step cancelled"); match the one.
  await expect(
    page.getByTestId("notice-success").filter({ hasText: title }).first(),
  ).toBeVisible();
}

export async function expectErrorNotice(page: Page, title: string) {
  await expect(
    page.getByTestId("notice-error").filter({ hasText: title }).first(),
  ).toBeVisible();
}

export async function activeStep(page: Page): Promise<Locator> {
  const card = page.getByTestId("active-step-card");
  await expect(card).toBeVisible();
  return card;
}

/**
 * pragmatic-drag-and-drop listens to pointer events, so a full mouse gesture
 * (with intermediate moves past the drag threshold) is required.
 */
export async function dragCardToColumn(page: Page, card: Locator, column: Locator) {
  // Long-lived boards accumulate cards below the fold; the pointer gesture
  // only works on elements inside the viewport.
  await card.scrollIntoViewIfNeeded();
  await column.scrollIntoViewIfNeeded();
  const from = await card.boundingBox();
  const to = await column.boundingBox();
  if (!from || !to) throw new Error("drag source/target has no bounding box");
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(from.x + from.width / 2 + 12, from.y + from.height / 2 + 12, {
    steps: 6,
  });
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 20 });
  await page.mouse.up();
}

export async function waitForItemStatus(api: Api, item: Item, status: string) {
  await expect
    .poll(async () => (await api.getItem(item.id)).data.status, { timeout: 10_000 })
    .toBe(status);
}
