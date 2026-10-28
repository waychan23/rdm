import { useCallback, useState } from "react";
import { Link, useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import Drawer from "@atlaskit/drawer";
import Textfield from "@atlaskit/textfield";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives";
import { token } from "@atlaskit/tokens";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Sprint, SprintDetail } from "../types";
import StatusLozenge from "../workitems/status";
import SprintFormDialog, { type SprintFormValues } from "./sprints/SprintFormDialog";
import "../styles/table.css";

function sprintLozenge(status: string) {
  if (status === "ACTIVE") return <StatusLozenge status="IN_PROGRESS" />;
  if (status === "CLOSED") return <StatusLozenge status="DONE" />;
  return <StatusLozenge status="TODO" />;
}

export default function SprintsPage() {
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SprintDetail | null>(null);
  const [itemRef, setItemRef] = useState("");
  const [confirmClose, setConfirmClose] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadSprints = useCallback(
    async () => (await api.get<Sprint[]>(`/projects/${projectKey}/sprints`)).data,
    [projectKey],
  );
  const { data: sprints, loading, reload } = useAsync(loadSprints, [projectKey]);

  const openDetail = useCallback(async (id: string) => {
    setDetailId(id);
    const res = await api.get<SprintDetail>(`/sprints/${id}`);
    setDetail(res.data);
  }, []);

  const refreshDetail = useCallback(async () => {
    if (detailId) {
      const res = await api.get<SprintDetail>(`/sprints/${detailId}`);
      setDetail(res.data);
    }
  }, [detailId]);

  const create = async (v: SprintFormValues) => {
    try {
      await api.post(`/projects/${projectKey}/sprints`, v);
      setShowCreate(false);
      await reload();
    } catch (e) {
      notify.error("创建失败", errorCause(e)?.message);
    }
  };

  const saveEdit = async (v: SprintFormValues) => {
    if (!detail) return;
    try {
      await api.patch(`/sprints/${detail.id}`, v);
      setShowEdit(false);
      await Promise.all([refreshDetail(), reload()]);
      notify.success("已保存");
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    }
  };

  const addItem = async () => {
    if (!detail || !itemRef.trim() || busy) return;
    setBusy(true);
    try {
      await api.post(`/sprints/${detail.id}/items`, { items: [itemRef.trim()] });
      setItemRef("");
      await Promise.all([refreshDetail(), reload()]);
    } catch (e) {
      notify.error("加入失败", errorCause(e)?.message);
    } finally {
      setBusy(false);
    }
  };

  const removeItem = async (displayId: string) => {
    if (!detail) return;
    try {
      await api.del(`/sprints/${detail.id}/items/${encodeURIComponent(displayId)}`);
      await refreshDetail();
    } catch (e) {
      notify.error("移出失败", errorCause(e)?.message);
    }
  };

  const startSprint = async () => {
    if (!detail) return;
    try {
      await api.post(`/sprints/${detail.id}/start`, {});
      await Promise.all([refreshDetail(), reload()]);
    } catch (e) {
      notify.error("启动失败", errorCause(e)?.message);
    }
  };

  const doClose = async () => {
    if (!detail) return;
    setConfirmClose(false);
    try {
      await api.post(`/sprints/${detail.id}/close`, {});
      await Promise.all([refreshDetail(), reload()]);
    } catch (e) {
      notify.error("关闭失败", errorCause(e)?.message);
    }
  };

  return (
    <Box padding="space.300">
      <Inline spread="space-between" alignBlock="center">
        <Heading size="large">Sprint · {projectKey}</Heading>
        <Button appearance="primary" onClick={() => setShowCreate(true)}>
          新建 Sprint
        </Button>
      </Inline>

      {loading ? (
        <Box padding="space.400">
          <Spinner size="large" />
        </Box>
      ) : (
        <table className="rdm-table" style={{ marginTop: token("space.200") }}>
          <thead>
            <tr>
              <th>名称</th>
              <th style={{ width: 110 }}>状态</th>
              <th style={{ width: 120 }}>开始</th>
              <th style={{ width: 120 }}>结束</th>
            </tr>
          </thead>
          <tbody>
            {(sprints ?? []).map((s) => (
              <tr key={s.id} onClick={() => openDetail(s.id)}>
                <td>
                  <TextButtonLink>{s.name}</TextButtonLink>
                </td>
                <td>
                  <span onClick={(e) => e.stopPropagation()}>{sprintLozenge(s.status)}</span>
                </td>
                <td>
                  <span className="cell-meta">{s.start_date ?? "—"}</span>
                </td>
                <td>
                  <span className="cell-meta">{s.end_date ?? "—"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <SprintFormDialog
        open={showCreate}
        title="新建 Sprint"
        onClose={() => setShowCreate(false)}
        onSave={create}
      />
      <SprintFormDialog
        open={showEdit}
        title="编辑 Sprint"
        initial={
          detail
            ? {
                name: detail.name,
                goal_md: detail.goal_md ?? "",
                start_date: detail.start_date,
                end_date: detail.end_date,
              }
            : undefined
        }
        onClose={() => setShowEdit(false)}
        onSave={saveEdit}
      />

      <Drawer
        isOpen={detailId !== null}
        onClose={() => {
          setDetailId(null);
          setDetail(null);
        }}
        width="wide"
        label="Sprint 详情"
      >
        {detail && (
          <Stack space="space.200">
            <Inline space="space.150" alignBlock="center">
              {sprintLozenge(detail.status)}
              <Heading size="large">{detail.name}</Heading>
              {detail.status !== "CLOSED" && (
                <Button spacing="compact" onClick={() => setShowEdit(true)}>
                  编辑
                </Button>
              )}
            </Inline>
            {detail.goal_md && (
              <Text size="small" color="color.text.subtlest">
                {detail.goal_md}
              </Text>
            )}
            <Inline space="space.075" shouldWrap>
              {Object.entries(detail.status_counts).map(([s, n]) => (
                <StatusLozenge key={s} status={s}>
                  {`${s}: ${n}`}
                </StatusLozenge>
              ))}
            </Inline>

            <Text weight="semibold">工作项</Text>
            <table className="rdm-table">
              <thead>
                <tr>
                  <th style={{ width: 110 }}>ID</th>
                  <th>标题</th>
                  <th style={{ width: 120 }}>状态</th>
                  <th style={{ width: 70 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {detail.items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Link to={`/projects/${projectKey}/items/${row.display_id}`}>
                        {row.display_id}
                      </Link>
                    </td>
                    <td>{row.title}</td>
                    <td>
                      <StatusLozenge status={row.status} />
                    </td>
                    <td>
                      {detail.status !== "CLOSED" && (
                        <button
                          type="button"
                          style={{
                            background: "none",
                            border: "none",
                            color: token("color.text.danger"),
                            cursor: "pointer",
                            padding: 0,
                          }}
                          onClick={() => removeItem(row.display_id)}
                        >
                          移出
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {detail.status !== "CLOSED" && (
              <Stack space="space.150">
                <Inline space="space.100">
                  <Textfield
                    placeholder="工作项 display_id（如 DEMO-3），回车加入"
                    value={itemRef}
                    onChange={(e) => setItemRef(e.currentTarget.value)}
                    onKeyDown={(e) => e.key === "Enter" && void addItem()}
                  />
                  <Button isLoading={busy} onClick={() => void addItem()}>
                    加入
                  </Button>
                </Inline>
                <Inline space="space.100">
                  {detail.status === "PLANNED" && (
                    <Button appearance="primary" onClick={() => void startSprint()}>
                      启动
                    </Button>
                  )}
                  {detail.status === "ACTIVE" && (
                    <Button appearance="warning" onClick={() => setConfirmClose(true)}>
                      关闭
                    </Button>
                  )}
                </Inline>
              </Stack>
            )}
          </Stack>
        )}
      </Drawer>

      <ModalTransition>
        {confirmClose && (
          <ModalDialog onClose={() => setConfirmClose(false)} width="420px">
            <ModalHeader>
              <ModalTitle>关闭 Sprint</ModalTitle>
            </ModalHeader>
            <ModalBody>关闭后不能再加项；未终态项需先移出。确认关闭？</ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setConfirmClose(false)}>
                取消
              </Button>
              <Button appearance="primary" onClick={() => void doClose()}>
                确认关闭
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Box>
  );
}

function TextButtonLink({ children }: { children: React.ReactNode }) {
  return <span style={{ color: token("color.link"), cursor: "pointer" }}>{children}</span>;
}
