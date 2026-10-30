import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import EmptyState from "@atlaskit/empty-state";
import Lozenge from "@atlaskit/lozenge";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Text } from "@atlaskit/primitives/compiled";

import ConfirmDialog from "../components/ConfirmDialog";
import ErrorState from "../components/ErrorState";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { roleLabel } from "../lib/labels";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { OrgUser, Project, ProjectMemberRow } from "../types";
import { AddMemberDialog, MemberEditDialog } from "../members/memberForms";
import "../styles/table.css";

const styles = cssMap({
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
});

function AgentRow({ agent }: { agent: NonNullable<ProjectMemberRow["agents"]>[number] }) {
  return (
    <tr className="rdm-table-child" data-testid={`member-agent-row-${agent.user.id}`}>
      <td>
        <Inline space="space.100" alignBlock="center">
          <span className="rdm-indent" aria-hidden>
            ↳
          </span>
          <Text size="small">{agent.user.name}</Text>
          <Lozenge appearance="default">自动</Lozenge>
          {!agent.user.effective_active && (
            <Lozenge appearance="default">已停用</Lozenge>
          )}
        </Inline>
      </td>
      <td>
        <Lozenge appearance="warning">{agent.user.type}</Lozenge>
      </td>
      <td>
        <Text size="small" color="color.text.subtlest">
          继承其 human 的项目权限
        </Text>
      </td>
      <td>
        <Text size="small" color="color.text.subtlest">
          {agent.user.notify_webhook ?? "—"}
        </Text>
      </td>
      <td>
        <Lozenge appearance={agent.user.effective_active ? "success" : "default"}>
          {agent.user.effective_active ? "启用" : "停用"}
        </Lozenge>
      </td>
      <td />
    </tr>
  );
}

export default function MembersPage() {
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();

  const [showAdd, setShowAdd] = useState(false);
  const [editMember, setEditMember] = useState<ProjectMemberRow | null>(null);
  const [removeTarget, setRemoveTarget] = useState<ProjectMemberRow | null>(null);
  const [nonce, setNonce] = useState(0);

  const { data: members, loading, error, reload: reloadAsync } = useAsync<ProjectMemberRow[]>(
    async () => (await api.get<ProjectMemberRow[]>(`/projects/${projectKey}/members`)).data,
    [projectKey, nonce],
  );
  const { data: orgUsers } = useAsync<OrgUser[]>(
    async () => (await api.get<OrgUser[]>("/users?type=human")).data,
    [projectKey, nonce],
  );
  // project.owner_user_id is the single source of truth for the 项目经理 badge.
  const { data: project } = useAsync<Project>(
    async () => (await api.get<Project>(`/projects/${projectKey}`)).data,
    [projectKey, nonce],
  );
  const ownerUserId = project?.owner_user_id ?? null;

  const reload = () => setNonce((n) => n + 1);

  const candidates = useMemo(() => {
    const memberIds = new Set((members ?? []).map((m) => m.id));
    return (orgUsers ?? []).filter((u) => !memberIds.has(u.id));
  }, [members, orgUsers]);

  const add = async (userId: string, roles: string[]) => {
    try {
      await api.post(`/projects/${projectKey}/members`, { user_id: userId, roles });
      setShowAdd(false);
      reload();
    } catch (e) {
      notify.error("添加失败", errorCause(e)?.message);
    }
  };

  const saveRoles = async (userId: string, roles: string[]) => {
    try {
      await api.patch(`/projects/${projectKey}/members/${userId}`, { roles });
      setEditMember(null);
      reload();
      notify.success("保存成功");
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    }
  };

  const remove = async () => {
    if (!removeTarget) return;
    try {
      await api.del(`/projects/${projectKey}/members/${removeTarget.id}`);
      setRemoveTarget(null);
      reload();
    } catch (e) {
      notify.error("移除失败", errorCause(e)?.message);
    }
  };

  const removeExtra =
    removeTarget?.agents && removeTarget.agents.length > 0
      ? `其 ${removeTarget.agents.length} 个 agent 也会随同移出项目。`
      : "";

  return (
    <Page testId="page-members">
      <PageHeader
        title={`成员 · ${projectKey}`}
        testId="members-header"
        actions={
          <Button appearance="primary" testId="member-add-button" onClick={() => setShowAdd(true)}>
            添加成员
          </Button>
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={reloadAsync} testId="members-error" />
      ) : loading ? (
        <Box xcss={styles.centered} testId="members-loading">
          <Spinner size="large" />
        </Box>
      ) : (members ?? []).length === 0 ? (
        <Box testId="members-empty">
          <EmptyState
            header="项目还没有成员"
            description="点击右上角「添加成员」把组织内的用户加入项目。"
          />
        </Box>
      ) : (
        <table className="rdm-table" aria-label="项目成员" data-testid="member-table">
          <thead>
            <tr>
              <th scope="col" className="col-name">
                名称
              </th>
              <th scope="col" className="col-type">
                类型
              </th>
              <th scope="col">项目角色</th>
              <th scope="col">Webhook</th>
              <th scope="col" className="col-active">
                活跃
              </th>
              <th scope="col" className="col-actions">
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            {(members ?? []).map((m) => (
              <MemberGroup
                key={m.id}
                member={m}
                isOwner={m.id === ownerUserId}
                onEdit={() => setEditMember(m)}
                onRemove={() => setRemoveTarget(m)}
              />
            ))}
          </tbody>
        </table>
      )}

      <AddMemberDialog
        open={showAdd}
        candidates={candidates}
        onClose={() => setShowAdd(false)}
        onAdd={add}
      />
      <MemberEditDialog
        open={editMember !== null}
        member={editMember}
        ownerUserId={ownerUserId}
        onClose={() => setEditMember(null)}
        onSave={saveRoles}
      />
      <ConfirmDialog
        open={removeTarget !== null}
        title="移出项目"
        danger
        confirmLabel="移出"
        testId="member-remove-dialog"
        onClose={() => setRemoveTarget(null)}
        onConfirm={() => void remove()}
      >
        确定把 {removeTarget?.name} 移出项目？{removeExtra}
      </ConfirmDialog>
    </Page>
  );
}

