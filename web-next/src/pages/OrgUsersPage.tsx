import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
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
import TextArea from "@atlaskit/textarea";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

import ErrorState from "../components/ErrorState";

import ConfirmDialog from "../components/ConfirmDialog";
import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import {
  createPasswordResetToken,
  createUser,
  listUsers,
  revokeAllUserTokens,
  setUserActive,
  setUserOrgRoles,
  transferOrgOwner,
  updateUser,
} from "../api/users-api";
import { errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { refreshSession, useCurrentUser } from "../lib/auth";
import { roleLabel } from "../lib/labels";
import { useNotify } from "../lib/flags";
import { userLabel } from "../lib/users";
import type { OrgUser } from "../types";
import "../styles/table.css";

const ASSIGNABLE_ROLES = ["user_manager", "project_director"];

// The API returns a root-relative path; the UI must show/copy a complete URL
// so it can be sent to the user as-is.
function absoluteUrl(path: string): string {
  return new URL(path, window.location.origin).toString();
}

const styles = cssMap({
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
});

export default function OrgUsersPage() {
  const { t } = useTranslation("org");
  const notify = useNotify();
  const navigate = useNavigate();
  const me = useCurrentUser();
  const isOwner = !!me?.org_roles.includes("org_owner");
  const [nonce, setNonce] = useState(0);
  const reload = () => setNonce((n) => n + 1);

  const { data: users, loading, error, reload: reloadUsers } = useAsync<OrgUser[]>(
    listUsers,
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
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [createdUrl, setCreatedUrl] = useState("");

  const createHuman = async () => {
    try {
      const result = await createUser({
        name,
        display_name: displayName.trim() || null,
        email: email || null,
      });
      setCreatedUrl(absoluteUrl(result.password_reset_url));
      setName("");
      setDisplayName("");
      setEmail("");
      reload();
    } catch (e) {
      notify.error(t("users.errors.createFailed"), errorCause(e)?.message);
    }
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      notify.success(t("users.notices.linkCopied"));
    } catch {
      // clipboard may be unavailable; the link stays visible in the dialog
    }
  };

  // --- reset link ---
  const [resetUrl, setResetUrl] = useState("");
  const resetPassword = async (user: OrgUser) => {
    try {
      const result = await createPasswordResetToken(user.id);
      const url = absoluteUrl(result.password_reset_url);
      setResetUrl(url);
      void copy(url);
    } catch (e) {
      notify.error(t("users.errors.resetLinkFailed"), errorCause(e)?.message);
    }
  };

  const updateActive = async (user: OrgUser, active: boolean) => {
    try {
      await setUserActive(user.id, active);
      reload();
    } catch (e) {
      notify.error(t("users.errors.actionFailed"), errorCause(e)?.message);
    }
  };

  const [disableTarget, setDisableTarget] = useState<OrgUser | null>(null);
  const disableUser = async () => {
    if (!disableTarget) return;
    const target = disableTarget;
    setDisableTarget(null);
    await updateActive(target, false);
  };

  const [confirmRevoke, setConfirmRevoke] = useState<OrgUser | null>(null);
  const revokeAll = async () => {
    if (!confirmRevoke) return;
    try {
      await revokeAllUserTokens(confirmRevoke.id);
      setConfirmRevoke(null);
      notify.success(t("users.notices.tokensRevoked"));
    } catch (e) {
      notify.error(t("users.errors.revokeFailed"), errorCause(e)?.message);
    }
  };

  // --- edit profile ---
  const [editTarget, setEditTarget] = useState<OrgUser | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const openEdit = (user: OrgUser) => {
    setEditTarget(user);
    setEditDisplayName(user.display_name ?? "");
    setEditEmail(user.email ?? "");
    setEditDescription(user.description_md ?? "");
  };
  const saveUser = async () => {
    if (!editTarget) return;
    try {
      await updateUser(editTarget.id, {
        display_name: editDisplayName.trim() || null,
        email: editEmail.trim() || null,
        description_md: editDescription.trim() || null,
      });
      setEditTarget(null);
      reload();
      notify.success(t("users.notices.saved"));
    } catch (e) {
      notify.error(t("users.errors.saveFailed"), errorCause(e)?.message);
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
      await setUserOrgRoles(rolesTarget.id, roles);
      setRolesTarget(null);
      reload();
      notify.success(t("users.notices.saved"));
    } catch (e) {
      notify.error(t("users.errors.saveFailed"), errorCause(e)?.message);
    }
  };

  const [confirmTransfer, setConfirmTransfer] = useState<OrgUser | null>(null);
  const transferOwner = async () => {
    if (!confirmTransfer) return;
    try {
      await transferOrgOwner(confirmTransfer.id);
      setConfirmTransfer(null);
      notify.success(t("users.notices.ownerTransferred"));
      // The caller just lost org_owner; refresh the identity store and leave
      // the org-admin page instead of waiting for the next request to 403.
      await refreshSession();
      navigate("/projects");
    } catch (e) {
      notify.error(t("users.errors.transferFailed"), errorCause(e)?.message);
    }
  };

  return (
    <Page testId="page-org-users">
      <PageHeader
        title={t("users.title")}
        testId="org-users-header"
        actions={
          <Button
            appearance="primary"
            testId="org-user-create-button"
            onClick={() => setCreateOpen(true)}
          >
            {t("users.createButton")}
          </Button>
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={reloadUsers} testId="org-users-error" />
      ) : loading ? (
        <Box xcss={styles.centered} testId="org-users-loading">
          <Spinner size="large" />
        </Box>
      ) : humans.length === 0 ? (
        <Box testId="org-users-empty">
          <EmptyState
            header={t("users.emptyHeader")}
            description={t("users.emptyDescription")}
          />
        </Box>
      ) : (
        <table className="rdm-table" aria-label={t("users.tableAria")} data-testid="org-user-table">
          <thead>
            <tr>
              <th scope="col" className="col-name">
                {t("users.columns.name")}
              </th>
              <th scope="col" className="col-type">
                {t("users.columns.type")}
              </th>
              <th scope="col">{t("users.columns.roles")}</th>
              <th scope="col">{t("users.columns.email")}</th>
              <th scope="col" className="col-active">
                {t("users.columns.status")}
              </th>
              <th scope="col" className="col-actions-wide">
                {t("users.columns.actions")}
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
                onToggle={() => {
                  if (h.is_active) setDisableTarget(h);
                  else void updateActive(h, true);
                }}
                onRevoke={() => setConfirmRevoke(h)}
                onEdit={() => openEdit(h)}
                onRoles={() => openRoles(h)}
                onTransferOwner={() => setConfirmTransfer(h)}
              />
            ))}
          </tbody>
        </table>
      )}

      <ModalTransition>
        {editTarget && (
          <ModalDialog
            onClose={() => setEditTarget(null)}
            width="520px"
            label={t("editUser.dialogLabel")}
            testId="org-user-edit-dialog"
          >
            <ModalHeader>
              <ModalTitle>{t("editUser.title", { name: userLabel(editTarget) })}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label={t("editUser.displayNameLabel")} htmlFor="edit-user-display-name">
                  <Textfield
                    id="edit-user-display-name"
                    value={editDisplayName}
                    testId="org-user-edit-display-name"
                    onChange={(e) => setEditDisplayName(e.currentTarget.value)}
                  />
                </FormField>
                <FormField label={t("editUser.emailLabel")} htmlFor="edit-user-email">
                  <Textfield
                    id="edit-user-email"
                    value={editEmail}
                    testId="org-user-edit-email"
                    onChange={(e) => setEditEmail(e.currentTarget.value)}
                  />
                </FormField>
                <FormField
                  label={t("editUser.descriptionLabel")}
                  htmlFor="edit-user-description"
                >
                  <TextArea
                    id="edit-user-description"
                    value={editDescription}
                    testId="org-user-edit-description"
                    onChange={(e) => setEditDescription(e.currentTarget.value)}
                  />
                </FormField>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button
                appearance="subtle"
                testId="org-user-edit-cancel"
                onClick={() => setEditTarget(null)}
              >
                {t("editUser.cancel")}
              </Button>
              <Button
                appearance="primary"
                testId="org-user-edit-save"
                onClick={saveUser}
              >
                {t("editUser.save")}
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {createOpen && (
          <ModalDialog
            onClose={() => setCreateOpen(false)}
            width="520px"
            label={t("createUser.dialogLabel")}
            testId="org-user-create-dialog"
          >
            <ModalHeader>
              <ModalTitle>{t("createUser.title")}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label={t("createUser.nameLabel")} htmlFor="new-user-name">
                  <Textfield
                    id="new-user-name"
                    value={name}
                    testId="org-user-create-name"
                    onChange={(e) => setName(e.currentTarget.value)}
                  />
                </FormField>
                <FormField
                  label={t("createUser.displayNameLabel")}
                  htmlFor="new-user-display-name"
                >
                  <Textfield
                    id="new-user-display-name"
                    value={displayName}
                    testId="org-user-create-display-name"
                    onChange={(e) => setDisplayName(e.currentTarget.value)}
                  />
                </FormField>
                <FormField label={t("createUser.emailLabel")} htmlFor="new-user-email">
                  <Textfield
                    id="new-user-email"
                    value={email}
                    testId="org-user-create-email"
                    onChange={(e) => setEmail(e.currentTarget.value)}
                  />
                </FormField>
                {createdUrl && (
                  <SectionMessage appearance="success" title={t("createUser.linkTitle")}>
                    <Stack space="space.100">
                      <code style={{ wordBreak: "break-all" }}>{createdUrl}</code>
                      <Inline>
                        <Button
                          spacing="compact"
                          testId="org-user-created-url-copy"
                          onClick={() => void copy(createdUrl)}
                        >
                          {t("createUser.copy")}
                        </Button>
                      </Inline>
                      <Text size="small">
                        {t("createUser.linkHint")}
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
                {t("createUser.close")}
              </Button>
              <Button
                appearance="primary"
                testId="org-user-create-submit"
                onClick={createHuman}
                isDisabled={!name.trim()}
              >
                {t("createUser.create")}
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {rolesTarget && (
          <ModalDialog
            onClose={() => setRolesTarget(null)}
            label={t("rolesDialog.dialogLabel")}
            testId="org-user-roles-dialog"
          >
            <ModalHeader>
              <ModalTitle>{t("rolesDialog.title", { name: userLabel(rolesTarget) })}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.100">
                <Checkbox
                  label={t("rolesDialog.userManager", { role: roleLabel("user_manager") })}
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
                  label={t("rolesDialog.projectDirector", {
                    role: roleLabel("project_director"),
                  })}
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
                {t("rolesDialog.cancel")}
              </Button>
              <Button
                appearance="primary"
                testId="org-user-roles-save"
                onClick={saveRoles}
              >
                {t("rolesDialog.save")}
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ModalTransition>
        {resetUrl && (
          <ModalDialog
            onClose={() => setResetUrl("")}
            label={t("resetDialog.dialogLabel")}
            testId="org-user-reset-dialog"
          >
            <ModalHeader>
              <ModalTitle>{t("resetDialog.title")}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <SectionMessage appearance="information" title={t("resetDialog.linkTitle")}>
                <code style={{ wordBreak: "break-all" }}>{resetUrl}</code>
              </SectionMessage>
            </ModalBody>
            <ModalFooter>
              <Button
                spacing="compact"
                testId="org-user-reset-copy"
                onClick={() => void copy(resetUrl)}
              >
                {t("resetDialog.copy")}
              </Button>
              <Button
                appearance="primary"
                testId="org-user-reset-close"
                onClick={() => setResetUrl("")}
              >
                {t("resetDialog.close")}
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>

      <ConfirmDialog
        open={confirmRevoke !== null}
        title={t("revokeDialog.title")}
        danger
        confirmLabel={t("revokeDialog.confirm")}
        testId="org-user-revoke-dialog"
        onClose={() => setConfirmRevoke(null)}
        onConfirm={() => void revokeAll()}
      >
        {t("revokeDialog.body", {
          name: confirmRevoke ? userLabel(confirmRevoke) : "—",
        })}
      </ConfirmDialog>

      <ConfirmDialog
        open={disableTarget !== null}
        title={t("disableDialog.title")}
        confirmLabel={t("disableDialog.confirm")}
        danger
        testId="org-user-disable-dialog"
        onClose={() => setDisableTarget(null)}
        onConfirm={() => void disableUser()}
      >
        {t("disableDialog.body", {
          name: disableTarget ? userLabel(disableTarget) : "—",
        })}
      </ConfirmDialog>

      <ConfirmDialog
        open={confirmTransfer !== null}
        title={t("transferDialog.title")}
        danger
        confirmLabel={t("transferDialog.confirm")}
        testId="org-user-transfer-dialog"
        onClose={() => setConfirmTransfer(null)}
        onConfirm={() => void transferOwner()}
      >
        {t("transferDialog.body", {
          name: confirmTransfer ? userLabel(confirmTransfer) : "—",
        })}
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
  onEdit,
  onRoles,
  onTransferOwner,
}: {
  human: OrgUser;
  agents: OrgUser[];
  isOwner: boolean;
  onReset: () => void;
  onToggle: () => void;
  onRevoke: () => void;
  onEdit: () => void;
  onRoles: () => void;
  onTransferOwner: () => void;
}) {
  const { t } = useTranslation("org");
  const orgOwner = human.org_roles.includes("org_owner");
  return (
    <>
      <tr data-testid={`org-user-row-${human.id}`}>
        <td>
          <Stack space="space.025">
            <Text weight="medium">{userLabel(human)}</Text>
            {human.display_name && (
              <Text size="small" color="color.text.subtlest">
                @{human.name}
              </Text>
            )}
          </Stack>
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
                  {roleLabel(r)}
                </Lozenge>
              ))
            )}
          </Inline>
        </td>
        <td className="cell-meta">{human.email ?? "—"}</td>
        <td>
          <Lozenge appearance={human.is_active ? "success" : "default"}>
            {human.is_active ? t("users.status.enabled") : t("users.status.disabled")}
          </Lozenge>
        </td>
        <td>
          <Inline space="space.050">
            <Button
              spacing="compact"
              appearance="subtle"
              testId={`org-user-edit-${human.id}`}
              onClick={onEdit}
            >
              {t("users.actions.edit")}
            </Button>
            {!orgOwner && (
              <>
                <Button
                  spacing="compact"
                  testId={`org-user-reset-${human.id}`}
                  onClick={onReset}
                >
                  {t("users.actions.resetLink")}
                </Button>
                <Button
                  spacing="compact"
                  appearance="subtle"
                  testId={`org-user-toggle-${human.id}`}
                  onClick={onToggle}
                >
                  {human.is_active ? t("users.actions.disable") : t("users.actions.enable")}
                </Button>
                <Button
                  spacing="compact"
                  appearance="subtle"
                  testId={`org-user-revoke-${human.id}`}
                  onClick={onRevoke}
                >
                  {t("users.actions.revoke")}
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
                  {t("users.actions.roles")}
                </Button>
                <Button
                  spacing="compact"
                  appearance="subtle"
                  testId={`org-user-transfer-${human.id}`}
                  onClick={onTransferOwner}
                >
                  {t("users.actions.makeOwner")}
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
              <Text size="small">{userLabel(a)}</Text>
            </Inline>
          </td>
          <td>
            <Lozenge appearance="warning">agent</Lozenge>
          </td>
          <td colSpan={2}>
            <Text size="small" color="color.text.subtlest">
              {t("users.agentHint")}
            </Text>
          </td>
          <td>
            <Lozenge appearance={a.effective_active ? "success" : "default"}>
              {a.effective_active ? t("users.status.effective") : t("users.status.disabled")}
            </Lozenge>
          </td>
          <td />
        </tr>
      ))}
    </>
  );
}
