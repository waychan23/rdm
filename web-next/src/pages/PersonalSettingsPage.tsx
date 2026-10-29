import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
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
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import { beginLogin } from "../lib/oauth";
import type { OrgUser, Token } from "../types";
import "../styles/table.css";

const sectionStyles = xcss({ marginTop: "space.400" });
const formStyles = xcss({ maxWidth: "520px" });

const ACCEPT_KINDS = [
  { label: "story", value: "story" },
  { label: "issue", value: "issue" },
  { label: "task", value: "task" },
];
const WEBHOOK_FORMATS = [
  { label: "generic", value: "generic" },
  { label: "dingtalk", value: "dingtalk" },
  { label: "feishu", value: "feishu" },
];

export default function PersonalSettingsPage() {
  const notify = useNotify();
  const [nonce, setNonce] = useState(0);
  const reload = () => setNonce((n) => n + 1);

  const { data: tokens } = useAsync<Token[]>(
    async () => (await api.get<Token[]>("/me/tokens")).data,
    [nonce],
  );
  const { data: agents } = useAsync<OrgUser[]>(
    async () => (await api.get<OrgUser[]>("/me/agents")).data,
    [nonce],
  );

  // --- password ---
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const changePassword = async () => {
    try {
      await api.post("/auth/password", { old_password: oldPw, new_password: newPw });
      setOldPw("");
      setNewPw("");
      notify.success("密码已修改，请重新登录");
      await beginLogin("/settings");
    } catch (e) {
      notify.error("修改密码失败", errorCause(e)?.message);
    }
  };

  // --- token create ---
  const [tokenOpen, setTokenOpen] = useState(false);
  const [tokenLabel, setTokenLabel] = useState("web");
  const [tokenDays, setTokenDays] = useState("");
  const [actAs, setActAs] = useState<string | null>(null);
  const [issued, setIssued] = useState("");
  const [savingToken, setSavingToken] = useState(false);

  const createToken = async () => {
    if (savingToken) return;
    setSavingToken(true);
    try {
      const body: Record<string, unknown> = { label: tokenLabel };
      if (tokenDays.trim()) body.expires_in_days = Number(tokenDays);
      if (actAs) body.act_as_user_id = actAs;
      const res = await api.post<Token>("/me/tokens", body);
      setIssued(res.data.token ?? "");
      reload();
    } catch (e) {
      notify.error("签发失败", errorCause(e)?.message);
    } finally {
      setSavingToken(false);
    }
  };

  const revokeToken = async (id: string) => {
    try {
      await api.del(`/me/tokens/${id}`);
      reload();
    } catch (e) {
      notify.error("吊销失败", errorCause(e)?.message);
    }
  };

  // --- agents ---
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentForm, setAgentForm] = useState({
    name: "",
    accept_kinds: [] as string[],
    email: "",
    notify_webhook: "",
    notify_webhook_format: "generic",
  });
  const [savingAgent, setSavingAgent] = useState(false);

  const createAgent = async () => {
    if (savingAgent) return;
    setSavingAgent(true);
    try {
      const body = {
        name: agentForm.name.trim(),
        accept_kinds: agentForm.accept_kinds,
        email: agentForm.email || null,
        notify_webhook: agentForm.notify_webhook || null,
        notify_webhook_format: agentForm.notify_webhook_format,
      };
      await api.post("/me/agents", body);
      setAgentOpen(false);
      setAgentForm({
        name: "",
        accept_kinds: [],
        email: "",
        notify_webhook: "",
        notify_webhook_format: "generic",
      });
      reload();
    } catch (e) {
      notify.error("创建 agent 失败", errorCause(e)?.message);
    } finally {
      setSavingAgent(false);
    }
  };

  const toggleAgent = async (agent: OrgUser) => {
    try {
      await api.patch(`/me/agents/${agent.id}`, { is_active: !agent.is_active });
      reload();
    } catch (e) {
      notify.error("操作失败", errorCause(e)?.message);
    }
  };

  const [editAgent, setEditAgent] = useState<OrgUser | null>(null);
  const [editHook, setEditHook] = useState("");
  const [editFmt, setEditFmt] = useState("generic");

  useEffect(() => {
    if (editAgent) {
      setEditHook(editAgent.notify_webhook ?? "");
      setEditFmt(editAgent.notify_webhook_format ?? "generic");
    }
  }, [editAgent]);

  const saveAgent = async () => {
    if (!editAgent) return;
    try {
      await api.patch(`/me/agents/${editAgent.id}`, {
        notify_webhook: editHook || null,
        notify_webhook_format: editFmt,
      });
      setEditAgent(null);
      reload();
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    }
  };

  return (
    <Box padding="space.300">
      <Heading size="large">我的设置</Heading>

      <Box xcss={sectionStyles}>
        <Stack space="space.150" xcss={formStyles}>
          <Text weight="semibold">修改密码</Text>
          <Stack space="space.050">
            <label htmlFor="old-pw">原密码</label>
            <Textfield
              id="old-pw"
              type="password"
              autoComplete="current-password"
              value={oldPw}
              onChange={(e) => setOldPw(e.currentTarget.value)}
            />
          </Stack>
          <Stack space="space.050">
            <label htmlFor="new-pw">新密码（8–128 位）</label>
            <Textfield
              id="new-pw"
              type="password"
              autoComplete="new-password"
              value={newPw}
              onChange={(e) => setNewPw(e.currentTarget.value)}
            />
          </Stack>
          <Inline>
            <Button appearance="primary" onClick={changePassword} isDisabled={!oldPw || !newPw}>
              修改密码
            </Button>
          </Inline>
          <Text size="small" color="color.text.subtlest">
            修改后浏览器会话需要重新登录；已签发的访问令牌（PAT）不受影响。
          </Text>
        </Stack>
      </Box>

      <Box xcss={sectionStyles}>
        <Inline spread="space-between" alignBlock="center">
          <Text weight="semibold">访问令牌（PAT）</Text>
          <Button
            onClick={() => {
              setIssued("");
              setTokenOpen(true);
            }}
          >
            创建令牌
          </Button>
        </Inline>
        <table className="rdm-table" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th style={{ width: 150 }}>标签</th>
              <th style={{ width: 150 }}>使用身份</th>
              <th style={{ width: 120 }}>创建</th>
              <th style={{ width: 120 }}>过期</th>
              <th style={{ width: 90 }}>状态</th>
              <th style={{ width: 90 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {(tokens ?? []).map((t) => (
              <tr key={t.id} style={{ cursor: "default" }}>
                <td className="cell-meta">{t.label ?? "—"}</td>
                <td className="cell-meta">
                  {t.act_as_user_id
                    ? `agent ${agents?.find((a) => a.id === t.act_as_user_id)?.name ?? ""}`
                    : "本人"}
                </td>
                <td className="cell-meta">{t.created_at.slice(0, 10)}</td>
                <td className="cell-meta">{t.expires_at ? t.expires_at.slice(0, 10) : "永久"}</td>
                <td>
                  <Lozenge appearance={t.is_valid ? "success" : "default"}>
                    {t.is_valid ? "有效" : "已吊销"}
                  </Lozenge>
                </td>
                <td>
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
      </Box>

      <Box xcss={sectionStyles}>
        <Inline spread="space-between" alignBlock="center">
          <Stack space="space.050">
            <Text weight="semibold">Agent 账号</Text>
            <Text size="small" color="color.text.subtlest">
              你创建的 agent 会自动加入你所在的项目；成员管理中它们折叠在你名下。
            </Text>
          </Stack>
          <Button onClick={() => setAgentOpen(true)}>创建 Agent</Button>
        </Inline>
        <table className="rdm-table" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th style={{ width: 180 }}>名称</th>
              <th>可接任务类型</th>
              <th>Webhook</th>
              <th style={{ width: 90 }}>状态</th>
              <th style={{ width: 160 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {(agents ?? []).map((a) => (
              <tr key={a.id} style={{ cursor: "default" }}>
                <td>
                  <Inline space="space.100" alignBlock="center">
                    <Text>{a.name}</Text>
                    <Lozenge appearance="warning">agent</Lozenge>
                  </Inline>
                </td>
                <td className="cell-meta">{(a.accept_kinds ?? []).join(", ") || "—"}</td>
                <td className="cell-meta">{a.notify_webhook ?? "—"}</td>
                <td>
                  <Lozenge appearance={a.is_active ? "success" : "default"}>
                    {a.is_active ? "启用" : "停用"}
                  </Lozenge>
                </td>
                <td>
                  <Inline space="space.100">
                    <Button spacing="compact" onClick={() => setEditAgent(a)}>
                      通知
                    </Button>
                    <Button
                      spacing="compact"
                      appearance={a.is_active ? "danger" : "default"}
                      onClick={() => void toggleAgent(a)}
                    >
                      {a.is_active ? "停用" : "启用"}
                    </Button>
                  </Inline>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>

      <ModalTransition>
        {tokenOpen && (
          <ModalDialog
            onClose={() => setTokenOpen(false)}
            width="520px"
            label="创建访问令牌"
          >
            <ModalHeader>
              <ModalTitle>创建访问令牌</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Stack space="space.050">
                  <label htmlFor="token-label">标签</label>
                  <Textfield
                    id="token-label"
                    value={tokenLabel}
                    onChange={(e) => setTokenLabel(e.currentTarget.value)}
                  />
                </Stack>
                <Stack space="space.050">
                  <label htmlFor="token-days">有效期（天，留空=永久）</label>
                  <Textfield
                    id="token-days"
                    type="number"
                    value={tokenDays}
                    onChange={(e) => setTokenDays(e.currentTarget.value)}
                  />
                </Stack>
                <Stack space="space.050">
                  <Text size="small" weight="medium">
                    使用身份
                  </Text>
                  <Select
                    inputId="token-act-as"
                    placeholder="本人"
                    options={(agents ?? []).map((a) => ({
                      label: `${a.name}（agent）`,
                      value: a.id,
                    }))}
                    value={
                      actAs
                        ? {
                            label: agents?.find((a) => a.id === actAs)?.name ?? "",
                            value: actAs,
                          }
                        : null
                    }
                    onChange={(opt) =>
                      setActAs((opt as { value: string } | null)?.value ?? null)
                    }
                    isClearable
                  />
                </Stack>
                {issued && (
                  <SectionMessage appearance="success" title="令牌只显示一次">
                    <code>{issued}</code>
                  </SectionMessage>
                )}
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setTokenOpen(false)}>
                关闭
              </Button>
              <Button appearance="primary" onClick={createToken} isLoading={savingToken}>
                创建
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {agentOpen && (
          <ModalDialog onClose={() => setAgentOpen(false)} width="520px" label="创建 Agent">
            <ModalHeader>
              <ModalTitle>创建 Agent</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Stack space="space.050">
                  <label htmlFor="agent-name">名称</label>
                  <Textfield
                    id="agent-name"
                    value={agentForm.name}
                    onChange={(e) => setAgentForm({ ...agentForm, name: e.currentTarget.value })}
                  />
                </Stack>
                <Stack space="space.050">
                  <Text size="small" weight="medium">
                    可接任务类型
                  </Text>
                  <Select
                    inputId="agent-kinds"
                    isMulti
                    options={ACCEPT_KINDS}
                    value={ACCEPT_KINDS.filter((k) => agentForm.accept_kinds.includes(k.value))}
                    onChange={(opts) =>
                      setAgentForm({
                        ...agentForm,
                        accept_kinds: (opts as readonly { value: string }[]).map((o) => o.value),
                      })
                    }
                  />
                </Stack>
                <Stack space="space.050">
                  <label htmlFor="agent-hook">Webhook URL（可选）</label>
                  <Textfield
                    id="agent-hook"
                    value={agentForm.notify_webhook}
                    onChange={(e) =>
                      setAgentForm({ ...agentForm, notify_webhook: e.currentTarget.value })
                    }
                  />
                </Stack>
                <Stack space="space.050">
                  <Text size="small" weight="medium">
                    Webhook 格式
                  </Text>
                  <Select
                    inputId="agent-fmt"
                    options={WEBHOOK_FORMATS}
                    value={WEBHOOK_FORMATS.find((f) => f.value === agentForm.notify_webhook_format)}
                    onChange={(opt) =>
                      setAgentForm({
                        ...agentForm,
                        notify_webhook_format:
                          (opt as { value: string } | null)?.value ?? "generic",
                      })
                    }
                  />
                </Stack>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setAgentOpen(false)}>
                取消
              </Button>
              <Button
                appearance="primary"
                onClick={createAgent}
                isLoading={savingAgent}
                isDisabled={!agentForm.name.trim()}
              >
                创建
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {editAgent && (
          <ModalDialog onClose={() => setEditAgent(null)} label={`通知设置 · ${editAgent.name}`}>
            <ModalHeader>
              <ModalTitle>通知设置 · {editAgent.name}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Stack space="space.050">
                  <label htmlFor="edit-hook">Webhook URL</label>
                  <Textfield
                    id="edit-hook"
                    value={editHook}
                    onChange={(e) => setEditHook(e.currentTarget.value)}
                  />
                </Stack>
                <Stack space="space.050">
                  <Text size="small" weight="medium">
                    格式
                  </Text>
                  <Select
                    inputId="edit-fmt"
                    options={WEBHOOK_FORMATS}
                    value={WEBHOOK_FORMATS.find((f) => f.value === editFmt)}
                    onChange={(opt) =>
                      setEditFmt((opt as { value: string } | null)?.value ?? "generic")
                    }
                  />
                </Stack>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setEditAgent(null)}>
                取消
              </Button>
              <Button appearance="primary" onClick={saveAgent}>
                保存
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Box>
  );
}
