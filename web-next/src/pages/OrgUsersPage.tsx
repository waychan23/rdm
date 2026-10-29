import { useMemo, useState } from "react";

import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
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
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useCurrentUser } from "../lib/auth";
import { useNotify } from "../lib/flags";
import type { OrgUser } from "../types";
import "../styles/table.css";

const ASSIGNABLE_ROLES = ["user_manager", "project_director"];

export default function OrgUsersPage() {
  const notify = useNotify();
  const me = useCurrentUser();
  const isOwner = !!me?.org_roles.includes("org_owner");
  const [nonce, setNonce] = useState(0);
  const reload = () => setNonce((n) => n + 1);

  const { data: users, loading } = useAsync<OrgUser[]>(
    async () => (await api.get<OrgUser[]>("/users")).data,
    [nonce],
  );

  const { humans, agentsByManager } = useMemo(() => {
    const humans: OrgUser[] = [];
    const agentsByManager = new Map<string, OrgUser[]>();
    for (const u of users ?? []) {
      if (u.type === "agent") {
        const list = agentsByManager.get(u.manager_user_id ?? "") ?? [];
        list.push(u);
        agentsByManager.set(u.manager_user_id ?? "", list);
      } else {
        humans.push(u);
      }
    }
    return { humans, agentsByManager };
  }, [users]);

  // --- create human ---
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [createdUrl, setCreatedUrl] = useState("");

  const createHuman = async () => {
    try {
      const res = await api.post<{ user: OrgUser; password_reset_url: string }>("/users", {
        name: name.trim(),
        email: email || null,
      });
      setCreatedUrl(res.data.password_reset_url);
      setName("");
      setEmail("");
      reload();
    } catch (e) {
      notify.error("创建失败", errorCause(e)?.message);
    }
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      notify.success("链接已复制");
    } catch {
      // clipboard may be unavailable; the link stays visible in the dialog
    }
  };

  // --- reset link ---
  const [resetUrl, setResetUrl] = useState("");
  const resetPassword = async (user: OrgUser) => {
    try {
      const res = await api.post<{ password_reset_url: string }>(
        `/users/${user.id}/password-reset-token`,
      );
      setResetUrl(res.data.password_reset_url);
      void copy(res.data.password_reset_url);
    } catch (e) {
      notify.error("生成链接失败", errorCause(e)?.message);
    }
  };

  const setActive = async (user: OrgUser, active: boolean) => {
    try {
      await api.post(`/users/${user.id}/${active ? "enable" : "disable"}`);
      reload();
    } catch (e) {
      notify.error("操作失败", errorCause(e)?.message);
    }
  };

  const revokeAll = async (user: OrgUser) => {
    if (!window.confirm(`撤销 ${user.name} 及其 agent 的全部访问令牌？`)) return;
    try {
      await api.post(`/users/${user.id}/tokens/revoke-all`);
      notify.success("令牌已撤销");
    } catch (e) {
      notify.error("撤销失败", errorCause(e)?.message);
    }
  };

  const [rolesTarget, setRolesTarget] = useState<OrgUser | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const openRoles = (user: OrgUser) => {
    setRolesTarget(user);
    setRoles(user.org_roles.filter((r) => ASSIGNABLE_ROLES.includes(r)));
  };
  const saveRoles = async () => {
    if (!rolesTarget) return;
    try {
      await api.put(`/users/${rolesTarget.id}/org-roles`, { roles });
      setRolesTarget(null);
      reload();
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    }
  };

  const transferOwner = async (user: OrgUser) => {
    if (!window.confirm(`把 Org Owner 转让给 ${user.name}？你将失去超级管理员权限。`)) return;
    try {
      await api.post("/org/transfer-owner", { user_id: user.id });
      notify.success("已转让 Org Owner");
      reload();
    } catch (e) {
      notify.error("转让失败", errorCause(e)?.message);
    }
  };

  return (
    <Box padding="space.300">
      <Inline spread="space-between" alignBlock="center">
        <Heading size="large">组织用户</Heading>
        <Button appearance="primary" onClick={() => setCreateOpen(true)}>
          创建用户
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
              <th>组织角色</th>
              <th>Email</th>
              <th style={{ width: 90 }}>状态</th>
              <th style={{ width: 340 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {humans.map((h) => (
              <HumanGroup
                key={h.id}
                human={h}
                agents={agentsByManager.get(h.id) ?? []}
                isOwner={isOwner}
                onReset={() => void resetPassword(h)}
                onToggle={() => void setActive(h, !h.is_active)}
                onRevoke={() => void revokeAll(h)}
                onRoles={() => openRoles(h)}
                onTransferOwner={() => void transferOwner(h)}
              />
            ))}
          </tbody>
        </table>
      )}

      <ModalTransition>
        {createOpen && (
          <ModalDialog onClose={() => setCreateOpen(false)} width="520px" label="创建用户">
            <ModalHeader>
              <ModalTitle>创建人类用户</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Stack space="space.050">
                  <label htmlFor="new-user-name">用户名（登录名，组织内唯一）</label>
                  <Textfield
                    id="new-user-name"
                    value={name}
                    onChange={(e) => setName(e.currentTarget.value)}
                  />
                </Stack>
                <Stack space="space.050">
                  <label htmlFor="new-user-email">Email（可选，仅通知）</label>
                  <Textfield
                    id="new-user-email"
                    value={email}
                    onChange={(e) => setEmail(e.currentTarget.value)}
                  />
                </Stack>
                {createdUrl && (
                  <SectionMessage appearance="success" title="一次性设置密码链接（24 小时）">
                    <Stack space="space.100">
                      <code>{createdUrl}</code>
                      <Inline>
                        <Button spacing="compact" onClick={() => void copy(createdUrl)}>
                          复制
                        </Button>
                      </Inline>
                      <Text size="small">
                        请通过可信渠道发给该用户；链接只能使用一次。
                      </Text>
                    </Stack>
                  </SectionMessage>
                )}
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setCreateOpen(false)}>
                关闭
              </Button>
              <Button
                appearance="primary"
                onClick={createHuman}
                isDisabled={!name.trim()}
              >
                创建
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {rolesTarget && (
          <ModalDialog onClose={() => setRolesTarget(null)} label="组织角色">
            <ModalHeader>
              <ModalTitle>组织角色 · {rolesTarget.name}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.100">
                <Checkbox
                  label="user-manager（管理用户）"
                  isChecked={roles.includes("user_manager")}
                  onChange={(e) =>
                    setRoles(
                      e.currentTarget.checked
                        ? [...roles, "user_manager"]
                        : roles.filter((r) => r !== "user_manager"),
                    )
                  }
                />
                <Checkbox
                  label="project-director（创建项目、改派项目经理）"
                  isChecked={roles.includes("project_director")}
                  onChange={(e) =>
                    setRoles(
                      e.currentTarget.checked
                        ? [...roles, "project_director"]
                        : roles.filter((r) => r !== "project_director"),
                    )
                  }
                />
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setRolesTarget(null)}>
                取消
              </Button>
              <Button appearance="primary" onClick={saveRoles}>
                保存
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {resetUrl && (
          <ModalDialog onClose={() => setResetUrl("")} label="密码重置链接">
            <ModalHeader>
              <ModalTitle>密码重置链接</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <SectionMessage appearance="information" title="一次性链接（24 小时）">
                <code>{resetUrl}</code>
              </SectionMessage>
            </ModalBody>
            <ModalFooter>
              <Button spacing="compact" onClick={() => void copy(resetUrl)}>
                复制链接
              </Button>
              <Button appearance="primary" onClick={() => setResetUrl("")}>
                关闭
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Box>
  );
}

function HumanGroup({
  human,
  agents,
  isOwner,
  onReset,
  onToggle,
  onRevoke,
  onRoles,
  onTransferOwner,
}: {
  human: OrgUser;
  agents: OrgUser[];
  isOwner: boolean;
  onReset: () => void;
  onToggle: () => void;
  onRevoke: () => void;
  onRoles: () => void;
  onTransferOwner: () => void;
}) {
  const orgOwner = human.org_roles.includes("org_owner");
  return (
    <>
      <tr style={{ cursor: "default" }}>
        <td>
          <Text weight="medium">{human.name}</Text>
        </td>
        <td>
          <Lozenge appearance="default">human</Lozenge>
        </td>
        <td>
          <Inline space="space.050">
            {human.org_roles.length === 0 ? (
              <Text size="small" color="color.text.subtlest">
                —
              </Text>
            ) : (
              human.org_roles.map((r) => (
                <Lozenge key={r} appearance={r === "org_owner" ? "inprogress" : "new"}>
                  {r}
                </Lozenge>
              ))
            )}
          </Inline>
        </td>
        <td className="cell-meta">{human.email ?? "—"}</td>
        <td>
          <Lozenge appearance={human.is_active ? "success" : "default"}>
            {human.is_active ? "启用" : "停用"}
          </Lozenge>
        </td>
        <td>
          <Inline space="space.050">
            {!orgOwner && (
              <>
                <Button spacing="compact" onClick={onReset}>
                  重置链接
                </Button>
                <Button spacing="compact" appearance="subtle" onClick={onToggle}>
                  {human.is_active ? "停用" : "启用"}
                </Button>
                <Button spacing="compact" appearance="subtle" onClick={onRevoke}>
                  撤销令牌
                </Button>
              </>
            )}
            {isOwner && !orgOwner && (
              <>
                <Button spacing="compact" appearance="subtle" onClick={onRoles}>
                  组织角色
                </Button>
                <Button spacing="compact" appearance="subtle" onClick={onTransferOwner}>
                  设为 Owner
                </Button>
              </>
            )}
          </Inline>
        </td>
      </tr>
      {agents.map((a) => (
        <tr key={a.id} className="rdm-table-child" style={{ cursor: "default" }}>
          <td>
            <Inline space="space.100" alignBlock="center">
              <span className="rdm-indent" aria-hidden>
                ↳
              </span>
              <Text size="small">{a.name}</Text>
            </Inline>
          </td>
          <td>
            <Lozenge appearance="warning">agent</Lozenge>
          </td>
          <td colSpan={3}>
            <Text size="small" color="color.text.subtlest">
              由其 human 在「我的设置」中管理
            </Text>
          </td>
          <td>
            <Lozenge appearance={a.effective_active ? "success" : "default"}>
              {a.effective_active ? "生效" : "停用"}
            </Lozenge>
          </td>
        </tr>
      ))}
    </>
  );
}
