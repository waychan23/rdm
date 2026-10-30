import { useState } from "react";
import { useParams } from "react-router-dom";

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
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Workspace } from "../types";
import "../styles/table.css";

const KINDS = ["git_repo", "doc_repo", "design", "other"];
const KIND_OPTIONS = KINDS.map((v) => ({ label: v, value: v }));

const styles = cssMap({
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
});

interface Option {
  label: string;
  value: string;
}

const isHttpLocation = (value: string) => /^https?:\/\//i.test(value);

export default function WorkspacesPage() {
  const { key: projectKey = "" } = useParams();
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
    kind: KIND_OPTIONS[0],
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
      kind: KIND_OPTIONS[0],
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
      kind: KIND_OPTIONS.find((k) => k.value === w.kind) ?? KIND_OPTIONS[0],
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
      notify.success("保存成功");
    } catch (e) {
      setSaveError(errorCause(e)?.message ?? "请稍后重试");
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
      notify.error("删除失败", errorCause(e)?.message);
    } finally {
      setConfirmId(null);
    }
  };

  return (
    <Page testId="page-workspaces">
      <PageHeader
        title={`工作区 · ${projectKey}`}
        testId="workspaces-header"
        actions={
          <Button appearance="primary" testId="workspace-create-button" onClick={openCreate}>
            登记工作区
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
            header="还没有登记工作区"
            description="登记仓库、文档或设计资源，方便团队成员快速跳转。"
          />
        </Box>
      ) : (
        <table className="rdm-table" aria-label="工作区列表" data-testid="workspace-table">
          <thead>
            <tr>
              <th scope="col">名称</th>
              <th scope="col" className="col-type">
                类型
              </th>
              <th scope="col">存储位置</th>
              <th scope="col" className="col-actions">
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            {(workspaces ?? []).map((w) => (
              <tr key={w.id} data-testid={`workspace-row-${w.id}`}>
                <td>{w.name}</td>
                <td className="cell-meta">{w.kind}</td>
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
                      编辑
                    </Button>
                    <Button
                      spacing="compact"
                      appearance="danger"
                      testId={`workspace-delete-${w.id}`}
                      onClick={() => setConfirmId(w.id)}
                    >
                      删除
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
              <ModalTitle>{form.id ? "编辑工作区" : "登记工作区"}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              {saveError && (
                <Box paddingBlockEnd="space.150">
                  <SectionMessage
                    appearance="error"
                    title="保存失败"
                    testId="workspace-save-error"
                    isDismissible
                    onDismiss={() => setSaveError(null)}
                  >
                    {saveError}
                  </SectionMessage>
                </Box>
              )}
              <Stack space="space.150">
                <FormField label="名称" htmlFor="ws-name">
                  <Textfield
                    id="ws-name"
                    value={form.name}
                    testId="workspace-form-name"
                    onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
                  />
                </FormField>
                <FormField label="类型">
                  <Select {...portalMenuProps}
                    options={KIND_OPTIONS}
                    value={form.kind}
                    onChange={(o) => o && setForm({ ...form, kind: o as Option })}
                  />
                </FormField>
                <FormField
                  label="存储位置"
                  htmlFor="ws-location"
                  hint="可选；支持 http(s)、git SSH、挂载路径、s3:// 等任意格式。"
                >
                  <Textfield
                    id="ws-location"
                    value={form.location}
                    placeholder="可选，如 https://… / git@github.com:org/repo.git"
                    testId="workspace-form-location"
                    onChange={(e) => setForm({ ...form, location: e.currentTarget.value })}
                  />
                </FormField>
                <FormField label="描述">
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
                取消
              </Button>
              <Button
                appearance="primary"
                isLoading={saving}
                isDisabled={!form.name.trim()}
                testId="workspace-form-submit"
                onClick={() => void save()}
              >
                保存
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
              <ModalTitle>确认删除</ModalTitle>
            </ModalHeader>
            <ModalBody>删除该工作区？软删可恢复。</ModalBody>
            <ModalFooter>
              <Button
                appearance="subtle"
                testId="workspace-delete-cancel"
                onClick={() => setConfirmId(null)}
              >
                取消
              </Button>
              <Button
                appearance="danger"
                testId="workspace-delete-confirm"
                onClick={() => void remove()}
              >
                删除
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Page>
  );
}
