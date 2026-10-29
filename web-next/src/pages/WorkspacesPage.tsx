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
import Spinner from "@atlaskit/spinner";
import TextArea from "@atlaskit/textarea";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack } from "@atlaskit/primitives/compiled";
import { portalMenuProps } from "../lib/portalMenu";

import FormField from "../components/FormField";
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

export default function WorkspacesPage() {
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();

  const [nonce, setNonce] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<{
    id: string;
    name: string;
    kind: Option;
    url: string;
    default_branch: string;
    description_md: string;
  }>({
    id: "",
    name: "",
    kind: KIND_OPTIONS[0],
    url: "",
    default_branch: "",
    description_md: "",
  });

  const { data: workspaces, loading } = useAsync<Workspace[]>(
    async () => (await api.get<Workspace[]>(`/projects/${projectKey}/workspaces`)).data,
    [projectKey, nonce],
  );

  const reload = () => setNonce((n) => n + 1);

  const openCreate = () => {
    setForm({
      id: "",
      name: "",
      kind: KIND_OPTIONS[0],
      url: "",
      default_branch: "",
      description_md: "",
    });
    setDialogOpen(true);
  };

  const openEdit = (w: Workspace) => {
    setForm({
      id: w.id,
      name: w.name,
      kind: KIND_OPTIONS.find((k) => k.value === w.kind) ?? KIND_OPTIONS[0],
      url: w.url,
      default_branch: w.default_branch ?? "",
      description_md: w.description_md ?? "",
    });
    setDialogOpen(true);
  };

  const save = async () => {
    if (!form.name.trim() || !form.url.trim() || saving) return;
    setSaving(true);
    const payload = {
      name: form.name,
      kind: form.kind.value,
      url: form.url,
      default_branch: form.default_branch || null,
      description_md: form.description_md || null,
    };
    try {
      if (form.id) await api.patch(`/workspaces/${form.id}`, payload);
      else await api.post(`/projects/${projectKey}/workspaces`, payload);
      setDialogOpen(false);
      reload();
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
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

      {loading ? (
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
              <th scope="col">URL</th>
              <th scope="col" className="col-branch">
                默认分支
              </th>
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
                  <Link href={w.url} target="_blank" testId={`workspace-link-${w.id}`}>
                    {w.url}
                  </Link>
                </td>
                <td className="cell-meta">{w.default_branch ?? "—"}</td>
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
                <FormField label="URL" htmlFor="ws-url">
                  <Textfield
                    id="ws-url"
                    value={form.url}
                    testId="workspace-form-url"
                    onChange={(e) => setForm({ ...form, url: e.currentTarget.value })}
                  />
                </FormField>
                <FormField label="默认分支" htmlFor="ws-branch">
                  <Textfield
                    id="ws-branch"
                    value={form.default_branch}
                    testId="workspace-form-branch"
                    onChange={(e) =>
                      setForm({ ...form, default_branch: e.currentTarget.value })
                    }
                  />
                </FormField>
                <FormField label="描述" htmlFor="ws-desc">
                  <TextArea
                    id="ws-desc"
                    value={form.description_md}
                    testId="workspace-form-description"
                    onChange={(e) =>
                      setForm({ ...form, description_md: e.currentTarget.value })
                    }
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
