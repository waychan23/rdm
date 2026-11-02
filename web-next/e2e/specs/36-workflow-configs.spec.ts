import { expect, test } from "../support/fixtures";

// RDM-84: workflow configs are imported into the DB, listed/edited in the web
// UI, and selected when creating a project.
test.describe("workflow configs", () => {
  test("builtin is read-only, fork is editable, and a key can be enabled/disabled", async ({
    page,
    app,
  }) => {
    await page.goto(`${app.baseURL}/workflow-configs`);
    await expect(page.getByTestId("page-workflow-configs")).toBeVisible();

    const builtin = page.getByTestId("workflow-config-default");
    await expect(builtin).toContainText("默认工作流");
    await expect(builtin).toContainText("内置");

    await page.getByTestId("workflow-config-open-default").click();
    await expect(page.getByTestId("workflow-config-dialog")).toBeVisible();
    // Builtins expose Fork but never Save.
    await expect(page.getByTestId("workflow-config-save")).toHaveCount(0);
    await page.getByTestId("workflow-config-fork").click();
    await expect(page.getByTestId("workflow-config-fork-dialog")).toBeVisible();

    const key = `e2eui${Date.now().toString(36)}`;
    await page.getByTestId("workflow-fork-key").fill(key);
    await page.getByTestId("workflow-fork-name").fill("E2E UI Flow");
    await page.getByTestId("workflow-fork-submit").click();

    await expect(page.getByTestId("workflow-config-dialog")).toBeHidden();
    const card = page.getByTestId(`workflow-config-${key}`);
    await expect(card).toBeVisible();
    await expect(card).toContainText("E2E UI Flow");
    await expect(card).toContainText("自定义");

    // Edit the current active version -> a new DB version becomes active.
    await page.getByTestId(`workflow-config-open-${key}`).click();
    const editor = page.getByTestId("workflow-config-content");
    await expect(editor).toBeEditable();
    const raw = JSON.parse(await editor.inputValue());
    raw.kinds.story.label = "E2E UI Story";
    await editor.fill(JSON.stringify(raw, null, 2));
    await page.getByTestId("workflow-config-save").click();

    await expect(
      page.getByTestId("notice-success").filter({ hasText: "已保存新版本 v2" }),
    ).toBeVisible();
    await expect(page.getByTestId("workflow-config-dialog")).toBeHidden();
    await expect(card).toContainText("2 个版本");
    await expect(card).toContainText("活跃版本 v2");

    // RDM-85: historical versions are viewable read-only; returning restores
    // the editable active content.
    await page.getByTestId(`workflow-config-open-${key}`).click();
    await page.getByTestId("workflow-config-version-view-1").click();
    const historyEditor = page.getByTestId("workflow-config-content");
    await expect(historyEditor).toHaveValue(/E2E UI Flow/);
    await expect(historyEditor).not.toHaveValue(/E2E UI Story/);
    await expect(page.getByTestId("workflow-config-save")).toHaveCount(0);
    await page.getByTestId("workflow-config-back-active").click();
    await expect(page.getByTestId("workflow-config-content")).toHaveValue(/E2E UI Story/);

    // RDM-85: re-saving identical content does not create a duplicate version.
    await page.getByTestId("workflow-config-save").click();
    await expect(
      page.getByTestId("notice-success").filter({ hasText: "未创建新版本" }),
    ).toBeVisible();
    await expect(page.getByTestId("workflow-config-dialog")).toBeHidden();
    await expect(card).toContainText("2 个版本");

    // Disable then re-enable: disabled configs stay visible but cannot be
    // selected by new projects (covered by the backend contract tests).
    await page.getByTestId(`workflow-config-toggle-${key}`).click();
    await expect(card).toContainText("停用");
    await page.getByTestId(`workflow-config-toggle-${key}`).click();
    await expect(card).toContainText("启用");
  });

  test("creating a project requires picking an enabled workflow config", async ({
    page,
    app,
  }) => {
    const key = `PW${Date.now().toString(36).toUpperCase()}`.slice(0, 12);

    await page.goto(`${app.baseURL}/projects`);
    await page.getByTestId("projects-create-button").click();
    await page.getByTestId("project-create-key").fill(key);
    await page.getByTestId("project-create-name").fill("Picked workflow");

    // Missing selection is rejected client-side.
    await page.getByTestId("project-create-submit").click();
    await expect(page.getByTestId("notice-error")).toContainText("工作流配置");
    await expect(page.getByTestId("project-create-dialog")).toBeVisible();

    await page
      .getByTestId("project-create-dialog")
      .getByRole("combobox")
      .click();
    await page.getByRole("option", { name: /E2E Workflow/ }).first().click();
    await page.getByTestId("project-create-submit").click();

    await expect(page.getByTestId("project-create-dialog")).toBeHidden();
    await expect(page.getByTestId(`project-card-${key}`)).toBeVisible();

    // RDM-86: project settings must echo the selected config, not fall back to
    // an empty select because the lookup only lists active/enabled versions.
    await page.goto(`${app.baseURL}/projects/${key}/settings`);
    await expect(page.getByTestId("project-settings-form")).toContainText("E2E Workflow");
    await expect(page.locator("#project-workflow")).toBeVisible();
  });

  test("project settings offers and applies a newer config version", async ({
    api,
    page,
    app,
  }) => {
    const stamp = Date.now().toString(36);
    const key = `UP${stamp.toUpperCase()}`.slice(0, 12);
    const flowKey = `up${stamp}`;

    const forked = (
      await api.post<{ version: { id: string; content_text: string } }>(
        "/workflow-configs/default/fork",
        { key: flowKey, name: "Upgrade Flow" },
      )
    ).data;
    await api.post("/projects", {
      key,
      name: "Upgrade project",
      workflow_config_version_id: forked.version.id,
    });

    const raw = JSON.parse(forked.version.content_text);
    raw.kinds.story.label = "Upgraded story";
    await api.post(`/workflow-configs/${flowKey}/versions`, {
      content_text: `${JSON.stringify(raw, null, 2)}\n`,
      base_version_id: forked.version.id,
    });

    await page.goto(`${app.baseURL}/projects/${key}/settings`);
    await expect(page.getByTestId("project-settings-form")).toContainText("Upgrade Flow");
    await expect(page.getByTestId("project-workflow-upgrade")).toBeVisible();

    await page.getByTestId("project-workflow-upgrade").click();
    await expect(page.getByTestId("project-workflow-upgrade-dialog")).toBeVisible();
    await page.getByTestId("project-workflow-upgrade-dialog-confirm").click();

    await expect(
      page.getByTestId("notice-success").filter({ hasText: "已升级到 v2" }),
    ).toBeVisible();
    await expect(page.getByTestId("project-workflow-upgrade")).toHaveCount(0);
    await expect(page.getByTestId("project-settings-form")).toContainText("v2");
  });
});
