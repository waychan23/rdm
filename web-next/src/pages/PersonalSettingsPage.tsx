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
import SectionMessage from "@atlaskit/section-message";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import { beginLogin } from "../lib/oauth";
import type { OrgUser, Token } from "../types";
import "../styles/table.css";

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

const emptyHint = (
  <Text size="small" color="color.text.subtlest">
    暂无记录
  </Text>
);

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
    <Page testId="page-personal-settings">
      <PageHeader title="我的设置" testId="personal-settings-header" />

      <Box testId="personal-password-section">
        <Stack space="space.150" xcss={formStyles}>
          <Heading size="small">修改密码</Heading>
          <FormField label="原密码" htmlFor="old-pw">
            <Textfield
              id="old-pw"
              type="password"
              autoComplete="current-password"
              value={oldPw}
              testId="personal-old-password"
              onChange={(e) => setOldPw(e.currentTarget.value)}
            />
          </FormField>
          <FormField label="新密码（8–128 位）" htmlFor="new-pw">
            <Textfield
              id="new-pw"
              type="password"
              autoComplete="new-password"
              value={newPw}
              testId="personal-new-password"
              onChange={(e) => setNewPw(e.currentTarget.value)}
            />
          </FormField>
          <Inline>
            <Button
              appearance="primary"
              testId="personal-change-password"
              onClick={changePassword}
              isDisabled={!oldPw || !newPw}
            >
              修改密码
            </Button>
          </Inline>
          <Text size="small" color="color.text.subtlest">
            修改后浏览器会话需要重新登录；已签发的访问令牌（PAT）不受影响。
          </Text>
        </Stack>
      </Box>

      <Box testId="personal-tokens-section">
        <Stack space="space.200">
          <Inline spread="space-between" alignBlock="center">
            <Heading size="small">访问令牌（PAT）</Heading>
            <Button
              testId="personal-token-create-button"
              onClick={() => {
                setIssued("");
                setTokenOpen(true);
              }}
            >
              创建令牌
            </Button>
          </Inline>
          {(tokens ?? []).length === 0 ? (
            emptyHint
          ) : (
            <table className="rdm-table" aria-label="访问令牌" data-testid="personal-token-table">
              <thead>
                <tr>
                  <th scope="col" className="col-label">
                    标签
                  </th>
                  <th scope="col" className="col-label">
                    使用身份
                  </th>
                  <th scope="col" className="col-created">
                    创建
                  </th>
                  <th scope="col" className="col-expires">
                    过期
                  </th>
                  <th scope="col" className="col-active">
                    状态
                  </th>
                  <th scope="col" className="col-active">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {(tokens ?? []).map((t) => (
                  <tr key={t.id} data-testid={`personal-token-row-${t.id}`}>
                    <td className="cell-meta">{t.label ?? "—"}</td>
                    <td className="cell-meta">
                      {t.act_as_user_id
                        ? `agent ${agents?.find((a) => a.id === t.act_as_user_id)?.name ?? ""}`
                        : "本人"}
                    </td>
                    <td className="cell-meta">{t.created_at.slice(0, 10)}</td>
                    <td className="cell-meta">
                      {t.expires_at ? t.expires_at.slice(0, 10) : "永久"}
                    </td>
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
                          testId={`personal-token-revoke-${t.id}`}
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
          )}
        </Stack>
      </Box>

      <Box testId="personal-agents-section">
        <Stack space="space.200">
          <Inline spread="space-between" alignBlock="center">
            <Stack space="space.050">
              <Heading size="small">Agent 账号</Heading>
              <Text size="small" color="color.text.subtlest">
                你创建的 agent 会自动加入你所在的项目；成员管理中它们折叠在你名下。
              </Text>
            </Stack>
            <Button testId="personal-agent-create-button" onClick={() => setAgentOpen(true)}>
              创建 Agent
            </Button>
          </Inline>
          {(agents ?? []).length === 0 ? (
            emptyHint
          ) : (
            <table className="rdm-table" aria-label="Agent 账号" data-testid="personal-agent-table">
              <thead>
                <tr>
                  <th scope="col" className="col-person">
                    名称
                  </th>
                  <th scope="col">可接任务类型</th>
                  <th scope="col">Webhook</th>
                  <th scope="col" className="col-active">
                    状态
                  </th>
                  <th scope="col" className="col-date">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {(agents ?? []).map((a) => (
                  <tr key={a.id} data-testid={`personal-agent-row-${a.id}`}>
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
                        <Button
                          spacing="compact"
                          testId={`personal-agent-notify-${a.id}`}
                          onClick={() => setEditAgent(a)}
                        >
                          通知
                        </Button>
                        <Button
                          spacing="compact"
                          appearance={a.is_active ? "danger" : "default"}
                          testId={`personal-agent-toggle-${a.id}`}
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
          )}
        </Stack>
      </Box>

      <ModalTransition>
        {tokenOpen && (
          <ModalDialog
            onClose={() => setTokenOpen(false)}
            width="520px"
            label="创建访问令牌"
            testId="personal-token-dialog"
          >
            <ModalHeader>
              <ModalTitle>创建访问令牌</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label="标签" htmlFor="token-label">
                  <Textfield
                    id="token-label"
                    value={tokenLabel}
                    testId="personal-token-label"
                    onChange={(e) => setTokenLabel(e.currentTarget.value)}
                  />
                </FormField>
                <FormField label="有效期（天，留空=永久）" htmlFor="token-days">
                  <Textfield
                    id="token-days"
                    type="number"
                    value={tokenDays}
                    testId="personal-token-days"
                    onChange={(e) => setTokenDays(e.currentTarget.value)}
                  />
                </FormField>
                <FormField label="使用身份">
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
                </FormField>
                {issued && (
                  <SectionMessage appearance="success" title="令牌只显示一次">
                    <code>{issued}</code>
                  </SectionMessage>
                )}
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button
                appearance="subtle"
                testId="personal-token-dialog-close"
                onClick={() => setTokenOpen(false)}
              >
                关闭
              </Button>
              <Button
                appearance="primary"
                onClick={createToken}
                isLoading={savingToken}
                testId="personal-token-submit"
              >
                创建
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {agentOpen && (
          <ModalDialog
            onClose={() => setAgentOpen(false)}
            width="520px"
            label="创建 Agent"
            testId="personal-agent-dialog"
          >
            <ModalHeader>
              <ModalTitle>创建 Agent</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label="名称" htmlFor="agent-name">
                  <Textfield
                    id="agent-name"
                    value={agentForm.name}
                    testId="personal-agent-name"
                    onChange={(e) => setAgentForm({ ...agentForm, name: e.currentTarget.value })}
                  />
                </FormField>
                <FormField label="可接任务类型">
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
                </FormField>
                <FormField label="Webhook URL（可选）" htmlFor="agent-hook">
                  <Textfield
                    id="agent-hook"
                    value={agentForm.notify_webhook}
                    testId="personal-agent-hook"
                    onChange={(e) =>
                      setAgentForm({ ...agentForm, notify_webhook: e.currentTarget.value })
                    }
                  />
                </FormField>
                <FormField label="Webhook 格式">
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
                </FormField>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button
                appearance="subtle"
                testId="personal-agent-cancel"
                onClick={() => setAgentOpen(false)}
              >
                取消
              </Button>
              <Button
                appearance="primary"
                onClick={createAgent}
                isLoading={savingAgent}
                isDisabled={!agentForm.name.trim()}
                testId="personal-agent-submit"
              >
                创建
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {editAgent && (
          <ModalDialog
            onClose={() => setEditAgent(null)}
            label={`通知设置 · ${editAgent.name}`}
            testId="personal-agent-notify-dialog"
          >
            <ModalHeader>
              <ModalTitle>通知设置 · {editAgent.name}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label="Webhook URL" htmlFor="edit-hook">
                  <Textfield
                    id="edit-hook"
                    value={editHook}
                    testId="personal-agent-notify-hook"
                    onChange={(e) => setEditHook(e.currentTarget.value)}
                  />
                </FormField>
                <FormField label="格式">
                  <Select
                    inputId="edit-fmt"
                    options={WEBHOOK_FORMATS}
                    value={WEBHOOK_FORMATS.find((f) => f.value === editFmt)}
                    onChange={(opt) =>
                      setEditFmt((opt as { value: string } | null)?.value ?? "generic")
                    }
                  />
                </FormField>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button
                appearance="subtle"
                testId="personal-agent-notify-cancel"
                onClick={() => setEditAgent(null)}
              >
                取消
              </Button>
              <Button
                appearance="primary"
                testId="personal-agent-notify-save"
                onClick={saveAgent}
              >
                保存
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Page>
  );
}
