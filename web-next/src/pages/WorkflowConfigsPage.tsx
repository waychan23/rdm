import { useEffect, useState, type CSSProperties, type FormEvent } from "react";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import EmptyState from "@atlaskit/empty-state";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import TextArea from "@atlaskit/textarea";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

import { cardBorder } from "../components/cardBorder";
import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { useCurrentUser } from "../lib/auth";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { WorkflowConfig, WorkflowConfigVersion } from "../types";

const styles = cssMap({
  card: {
    display: "block",
    width: "100%",
    padding: "var(--ds-space-250)",
    borderRadius: "var(--ds-radius-small)",
    backgroundColor: "var(--ds-surface)",
    color: "var(--ds-text)",
  },
  loading: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
  list: {
    display: "grid",
    gap: "var(--ds-space-150)",
  },
  meta: {
    color: "var(--ds-text-subtlest)",
    paddingBlockEnd: "var(--ds-space-200)",
  },
});

const CODE_STYLE: CSSProperties = {
  width: "100%",
  fontFamily: "var(--ds-font-family-code, ui-monospace, SFMono-Regular, Menlo, monospace)",
  lineHeight: "20px",
};

const HISTORY_STYLE: CSSProperties = {
  borderCollapse: "collapse",
  width: "100%",
  fontSize: "12px",
};

const HISTORY_CELL_STYLE: CSSProperties = {
  textAlign: "start",
  padding: "4px 8px",
  borderBlockEnd: "1px solid var(--ds-border)",
};

interface ForkForm {
  key: string;
  name: string;
}

const EMPTY_FORK: ForkForm = { key: "", name: "" };

