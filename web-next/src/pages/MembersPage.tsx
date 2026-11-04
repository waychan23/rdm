import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useListProjectKey } from "../lib/originSearch";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import EmptyState from "@atlaskit/empty-state";
import Lozenge from "@atlaskit/lozenge";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

import ConfirmDialog from "../components/ConfirmDialog";
import ErrorState from "../components/ErrorState";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { roleLabel } from "../lib/labels";
import {
  invalidateProjectMembers,
  loadProjectMembers,
} from "../lib/members";
import { userLabel } from "../lib/users";
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
  const { t } = useTranslation("members");
  return (
    <tr className="rdm-table-child" data-testid={`member-agent-row-${agent.user.id}`}>
      <td>
        <Inline space="space.100" alignBlock="center">
          <span className="rdm-indent" aria-hidden>
            ↳
          </span>
          <Text size="small">{userLabel(agent.user)}</Text>
          <Lozenge appearance="default">{t("agent.auto")}</Lozenge>
          {!agent.user.effective_active && (
            <Lozenge appearance="default">{t("agent.disabled")}</Lozenge>
          )}
        </Inline>
      </td>
      <td>
        <Lozenge appearance="warning">{agent.user.type}</Lozenge>
      </td>
      <td>
        <Text size="small" color="color.text.subtlest">
          {t("agent.inherited")}
        </Text>
      </td>
      <td>
        <Text size="small" color="color.text.subtlest">
          {agent.user.notify_webhook ?? "—"}
        </Text>
      </td>
      <td>
        <Lozenge appearance={agent.user.effective_active ? "success" : "default"}>
          {agent.user.effective_active ? t("agent.status.enabled") : t("agent.status.disabled")}
        </Lozenge>
      </td>
      <td />
    </tr>
  );
}

export default function MembersPage() {
  const { t } = useTranslation("members");
  const { key: routeKey = "" } = useParams();
  // The origin URL owns the project while this page is a drawer backdrop.
  const projectKey = useListProjectKey(routeKey);
  const notify = useNotify();

  const [showAdd, setShowAdd] = useState(false);
  const [editMember, setEditMember] = useState<ProjectMemberRow | null>(null);
  const [removeTarget, setRemoveTarget] = useState<ProjectMemberRow | null>(null);
  const [nonce, setNonce] = useState(0);

  const { data: members, loading, error, reload: reloadAsync } = useAsync<ProjectMemberRow[]>(
    async () => loadProjectMembers(projectKey, { force: nonce > 0 }),
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
      invalidateProjectMembers(projectKey);
      setShowAdd(false);
      reload();
    } catch (e) {
      notify.error(t("errors.addFailed"), errorCause(e)?.message);
    }
  };

  const saveRoles = async (userId: string, roles: string[]) => {
    try {
      await api.patch(`/projects/${projectKey}/members/${userId}`, { roles });
      invalidateProjectMembers(projectKey);
      setEditMember(null);
      reload();
      notify.success(t("notices.saved"));
    } catch (e) {
      notify.error(t("errors.saveFailed"), errorCause(e)?.message);
    }
  };

  const remove = async () => {
    if (!removeTarget) return;
    try {
      await api.del(`/projects/${projectKey}/members/${removeTarget.id}`);
      invalidateProjectMembers(projectKey);
      setRemoveTarget(null);
      reload();
    } catch (e) {
      notify.error(t("errors.removeFailed"), errorCause(e)?.message);
    }
  };

  const removeExtra =
    removeTarget?.agents && removeTarget.agents.length > 0
      ? t("removeDialog.extra", { count: removeTarget.agents.length })
      : "";

  return (
    <Page testId="page-members">
      <PageHeader
        title={t("page.title", { projectKey })}
        testId="members-header"
        actions={
          <Button appearance="primary" testId="member-add-button" onClick={() => setShowAdd(true)}>
            {t("page.addMember")}
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
            header={t("empty.header")}
            description={t("empty.description")}
          />
        </Box>
      ) : (
        <table className="rdm-table" aria-label={t("table.aria")} data-testid="member-table">
          <thead>
            <tr>
              <th scope="col" className="col-name">
                {t("table.name")}
              </th>
              <th scope="col" className="col-type">
                {t("table.type")}
              </th>
              <th scope="col">{t("table.roles")}</th>
              <th scope="col">{t("table.webhook")}</th>
              <th scope="col" className="col-active">
                {t("table.active")}
              </th>
              <th scope="col" className="col-actions">
                {t("table.actions")}
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
        title={t("removeDialog.title")}
        danger
        confirmLabel={t("removeDialog.confirm")}
        testId="member-remove-dialog"
        onClose={() => setRemoveTarget(null)}
        onConfirm={() => void remove()}
      >
        {t("removeDialog.body", {
          name: removeTarget ? userLabel(removeTarget) : "—",
          extra: removeExtra,
        })}
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
  const { t } = useTranslation("members");
  return (
    <>
      <tr data-testid={`member-row-${member.id}`}>
        <td>
          <Inline space="space.100" alignBlock="center">
            <Text weight="medium">{userLabel(member)}</Text>
            {isOwner && <Lozenge appearance="inprogress">{t("ownerBadge")}</Lozenge>}
            {!member.is_active && <Lozenge appearance="default">{t("agent.disabled")}</Lozenge>}
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
            {member.is_active ? t("member.status.enabled") : t("member.status.disabled")}
          </Lozenge>
        </td>
        <td>
          <Inline space="space.100">
            <Button spacing="compact" testId={`member-edit-${member.id}`} onClick={onEdit}>
              {t("member.roles")}
            </Button>
            <Button
              spacing="compact"
              appearance="danger"
              testId={`member-remove-${member.id}`}
              onClick={onRemove}
            >
              {t("member.remove")}
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
