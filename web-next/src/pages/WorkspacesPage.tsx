import { useState } from "react";
import { useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Textfield from "@atlaskit/textfield";
import TextArea from "@atlaskit/textarea";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Workspace } from "../types";
import "../styles/table.css";

const KINDS = ["git_repo", "doc_repo", "design", "other"];
const KIND_OPTIONS = KINDS.map((v) => ({ label: v, value: v }));

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
    <Box padding="space.300">
      <Inline spread="space-between" alignBlock="center">
        <Heading size="large">工作区 · {projectKey}</Heading>
        <Button appearance="primary" onClick={openCreate}>
          登记工作区
        </Button>
      </Inline>

      {loading ? (
        <Box padding="space.400">
          <Spinner size="large" />
        </Box>
      ) : (
        <table className="rdm-table" style={{ marginTop: 16 }}>
          <thead>
            <tr>
              <th>名称</th>
              <th style={{ width: 120 }}>类型</th>
              <th>URL</th>
              <th style={{ width: 110 }}>默认分支</th>
              <th style={{ width: 150 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {(workspaces ?? []).map((w) => (
              <tr key={w.id} style={{ cursor: "default" }}>
                <td>{w.name}</td>
                <td className="cell-meta">{w.kind}</td>
                <td>
                  <a href={w.url} target="_blank" rel="noreferrer">
                    {w.url}
                  </a>
                </td>
                <td className="cell-meta">{w.default_branch ?? "—"}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <Inline space="space.100">
                    <Button spacing="compact" onClick={() => openEdit(w)}>
                      编辑
                    </Button>
                    <Button spacing="compact" appearance="danger" onClick={() => setConfirmId(w.id)}>
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
          <ModalDialog onClose={() => setDialogOpen(false)} width="460px">
            <ModalHeader>
              <ModalTitle>{form.id ? "编辑工作区" : "登记工作区"}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Stack space="space.050">
                  <label htmlFor="ws-name">名称</label>
                  <Textfield
                    id="ws-name"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
                  />
                </Stack>
                <Stack space="space.050">
                  <label>类型</label>
                  <Select
                    options={KIND_OPTIONS}
                    value={form.kind}
                    onChange={(o) => o && setForm({ ...form, kind: o as Option })}
                  />
                </Stack>
                <Stack space="space.050">
                  <label htmlFor="ws-url">URL</label>
                  <Textfield
                    id="ws-url"
                    value={form.url}
                    onChange={(e) => setForm({ ...form, url: e.currentTarget.value })}
                  />
                </Stack>
                <Stack space="space.050">
                  <label htmlFor="ws-branch">默认分支</label>
                  <Textfield
                    id="ws-branch"
                    value={form.default_branch}
                    onChange={(e) =>
                      setForm({ ...form, default_branch: e.currentTarget.value })
                    }
                  />
                </Stack>
                <Stack space="space.050">
                  <label htmlFor="ws-desc">描述</label>
                  <TextArea
                    id="ws-desc"
                    value={form.description_md}
                    onChange={(e) =>
                      setForm({ ...form, description_md: e.currentTarget.value })
                    }
                  />
                </Stack>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setDialogOpen(false)}>
                取消
              </Button>
              <Button appearance="primary" isLoading={saving} onClick={() => void save()}>
                保存
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {confirmId && (
          <ModalDialog onClose={() => setConfirmId(null)} width="420px">
            <ModalHeader>
              <ModalTitle>确认删除</ModalTitle>
            </ModalHeader>
            <ModalBody>删除该工作区？软删可恢复。</ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setConfirmId(null)}>
                取消
              </Button>
              <Button appearance="danger" onClick={() => void remove()}>
                删除
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Box>
  );
}
