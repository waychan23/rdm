import { expect, test } from "../support/fixtures";
import { beginInlineEdit, expectSuccessNotice, openItem } from "../support/ui";

// RDM-28: hours fields keep the raw text while editing (so "0." and deletion
// work) and keep at most one decimal digit.
test("create dialog accepts a decimal hours value", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  await page.goto(`${app.baseURL}/projects/${projectKey}/backlog`);

  await page.getByTestId("work-item-create-button").click();
  await page.getByRole("radio", { name: "任务" }).click();
  await page.getByTestId("work-item-create-title").fill(`hours-create-${Date.now()}`);

  const hours = page.getByTestId("wi-est-hours");
  await hours.fill("");
  await expect(hours).toHaveValue("");
  await hours.pressSequentially("0.55");
  await expect(hours).toHaveValue("0.5");

  await page.getByTestId("work-item-create-submit").click();
  await expectSuccessNotice(page, "已创建");
  await expect(page.getByTestId("item-est-work-hours")).toContainText("0.5h");
});

test("edit dialog accepts a decimal hours value", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  const task = await api.createItemIn(projectKey, {
    kind: "task",
    title: `hours-edit-${Date.now()}`,
    assignee: "alice",
  });

  await openItem(page, app, task, projectKey);
  await page.getByTestId("item-panel-edit").click();

  const hours = page.getByTestId("wi-est-hours");
  await expect(hours).toHaveValue("0");
  await hours.fill("");
  await expect(hours).toHaveValue("");
  await hours.pressSequentially("1.25");
  await expect(hours).toHaveValue("1.2");

  await page.getByTestId("work-item-edit-submit").click();
  await expectSuccessNotice(page, "保存成功");
  await expect(page.getByTestId("item-est-work-hours")).toContainText("1.2h");
});

test("drawer inline hours edit limits decimals while typing", async ({ api, app, page }) => {
  const projectKey = await api.createSandboxProject(["alice"]);
  const task = await api.createItemIn(projectKey, {
    kind: "task",
    title: `hours-inline-${Date.now()}`,
    assignee: "alice",
  });

  await openItem(page, app, task, projectKey);
  await beginInlineEdit(page, "item-est-work-hours");
  const input = page.getByTestId("item-est-work-hours-input");
  await input.click();
  await input.press("ControlOrMeta+a");
  await input.pressSequentially("2.34", { delay: 20 });
  // The extra digit is dropped on the keystroke, before saving.
  await expect(input).toHaveValue("2.3");

  await page.getByTestId("item-est-work-hours-save").click();
  await expectSuccessNotice(page, "保存成功");
  await expect(page.getByTestId("item-est-work-hours")).toContainText("2.3h");
});
