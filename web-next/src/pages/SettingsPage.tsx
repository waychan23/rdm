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
import Spinner from "@atlaskit/spinner";
import Lozenge from "@atlaskit/lozenge";
import SectionMessage from "@atlaskit/section-message";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";
import { token } from "@atlaskit/tokens";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Member, Project, Token } from "../types";
import { MemberEditDialog } from "../members/memberForms";
import "../styles/table.css";

const infoBlock = xcss({
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
  padding: "space.200",
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: "space.200",
});

const nameCellStyles = xcss({
  gridColumn: "1 / -1",
});

export default function SettingsPage() {
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();

  const [nonce, setNonce] = useState(0);
  const [editMember, setEditMember] = useState<Member | null>(null);
  const [tokenMember, setTokenMember] = useState<Member | null>(null);
  const [tokens, setTokens] = useState<Token[]>([]);
  const [issuedToken, setIssuedToken] = useState("");

  const { data, loading } = useAsync<{ project: Project; members: Member[] }>(
    async () => {
      const [p, m] = await Promise.all([
        api.get<Project>(`/projects/${projectKey}`),
        api.get<Member[]>(`/projects/${projectKey}/members`),
      ]);
      return { project: p.data, members: m.data };
    },
    [projectKey, nonce],
  );

  const reload = () => setNonce((n) => n + 1);

  const saveMember = async (id: string, payload: Record<string, unknown>) => {
    try {
      await api.patch(`/members/${id}`, payload);
      setEditMember(null);
      reload();
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    }
  };

  const openTokens = async (m: Member) => {
    setTokenMember(m);
    setIssuedToken("");
    const res = await api.get<Token[]>(`/members/${m.id}/tokens`);
    setTokens(res.data);
  };

  const issueToken = async () => {
    if (!tokenMember) return;
    const res = await api.post<{ token: string }>(
      `/members/${tokenMember.id}/tokens`,
      { label: "web" },
    );
    setIssuedToken(res.data.token);
    const fresh = await api.get<Token[]>(`/members/${tokenMember.id}/tokens`);
    setTokens(fresh.data);
  };

  const revokeToken = async (id: string) => {
    if (!tokenMember) return;
    await api.del(`/tokens/${id}`);
    const fresh = await api.get<Token[]>(`/members/${tokenMember.id}/tokens`);
    setTokens(fresh.data);
  };

  if (loading || !data) {
    return (
      <Box padding="space.400">
        <Spinner size="large" />
      </Box>
    );
  }

  return (
    <Box padding="space.300">
      <Heading size="large">设置 · {projectKey}</Heading>

      <Box xcss={infoBlock} style={{ marginTop: 16, marginBottom: 16 }}>
        <Stack space="space.050">
          <Text size="small" color="color.text.subtlest">
            项目 ID
          </Text>
          <Text>{data.project.id}</Text>
        </Stack>
        <Stack space="space.050">
          <Text size="small" color="color.text.subtlest">
            状态
          </Text>
          <Lozenge appearance={data.project.status === "archived" ? "default" : "success"}>
            {data.project.status}
          </Lozenge>
        </Stack>
        <Stack space="space.050" xcss={nameCellStyles}>
          <Text size="small" color="color.text.subtlest">
            名称
          </Text>
          <Text>{data.project.name}</Text>
        </Stack>
      </Box>

      <Text weight="semibold">成员与通知</Text>
      <table className="rdm-table" style={{ marginTop: 8 }}>
        <thead>
          <tr>
            <th style={{ width: 130 }}>名称</th>
            <th style={{ width: 80 }}>类型</th>
            <th style={{ width: 200 }}>角色</th>
            <th>Webhook</th>
            <th style={{ width: 70 }}>活跃</th>
            <th style={{ width: 150 }}>操作</th>
          </tr>
        </thead>
        <tbody>
          {data.members.map((m) => (
            <tr key={m.id} style={{ cursor: "default" }}>
              <td>{m.name}</td>
              <td>
                <Lozenge appearance={m.type === "agent" ? "warning" : "default"}>{m.type}</Lozenge>
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
                  <Button spacing="compact" onClick={() => void openTokens(m)}>
                    Token
                  </Button>
                </Inline>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <MemberEditDialog
        open={editMember !== null}
        member={editMember}
        onClose={() => setEditMember(null)}
        onSave={saveMember}
      />

      <ModalTransition>
        {tokenMember && (
          <ModalDialog
            onClose={() => setTokenMember(null)}
            width="560px"
            label={`Token · ${tokenMember.name}`}
          >
            <ModalHeader>
              <ModalTitle>Token · {tokenMember.name}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Button appearance="primary" onClick={() => void issueToken()}>
                  签发新 Token
                </Button>
                {issuedToken && (
                  <SectionMessage appearance="success">
                    新 Token（只显示一次）：<code>{issuedToken}</code>
                  </SectionMessage>
                )}
                <table className="rdm-table">
                  <thead>
                    <tr>
                      <th style={{ width: 120 }}>标签</th>
                      <th>创建</th>
                      <th style={{ width: 90 }}>状态</th>
                      <th style={{ width: 80 }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tokens.map((t) => (
                      <tr key={t.id} style={{ cursor: "default" }}>
                        <td className="cell-meta">{t.label ?? "—"}</td>
                        <td className="cell-meta">{t.created_at.slice(0, 10)}</td>
                        <td>
                          <Lozenge appearance={t.is_valid ? "success" : "default"}>
                            {t.is_valid ? "有效" : "已吊销"}
                          </Lozenge>
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          {t.is_valid && (
                            <Button
                              spacing="compact"
                              appearance="danger"
                              onClick={() => void revokeToken(t.id)}
                            >
                              吊销
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setTokenMember(null)}>
                关闭
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Box>
  );
}
