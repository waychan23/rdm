import { useState } from "react";
import { useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import Lozenge from "@atlaskit/lozenge";
import { Box, Inline, Text } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Member } from "../types";
import {
  CreateMemberDialog,
  MemberEditDialog,
  ResetPasswordDialog,
} from "../members/memberForms";
import "../styles/table.css";

export default function MembersPage() {
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();

  const [showCreate, setShowCreate] = useState(false);
  const [editMember, setEditMember] = useState<Member | null>(null);
  const [resetMember, setResetMember] = useState<Member | null>(null);
  const [nonce, setNonce] = useState(0);

  const { data: members, loading } = useAsync<Member[]>(
    async () => (await api.get<Member[]>(`/projects/${projectKey}/members`)).data,
    [projectKey, nonce],
  );

  const reload = () => setNonce((n) => n + 1);

  const create = async (payload: Record<string, unknown>) => {
    try {
      await api.post(`/projects/${projectKey}/members`, payload);
      setShowCreate(false);
      reload();
    } catch (e) {
      notify.error("创建失败", errorCause(e)?.message);
    }
  };

  const saveEdit = async (id: string, payload: Record<string, unknown>) => {
    try {
      await api.patch(`/members/${id}`, payload);
      setEditMember(null);
      reload();
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    }
  };

  const resetPassword = async (password: string | null) => {
    if (!resetMember) return "";
    const res = await api.post<{ password: string }>(
      `/members/${resetMember.id}/password`,
      { password },
    );
    try {
      await navigator.clipboard.writeText(res.data.password);
    } catch {
      // clipboard may be unavailable; the plaintext is still shown in the dialog
    }
    notify.success("已重置，新密码已复制");
    reload();
    return res.data.password;
  };

  return (
    <Box padding="space.300">
      <Inline spread="space-between" alignBlock="center">
        <Heading size="large">成员 · {projectKey}</Heading>
        <Button appearance="primary" onClick={() => setShowCreate(true)}>
          新增成员
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
              <th style={{ width: 140 }}>名称</th>
              <th style={{ width: 90 }}>类型</th>
              <th>角色</th>
              <th>Webhook</th>
              <th style={{ width: 70 }}>活跃</th>
              <th style={{ width: 170 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {(members ?? []).map((m) => (
              <tr key={m.id} style={{ cursor: "default" }}>
                <td>{m.name}</td>
                <td>
                  <Lozenge appearance={m.type === "agent" ? "warning" : "default"}>
                    {m.type}
                  </Lozenge>
                </td>
                <td>
                  <Inline space="space.050">
                    {m.roles.map((r) => (
                      <Lozenge key={r} appearance="new">
                        {r}
                      </Lozenge>
                    ))}
                  </Inline>
                </td>
                <td>
                  <Text size="small" color="color.text.subtlest">
                    {m.notify_webhook ?? "—"}
                    {m.notify_webhook ? ` ${m.notify_webhook_format}` : ""}
                  </Text>
                </td>
                <td>
                  <Lozenge appearance={m.is_active ? "success" : "default"}>
                    {m.is_active ? "是" : "否"}
                  </Lozenge>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <Inline space="space.100">
                    <Button spacing="compact" onClick={() => setEditMember(m)}>
                      编辑
                    </Button>
                    {m.type === "human" && (
                      <Button spacing="compact" onClick={() => setResetMember(m)}>
                        重置密码
                      </Button>
                    )}
                  </Inline>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <CreateMemberDialog
        open={showCreate}
        humans={(members ?? []).filter((m) => m.type === "human")}
        onClose={() => setShowCreate(false)}
        onCreate={create}
      />
      <MemberEditDialog
        open={editMember !== null}
        member={editMember}
        onClose={() => setEditMember(null)}
        onSave={saveEdit}
      />
      <ResetPasswordDialog
        open={resetMember !== null}
        memberName={resetMember?.name ?? ""}
        onClose={() => setResetMember(null)}
        onReset={resetPassword}
      />
    </Box>
  );
}