function MemberGroup({
  member,
  isOwner,
  onEdit,
  onRemove,
}: {
  member: ProjectMemberRow;
  isOwner: boolean;
  onEdit: () => void;
  onRemove: () => void;
}) {
  return (
    <>
      <tr data-testid={`member-row-${member.id}`}>
        <td>
          <Inline space="space.100" alignBlock="center">
            <Text weight="medium">{member.name}</Text>
            {isOwner && <Lozenge appearance="inprogress">项目经理</Lozenge>}
            {!member.is_active && <Lozenge appearance="default">已停用</Lozenge>}
          </Inline>
        </td>
        <td>
          <Lozenge appearance="default">{member.type}</Lozenge>
        </td>
        <td>
          <Inline space="space.050">
            {member.roles.length === 0 ? (
              <Text size="small" color="color.text.subtlest">
                —
              </Text>
            ) : (
              member.roles.map((r) => (
                <Lozenge key={r} appearance={r === "project_owner" ? "inprogress" : "new"}>
                  {roleLabel(r)}
                </Lozenge>
              ))
            )}
          </Inline>
        </td>
        <td>
          <Text size="small" color="color.text.subtlest">
            {member.notify_webhook ?? "—"}
            {member.notify_webhook ? ` ${member.notify_webhook_format}` : ""}
          </Text>
        </td>
        <td>
          <Lozenge appearance={member.is_active ? "success" : "default"}>
            {member.is_active ? "启用" : "停用"}
          </Lozenge>
        </td>
        <td>
          <Inline space="space.100">
            <Button spacing="compact" testId={`member-edit-${member.id}`} onClick={onEdit}>
              角色
            </Button>
            <Button
              spacing="compact"
              appearance="danger"
              testId={`member-remove-${member.id}`}
              onClick={onRemove}
            >
              移出
            </Button>
          </Inline>
        </td>
      </tr>
      {(member.agents ?? []).map((agent) => (
        <AgentRow key={agent.user.id} agent={agent} />
      ))}
    </>
  );
}