export default function WorkflowConfigsPage() {
  const { t } = useTranslation("workflows");
  const notify = useNotify();
  const me = useCurrentUser();
  const canEdit = !!me && (me.org_roles.includes("org_owner") || me.org_roles.includes("user_manager"));

  const [nonce, setNonce] = useState(0);
  const [selected, setSelected] = useState<WorkflowConfig | null>(null);
  const [content, setContent] = useState("");
  const [viewing, setViewing] = useState<WorkflowConfigVersion | null>(null);
  const [saving, setSaving] = useState(false);
  const [forkOpen, setForkOpen] = useState(false);
  const [forkForm, setForkForm] = useState<ForkForm>(EMPTY_FORK);
  const [forking, setForking] = useState(false);

  const { data: configs, loading, error } = useAsync(
    async () => (await api.get<WorkflowConfig[]>("/workflow-configs")).data,
    [nonce],
  );

  const reload = () => setNonce((n) => n + 1);

  useEffect(() => {
    if (!selected) return;
    setViewing(null);
    setContent(selected.active_version?.content_text ?? "");
  }, [selected]);

  const open = async (key: string) => {
    try {
      const detail = (await api.get<WorkflowConfig>(`/workflow-configs/${encodeURIComponent(key)}`)).data;
      setSelected(detail);
    } catch (e) {
      notify.error(t("loadFailed"), errorCause(e)?.message);
    }
  };

  const viewVersion = async (version: WorkflowConfigVersion) => {
    try {
      const detail = (
        await api.get<WorkflowConfigVersion>(
          `/workflow-configs/versions/${encodeURIComponent(version.id)}`,
        )
      ).data;
      setContent(detail.content_text ?? "");
      setViewing(detail);
    } catch (e) {
      notify.error(t("loadFailed"), errorCause(e)?.message);
    }
  };

  const backToActive = () => {
    setViewing(null);
    setContent(selected?.active_version?.content_text ?? "");
  };

  const save = async () => {
    if (!selected?.active_version || saving || viewing) return;
    setSaving(true);
    try {
      const result = await api.post<{ created: boolean; version: WorkflowConfigVersion }>(
        `/workflow-configs/${encodeURIComponent(selected.key)}/versions`,
        { content_text: content, base_version_id: selected.active_version.id },
      );
      if (result.data.created) {
        notify.success(t("editor.saveSuccess", { version: result.data.version.version }));
      } else {
        notify.success(t("editor.noChange"));
      }
      setSelected(null);
      reload();
    } catch (e) {
      notify.error(t("editor.saveFailed"), errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (config: WorkflowConfig) => {
    try {
      await api.patch(`/workflow-configs/${encodeURIComponent(config.key)}`, {
        enabled: !config.enabled,
      });
      notify.success(
        t("editor.toggleSuccess", {
          name: config.name,
          state: t(config.enabled ? "disabled" : "enabled"),
        }),
      );
      reload();
    } catch (e) {
      notify.error(t("editor.toggleFailed"), errorCause(e)?.message);
    }
  };

  const fork = async (e: FormEvent) => {
    e.preventDefault();
    if (!selected || forking) return;
    setForking(true);
    try {
      await api.post(`/workflow-configs/${encodeURIComponent(selected.key)}/fork`, forkForm);
      notify.success(t("editor.forkSuccess", { key: forkForm.key }));
      setForkOpen(false);
      setForkForm(EMPTY_FORK);
      setSelected(null);
      reload();
    } catch (e) {
      notify.error(t("editor.forkFailed"), errorCause(e)?.message);
    } finally {
      setForking(false);
    }
  };

  return (
    <Page testId="page-workflow-configs">
      <PageHeader title={t("title")} testId="workflow-configs-header" />
      <Box xcss={styles.meta}>
        <Text size="small">{t("subtitle")}</Text>
      </Box>

      {loading ? (
        <Box xcss={styles.loading} testId="workflow-configs-loading">
          <Spinner size="large" />
        </Box>
      ) : error ? (
        <SectionMessage appearance="error" title={t("loadFailed")}>
          {t("loadFailedDescription")}
        </SectionMessage>
      ) : (configs ?? []).length === 0 ? (
        <EmptyState header={t("empty")} description={t("emptyDescription")} />
      ) : (
        <Box xcss={styles.list} testId="workflow-configs-list">
          {(configs ?? []).map((config) => (
            <Box key={config.id} xcss={styles.card} style={cardBorder} testId={`workflow-config-${config.key}`}>
              <Inline space="space.150" alignBlock="center" spread="space-between">
                <Stack space="space.050">
                  <Inline space="space.100" alignBlock="center">
                    <Text weight="semibold">{config.name}</Text>
                    <Lozenge appearance={config.is_builtin ? "default" : "inprogress"}>
                      {t(config.is_builtin ? "builtin" : "custom")}
                    </Lozenge>
                    <Lozenge appearance={config.enabled ? "success" : "default"}>
                      {t(config.enabled ? "enabled" : "disabled")}
                    </Lozenge>
                  </Inline>
                  <Text size="small" color="color.text.subtlest">
                    {config.key} · {t("versionCount", { count: config.version_count })}
                    {config.active_version
                      ? ` · ${t("activeVersion", {
                          version: config.active_version.version,
                          schema: config.active_version.schema_version,
                          revision: config.active_version.revision,
                        })}`
                      : null}
                  </Text>
                </Stack>
                <Inline space="space.100">
                  <Button
                    appearance="subtle"
                    testId={`workflow-config-open-${config.key}`}
                    onClick={() => void open(config.key)}
                  >
                    {t("actions.open")}
                  </Button>
                  {canEdit ? (
                    <Button
                      appearance="subtle"
                      testId={`workflow-config-toggle-${config.key}`}
                      onClick={() => void toggle(config)}
                    >
                      {t(config.enabled ? "actions.disable" : "actions.enable")}
                    </Button>
                  ) : null}
                </Inline>
              </Inline>
            </Box>
          ))}
        </Box>
      )}

      <ModalTransition>
        {selected ? (
          <ModalDialog width="x-large" onClose={() => setSelected(null)} testId="workflow-config-dialog">
            <ModalHeader>
              <ModalTitle>{t("editor.title", { name: selected.name })}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.200">
                <Inline space="space.100" alignBlock="center">
                  <Text size="small" color="color.text.subtlest">
                    {t("editor.key")}: {selected.key}
                  </Text>
                  <Lozenge appearance={selected.is_builtin ? "default" : "inprogress"}>
                    {t(selected.is_builtin ? "builtin" : "custom")}
                  </Lozenge>
                  {selected.active_version ? (
                    <Text size="small" color="color.text.subtlest">
                      {t("editor.forkSource", {
                        key: selected.key,
                        version: selected.active_version.version,
                      })}
                    </Text>
                  ) : null}
                </Inline>

                {selected.is_builtin ? (
                  <SectionMessage appearance="information">{t("editor.readonly")}</SectionMessage>
                ) : null}
                {viewing ? (
                  <Inline space="space.100" alignBlock="center" spread="space-between">
                    <SectionMessage appearance="information">
                      {t("history.viewing", { version: viewing.version })}
                    </SectionMessage>
                    <Button
                      appearance="subtle"
                      testId="workflow-config-back-active"
                      onClick={backToActive}
                    >
                      {t("history.back")}
                    </Button>
                  </Inline>
                ) : null}

                <FormField label={t("editor.content")} htmlFor="workflow-config-content">
                  <TextArea
                    id="workflow-config-content"
                    value={content}
                    minimumRows={18}
                    isReadOnly={!!viewing || selected.is_builtin || !canEdit}
                    testId="workflow-config-content"
                    style={CODE_STYLE}
                    onChange={(e) => setContent(e.currentTarget.value)}
                  />
                </FormField>

                {selected.versions && selected.versions.length > 0 ? (
                  <Stack space="space.100">
                    <Heading size="small">{t("history.title")}</Heading>
                    <table style={HISTORY_STYLE}>
                      <thead>
                        <tr>
                          <th style={HISTORY_CELL_STYLE}>{t("history.version")}</th>
                          <th style={HISTORY_CELL_STYLE}>{t("history.schema")}</th>
                          <th style={HISTORY_CELL_STYLE}>{t("history.revision")}</th>
                          <th style={HISTORY_CELL_STYLE}>{t("history.source")}</th>
                          <th style={HISTORY_CELL_STYLE}>{t("history.createdAt")}</th>
                          <th style={HISTORY_CELL_STYLE}>{t("history.actions")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selected.versions.map((version) => (
                          <tr key={version.id}>
                            <td style={HISTORY_CELL_STYLE}>
                              v{version.version}{" "}
                              {version.is_active ? <Lozenge appearance="success">{t("history.active")}</Lozenge> : null}
                            </td>
                            <td style={HISTORY_CELL_STYLE}>{version.schema_version}</td>
                            <td style={HISTORY_CELL_STYLE}>{version.revision}</td>
                            <td style={HISTORY_CELL_STYLE}>
                              {version.source_version_id ? version.source_version_id : t("history.none")}
                            </td>
                            <td style={HISTORY_CELL_STYLE}>{version.created_at}</td>
                            <td style={HISTORY_CELL_STYLE}>
                              <Button
                                appearance="subtle"
                                testId={`workflow-config-version-view-${version.version}`}
                                onClick={() => void viewVersion(version)}
                              >
                                {t("history.view")}
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Stack>
                ) : null}
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setSelected(null)}>
                {t("editor.cancel")}
              </Button>
              {viewing ? null : selected.is_builtin || !canEdit ? (
                canEdit ? (
                  <Button
                    appearance="primary"
                    testId="workflow-config-fork"
                    onClick={() => setForkOpen(true)}
                  >
                    {t("actions.fork")}
                  </Button>
                ) : null
              ) : (
                <Button
                  appearance="primary"
                  isLoading={saving}
                  isDisabled={!selected.active_version}
                  testId="workflow-config-save"
                  onClick={() => void save()}
                >
                  {t("editor.save")}
                </Button>
              )}
            </ModalFooter>
          </ModalDialog>
        ) : null}
      </ModalTransition>

      <ModalTransition>
        {forkOpen && selected ? (
          <ModalDialog onClose={() => setForkOpen(false)} testId="workflow-config-fork-dialog">
            <ModalHeader>
              <ModalTitle>{t("editor.forkTitle")}</ModalTitle>
            </ModalHeader>
            <form onSubmit={fork}>
              <ModalBody>
                <Stack space="space.150">
                  <Text size="small">{t("editor.forkHint")}</Text>
                  {selected.active_version ? (
                    <Text size="small" color="color.text.subtlest">
                      {t("editor.forkSource", {
                        key: selected.key,
                        version: selected.active_version.version,
                      })}
                    </Text>
                  ) : null}
                  <FormField label={t("editor.forkKey")} htmlFor="workflow-fork-key">
                    <Textfield
                      id="workflow-fork-key"
                      value={forkForm.key}
                      testId="workflow-fork-key"
                      onChange={(e) => setForkForm({ ...forkForm, key: e.currentTarget.value })}
                    />
                  </FormField>
                  <FormField label={t("editor.forkName")} htmlFor="workflow-fork-name">
                    <Textfield
                      id="workflow-fork-name"
                      value={forkForm.name}
                      testId="workflow-fork-name"
                      onChange={(e) => setForkForm({ ...forkForm, name: e.currentTarget.value })}
                    />
                  </FormField>
                </Stack>
              </ModalBody>
              <ModalFooter>
                <Button appearance="subtle" onClick={() => setForkOpen(false)}>
                  {t("editor.cancel")}
                </Button>
                <Button type="submit" appearance="primary" isLoading={forking} testId="workflow-fork-submit">
                  {t("editor.forkSubmit")}
                </Button>
              </ModalFooter>
            </form>
          </ModalDialog>
        ) : null}
      </ModalTransition>
    </Page>
  );
}
