import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Text } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { OrgUser, ProjectMemberRow } from "../types";
import { AddMemberDialog, MemberEditDialog } from "../members/memberForms";
import "../styles/table.css";

function AgentRow({ agent }: { agent: NonNullable<ProjectMemberRow["agents"]>[number] }) {
  return (
    <tr className="rdm-table-child" style={{ cursor: "default" }}>
      <td>
        <Inline space="space.100" alignBlock="center">
          <span className="rdm-indent" aria-hidden>
            ↳
          </span>
          <Text size="small">{agent.user.name}</Text>
          <Lozenge appearance="default">自动</Lozenge>
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
          {agent.user.effective_active ? "是" : "否"}
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
  const [nonce, setNonce] = useState(0);

  const { data: members, loading } = useAsync<ProjectMemberRow[]>(
    async () => (await api.get<ProjectMemberRow[]>(`/projects/${projectKey}/members`)).data,
    [projectKey, nonce],
  );
  const { data: orgUsers } = useAsync<OrgUser[]>(
    async () => (await api.get<OrgUser[]>("/users?type=human")).data,
    [projectKey, nonce],
  );

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
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    }
  };

  const remove = async (member: ProjectMemberRow) => {
    const extra =
      member.agents && member.agents.length > 0
        ? `其 ${member.agents.length} 个 agent 也会随同移出项目。`
        : "";
    if (!window.confirm(`确定把 ${member.name} 移出项目？${extra}`)) return;
    try {
      await api.del(`/projects/${projectKey}/members/${member.id}`);
      reload();
    } catch (e) {
      notify.error("移除失败", errorCause(e)?.message);
    }
  };

  return (
    <Box padding="space.300">
      <Inline spread="space-between" alignBlock="center">
        <Heading size="large">成员 · {projectKey}</Heading>
        <Button appearance="primary" onClick={() => setShowAdd(true)}>
          添加成员
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
              <th style={{ width: 220 }}>名称</th>
              <th style={{ width: 90 }}>类型</th>
              <th>项目角色</th>
              <th>Webhook</th>
              <th style={{ width: 70 }}>活跃</th>
              <th style={{ width: 160 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {(members ?? []).map((m) => (
              <MemberGroup
                key={m.id}
                member={m}
                onEdit={() => setEditMember(m)}
                onRemove={() => remove(m)}
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
        onClose={() => setEditMember(null)}
        onSave={saveRoles}
      />
    </Box>
  );
}

function MemberGroup({
  member,
  onEdit,
  onRemove,
}: {
  member: ProjectMemberRow;
  onEdit: () => void;
  onRemove: () => void;
}) {
  return (
    <>
      <tr style={{ cursor: "default" }}>
        <td>
          <Inline space="space.100" alignBlock="center">
            <Text weight="medium">{member.name}</Text>
            {member.id && member.roles.includes("project_owner") && (
              <Lozenge appearance="inprogress">Owner</Lozenge>
            )}
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
                <Lozenge key={r} appearance="new">
                  {r}
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
            {member.is_active ? "是" : "否"}
          </Lozenge>
        </td>
        <td onClick={(e) => e.stopPropagation()}>
          <Inline space="space.100">
            <Button spacing="compact" onClick={onEdit}>
              角色
            </Button>
            <Button spacing="compact" appearance="subtle" onClick={onRemove}>
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
