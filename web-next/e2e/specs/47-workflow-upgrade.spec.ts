import { expect, test } from "../support/fixtures";
import { expectSuccessNotice, openItem } from "../support/ui";

interface ConfigVersion {
  id: string;
  version: number;
  content_text: string;
}

interface ConfigDetail {
  key: string;
  active_version: ConfigVersion;
  versions: ConfigVersion[];
}

test.describe("workflow: upgrade pinned definition", () => {
  test("shows the config key, upgrades, and records history", async ({
    api,
    app,
    page,
  }) => {
    const projectKey = await api.createSandboxProject();
    const item = await api.createItemIn(projectKey, {
      kind: "story",
      title: `workflow-upgrade-${Date.now()}`,
    });

    // Fork the e2e config, change the story label, and switch the project to
    // the new version. Existing items stay pinned until the user upgrades.
    const source = (await api.get<ConfigDetail>("/workflow-configs/e2e")).data;
    const forked = (
      await api.post<{ version: ConfigVersion }>("/workflow-configs/e2e/fork", {
        key: "e2e_upgrade",
        name: "E2E Upgrade",
      })
    ).data;
    const raw = JSON.parse(forked.version.content_text) as Record<string, any>;
    raw.kinds.story.label = "需求（升级后）";
    const saved = (
      await api.post<{ version: ConfigVersion }>(
        "/workflow-configs/e2e_upgrade/versions",
        {
          content_text: `${JSON.stringify(raw, null, 2)}\n`,
          base_version_id: forked.version.id,
        },
      )
    ).data.version;
    await api.request("PATCH", `/projects/${projectKey}`, {
      workflow_config_version_id: saved.id,
    });

    await openItem(page, app, item, projectKey);
    await expect(page.getByTestId("item-version-line")).toContainText(
      source.key,
    );
    const upgrade = page.getByTestId("item-workflow-upgrade");
    await expect(upgrade).toBeVisible();
    await upgrade.click();

    const dialog = page.getByTestId("item-workflow-upgrade-dialog");
    await expect(dialog).toBeVisible();
    await page.getByTestId("item-workflow-upgrade-dialog-confirm").click();
    await expectSuccessNotice(page, "流程已升级");

    await expect(page.getByTestId("item-version-line")).toContainText(
      "e2e_upgrade",
    );
    await page.getByTestId("item-history-toggle").click();
    await expect(page.getByTestId("item-history-list")).toContainText(
      "升级了流程",
    );
    await expect(page.getByTestId("item-history-list")).toContainText(
      "e2e_upgrade",
    );
  });
});
