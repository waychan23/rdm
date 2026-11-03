import { useState } from "react";
import { useParams } from "react-router-dom";
import { useListProjectKey } from "../lib/originSearch";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import EmptyState from "@atlaskit/empty-state";
import Link from "@atlaskit/link";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Select from "@atlaskit/select";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack } from "@atlaskit/primitives/compiled";
import { portalMenuProps } from "../lib/portalMenu";

import ErrorState from "../components/ErrorState";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { workspaceKindLabel } from "../lib/labels";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Workspace } from "../types";
import "../styles/table.css";

const KINDS = ["git_repo", "doc_repo", "design", "other"];
const kindOptions = () => KINDS.map((v) => ({ label: workspaceKindLabel(v), value: v }));

const styles = cssMap({
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
  saveError: {
    paddingBlockEnd: "var(--ds-space-150)",
  },
});

interface Option {
  label: string;
  value: string;
}

const isHttpLocation = (value: string) => /^https?:\/\//i.test(value);

export default function WorkspacesPage() {
  const { t } = useTranslation("projects");
  const { key: routeKey = "" } = useParams();
  // The origin URL owns the project while this page is a drawer backdrop.
  const projectKey = useListProjectKey(routeKey);
  const notify = useNotify();

  const [nonce, setNonce] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [form, setForm] = useState<{
    id: string;
    name: string;
    kind: Option;
    location: string;
    description_md: string;
  }>({
    id: "",
    name: "",
    kind: kindOptions()[0],
    location: "",
    description_md: "",
  });

  const { data: workspaces, loading, error } = useAsync<Workspace[]>(
    async () => (await api.get<Workspace[]>(`/projects/${projectKey}/workspaces`)).data,
    [projectKey, nonce],
  );

  const reload = () => setNonce((n) => n + 1);

  const openCreate = () => {
    setSaveError(null);
    setForm({
      id: "",
      name: "",
      kind: kindOptions()[0],
      location: "",
      description_md: "",
    });
    setDialogOpen(true);
  };

  const openEdit = (w: Workspace) => {
    setSaveError(null);
    setForm({
      id: w.id,
      name: w.name,
      kind: kindOptions().find((k) => k.value === w.kind) ?? kindOptions()[0],
      location: w.url,
      description_md: w.description_md ?? "",
    });
    setDialogOpen(true);
  };

  const save = async () => {
    if (!form.name.trim() || saving) return;
    setSaveError(null);
    setSaving(true);
    const payload = {
      name: form.name,
      kind: form.kind.value,
      url: form.location.trim(),
      description_md: form.description_md || null,
    };
    try {
      if (form.id) await api.patch(`/workspaces/${form.id}`, payload);
      else await api.post(`/projects/${projectKey}/workspaces`, payload);
      setDialogOpen(false);
      reload();
      notify.success(t("workspaces.saveSuccess"));
    } catch (e) {
      setSaveError(errorCause(e)?.message ?? t("workspaces.saveRetry"));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!confirmId) return;
    try {
      await api.del(`/workspaces/${confirmId}`);
      reload();
    } catch (e) {
      notify.error(t("workspaces.deleteFailed"), errorCause(e)?.message);
    } finally {
      setConfirmId(null);
    }
  };

  return (
    <Page testId="page-workspaces">
      <PageHeader
        title={t("workspaces.title", { key: projectKey })}
        testId="workspaces-header"
        actions={
          <Button appearance="primary" testId="workspace-create-button" onClick={openCreate}>
            {t("workspaces.create")}
          </Button>
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={reload} testId="workspaces-error" />
      ) : loading ? (
        <Box xcss={styles.centered} testId="workspaces-loading">
          <Spinner size="large" />
        </Box>
      ) : (workspaces ?? []).length === 0 ? (
        <Box testId="workspaces-empty">
          <EmptyState
            header={t("workspaces.empty")}
            description={t("workspaces.emptyDescription")}
          />
        </Box>
      ) : (
        <table
          className="rdm-table"
          aria-label={t("workspaces.tableLabel")}
          data-testid="workspace-table"
        >
          <thead>
            <tr>
              <th scope="col">{t("workspaces.col.name")}</th>
              <th scope="col" className="col-type">
                {t("workspaces.col.kind")}
              </th>
              <th scope="col">{t("workspaces.col.location")}</th>
              <th scope="col" className="col-actions">
                {t("workspaces.col.actions")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(workspaces ?? []).map((w) => (
              <tr key={w.id} data-testid={`workspace-row-${w.id}`}>
                <td>{w.name}</td>
                <td className="cell-meta">{workspaceKindLabel(w.kind)}</td>
                <td>
                  {isHttpLocation(w.url) ? (
                    <Link href={w.url} target="_blank" testId={`workspace-link-${w.id}`}>
                      {w.url}
                    </Link>
                  ) : (
                    <span data-testid={`workspace-location-${w.id}`}>{w.url || "—"}</span>
                  )}
                </td>
                <td>
                  <Inline space="space.100">
                    <Button
                      spacing="compact"
                      testId={`workspace-edit-${w.id}`}
                      onClick={() => openEdit(w)}
                    >
                      {t("workspaces.edit")}
                    </Button>
                    <Button
                      spacing="compact"
                      appearance="danger"
                      testId={`workspace-delete-${w.id}`}
                      onClick={() => setConfirmId(w.id)}
                    >
                      {t("workspaces.delete")}
                    </Button>
                  </Inline>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ModalTransition>
        {dialogOpen && (
          <ModalDialog
            onClose={() => setDialogOpen(false)}
            width="460px"
            testId="workspace-form-dialog"
          >
            <ModalHeader>
              <ModalTitle>
                {form.id ? t("workspaces.form.editTitle") : t("workspaces.form.createTitle")}
              </ModalTitle>
            </ModalHeader>
            <ModalBody>
              {saveError && (
                <Box xcss={styles.saveError}>
                  <SectionMessage
                    appearance="error"
                    title={t("workspaces.saveFailed")}
                    testId="workspace-save-error"
                    isDismissible
                    onDismiss={() => setSaveError(null)}
                  >
                    {saveError}
                  </SectionMessage>
                </Box>
              )}
              <Stack space="space.150">
                <FormField label={t("workspaces.form.name")} htmlFor="ws-name">
                  <Textfield
                    id="ws-name"
                    value={form.name}
                    testId="workspace-form-name"
                    onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
                  />
                </FormField>
                <FormField label={t("workspaces.form.kind")}>
                  <Select {...portalMenuProps}
                    options={kindOptions()}
                    value={form.kind}
                    onChange={(o) => o && setForm({ ...form, kind: o as Option })}
                  />
                </FormField>
                <FormField
                  label={t("workspaces.form.location")}
                  htmlFor="ws-location"
                  hint={t("workspaces.form.locationHint")}
                >
                  <Textfield
                    id="ws-location"
                    value={form.location}
                    placeholder={t("workspaces.form.locationPlaceholder")}
                    testId="workspace-form-location"
                    onChange={(e) => setForm({ ...form, location: e.currentTarget.value })}
                  />
                </FormField>
                <FormField label={t("workspaces.form.description")}>
                  <MarkdownEditor
                    value={form.description_md}
                    onChange={(value) => setForm({ ...form, description_md: value })}
                    projectKey={projectKey}
                    minimumRows={3}
                    testId="workspace-form-description"
                  />
                </FormField>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button
                appearance="subtle"
                testId="workspace-form-cancel"
                onClick={() => setDialogOpen(false)}
              >
                {t("workspaces.form.cancel")}
              </Button>
              <Button
                appearance="primary"
                isLoading={saving}
                isDisabled={!form.name.trim()}
                testId="workspace-form-submit"
                onClick={() => void save()}
              >
                {t("workspaces.form.save")}
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {confirmId && (
          <ModalDialog
            onClose={() => setConfirmId(null)}
            width="420px"
            testId="workspace-delete-dialog"
          >
            <ModalHeader>
              <ModalTitle>{t("workspaces.deleteConfirm.title")}</ModalTitle>
            </ModalHeader>
            <ModalBody>{t("workspaces.deleteConfirm.body")}</ModalBody>
            <ModalFooter>
              <Button
                appearance="subtle"
                testId="workspace-delete-cancel"
                onClick={() => setConfirmId(null)}
              >
                {t("workspaces.deleteConfirm.cancel")}
              </Button>
              <Button
                appearance="danger"
                testId="workspace-delete-confirm"
                onClick={() => void remove()}
              >
                {t("workspaces.deleteConfirm.confirm")}
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Page>
  );
}
