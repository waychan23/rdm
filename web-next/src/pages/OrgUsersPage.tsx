import { useMemo, useState } from "react";

import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
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
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import ConfirmDialog from "../components/ConfirmDialog";
import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useCurrentUser } from "../lib/auth";
import { useNotify } from "../lib/flags";
import type { OrgUser } from "../types";
import "../styles/table.css";

const ASSIGNABLE_ROLES = ["user_manager", "project_director"];

const centeredStyles = xcss({
  display: "flex",
  justifyContent: "center",
  padding: "space.400",
});

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

  const [confirmRevoke, setConfirmRevoke] = useState<OrgUser | null>(null);
  const revokeAll = async () => {
    if (!confirmRevoke) return;
    try {
      await api.post(`/users/${confirmRevoke.id}/tokens/revoke-all`);
      setConfirmRevoke(null);
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

  const [confirmTransfer, setConfirmTransfer] = useState<OrgUser | null>(null);
  const transferOwner = async () => {
    if (!confirmTransfer) return;
    try {
      await api.post("/org/transfer-owner", { user_id: confirmTransfer.id });
      setConfirmTransfer(null);
      notify.success("已转让 Org Owner");
      reload();
    } catch (e) {
      notify.error("转让失败", errorCause(e)?.message);
    }
  };

  return (
    <Page testId="page-org-users">
      <PageHeader
        title="组织用户"
        testId="org-users-header"
        actions={
          <Button
            appearance="primary"
            testId="org-user-create-button"
            onClick={() => setCreateOpen(true)}
          >
            创建用户
          </Button>
        }
      />

      {loading ? (
        <Box xcss={centeredStyles} testId="org-users-loading">
          <Spinner size="large" />
        </Box>
      ) : humans.length === 0 ? (
        <Box testId="org-users-empty">
          <EmptyState
            header="还没有人类用户"
            description="点击右上角「创建用户」添加组织成员。"
          />
        </Box>
      ) : (
        <table className="rdm-table" aria-label="组织用户" data-testid="org-user-table">
          <thead>
            <tr>
              <th scope="col" className="col-name">
                名称
              </th>
              <th scope="col" className="col-type">
                类型
              </th>
              <th scope="col">组织角色</th>
              <th scope="col">Email</th>
              <th scope="col" className="col-active">
                状态
              </th>
              <th scope="col" className="col-actions-wide">
                操作
              </th>
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
                onRevoke={() => setConfirmRevoke(h)}
                onRoles={() => openRoles(h)}
                onTransferOwner={() => setConfirmTransfer(h)}
              />
            ))}
          </tbody>
        </table>
      )}

      <ModalTransition>
        {createOpen && (
          <ModalDialog
            onClose={() => setCreateOpen(false)}
            width="520px"
            label="创建用户"
            testId="org-user-create-dialog"
          >
            <ModalHeader>
              <ModalTitle>创建人类用户</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label="用户名（登录名，组织内唯一）" htmlFor="new-user-name">
                  <Textfield
                    id="new-user-name"
                    value={name}
                    testId="org-user-create-name"
                    onChange={(e) => setName(e.currentTarget.value)}
                  />
                </FormField>
                <FormField label="Email（可选，仅通知）" htmlFor="new-user-email">
                  <Textfield
                    id="new-user-email"
                    value={email}
                    testId="org-user-create-email"
                    onChange={(e) => setEmail(e.currentTarget.value)}
                  />
                </FormField>
                {createdUrl && (
                  <SectionMessage appearance="success" title="一次性设置密码链接（24 小时）">
                    <Stack space="space.100">
                      <code>{createdUrl}</code>
                      <Inline>
                        <Button
                          spacing="compact"
                          testId="org-user-created-url-copy"
                          onClick={() => void copy(createdUrl)}
                        >
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
              <Button
                appearance="subtle"
                testId="org-user-create-cancel"
                onClick={() => setCreateOpen(false)}
              >
                关闭
              </Button>
              <Button
                appearance="primary"
                testId="org-user-create-submit"
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
          <ModalDialog
            onClose={() => setRolesTarget(null)}
            label="组织角色"
            testId="org-user-roles-dialog"
          >
            <ModalHeader>
              <ModalTitle>组织角色 · {rolesTarget.name}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.100">
                <Checkbox
                  label="user-manager（管理用户）"
                  isChecked={roles.includes("user_manager")}
                  testId="org-user-role-user-manager"
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
                  testId="org-user-role-project-director"
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
              <Button
                appearance="subtle"
                testId="org-user-roles-cancel"
                onClick={() => setRolesTarget(null)}
              >
                取消
              </Button>
              <Button
                appearance="primary"
                testId="org-user-roles-save"
                onClick={saveRoles}
              >
                保存
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {resetUrl && (
          <ModalDialog
            onClose={() => setResetUrl("")}
            label="密码重置链接"
            testId="org-user-reset-dialog"
          >
            <ModalHeader>
              <ModalTitle>密码重置链接</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <SectionMessage appearance="information" title="一次性链接（24 小时）">
                <code>{resetUrl}</code>
              </SectionMessage>
            </ModalBody>
            <ModalFooter>
              <Button
                spacing="compact"
                testId="org-user-reset-copy"
                onClick={() => void copy(resetUrl)}
              >
                复制链接
              </Button>
              <Button
                appearance="primary"
                testId="org-user-reset-close"
                onClick={() => setResetUrl("")}
              >
                关闭
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ConfirmDialog
        open={confirmRevoke !== null}
        title="撤销访问令牌"
        danger
        confirmLabel="撤销"
        testId="org-user-revoke-dialog"
        onClose={() => setConfirmRevoke(null)}
        onConfirm={() => void revokeAll()}
      >
        撤销 {confirmRevoke?.name} 及其 agent 的全部访问令牌？该操作不可恢复。
      </ConfirmDialog>

      <ConfirmDialog
        open={confirmTransfer !== null}
        title="转让 Org Owner"
        danger
        confirmLabel="转让"
        testId="org-user-transfer-dialog"
        onClose={() => setConfirmTransfer(null)}
        onConfirm={() => void transferOwner()}
      >
        把 Org Owner 转让给 {confirmTransfer?.name}？你将失去超级管理员权限。
      </ConfirmDialog>
    </Page>
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
      <tr data-testid={`org-user-row-${human.id}`}>
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
                <Button
                  spacing="compact"
                  testId={`org-user-reset-${human.id}`}
                  onClick={onReset}
                >
                  重置链接
                </Button>
                <Button
                  spacing="compact"
                  appearance="subtle"
                  testId={`org-user-toggle-${human.id}`}
                  onClick={onToggle}
                >
                  {human.is_active ? "停用" : "启用"}
                </Button>
                <Button
                  spacing="compact"
                  appearance="subtle"
                  testId={`org-user-revoke-${human.id}`}
                  onClick={onRevoke}
                >
                  撤销令牌
                </Button>
              </>
            )}
            {isOwner && !orgOwner && (
              <>
                <Button
                  spacing="compact"
                  appearance="subtle"
                  testId={`org-user-roles-${human.id}`}
                  onClick={onRoles}
                >
                  组织角色
                </Button>
                <Button
                  spacing="compact"
                  appearance="subtle"
                  testId={`org-user-transfer-${human.id}`}
                  onClick={onTransferOwner}
                >
                  设为 Owner
                </Button>
              </>
            )}
          </Inline>
        </td>
      </tr>
      {agents.map((a) => (
        <tr key={a.id} className="rdm-table-child" data-testid={`org-agent-row-${a.id}`}>
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
