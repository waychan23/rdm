import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import Lozenge from "@atlaskit/lozenge";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import { useTranslation } from "react-i18next";

import FormField from "../components/FormField";
import { roleLabel } from "../lib/labels";
import { portalMenuProps } from "../lib/portalMenu";
import type { OrgUser, ProjectMemberRow } from "../types";

// Resolved per render so role labels follow the active language.
function projectRoleOptions() {
  return [
    { label: roleLabel("manager"), value: "manager" },
    { label: roleLabel("sprint_manager"), value: "sprint_manager" },
    { label: roleLabel("worker"), value: "worker" },
  ];
}

function rolesToOptions(roles: string[], options: ReturnType<typeof projectRoleOptions>) {
  return options.filter((r) => roles.includes(r.value));
}

/** Add an existing organization human to the project (§17). */
export function AddMemberDialog({
  open,
  candidates,
  onClose,
  onAdd,
}: {
  open: boolean;
  candidates: OrgUser[];
  onClose: () => void;
  onAdd: (userId: string, roles: string[]) => Promise<void>;
}) {
  const { t } = useTranslation("members");
  const roleOptions = projectRoleOptions();
  const [userId, setUserId] = useState<string | null>(null);
  const [roles, setRoles] = useState<string[]>(["worker"]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setUserId(null);
      setRoles(["worker"]);
    }
  }, [open]);

  const submit = async () => {
    if (!userId || saving) return;
    setSaving(true);
    try {
      await onAdd(userId, roles);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} testId="member-add-dialog">
          <ModalHeader>
            <ModalTitle>{t("addDialog.title")}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.200">
              <FormField
                label={t("addDialog.userLabel")}
                htmlFor="add-member-user"
                hint={t("addDialog.userHint")}
              >
                <Select
                  inputId="add-member-user"
                  placeholder={t("addDialog.userPlaceholder")}
                  options={candidates.map((u) => ({ label: u.name, value: u.id }))}
                  value={
                    userId
                      ? {
                          label: candidates.find((u) => u.id === userId)?.name ?? "",
                          value: userId,
                        }
                      : null
                  }
                  onChange={(opt) =>
                    setUserId((opt as { value: string } | null)?.value ?? null)
                  }
                  isClearable
                  {...portalMenuProps}
                />
              </FormField>
              <FormField
                label={t("addDialog.roleLabel")}
                hint={t("addDialog.roleHint")}
              >
                <Select
                  inputId="add-member-roles"
                  isMulti
                  placeholder={t("addDialog.rolePlaceholder")}
                  options={roleOptions}
                  value={rolesToOptions(roles, roleOptions)}
                  onChange={(opts) =>
                    setRoles((opts as readonly { value: string }[]).map((o) => o.value))
                  }
                  {...portalMenuProps}
                />
              </FormField>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="member-add-cancel">
              {t("addDialog.cancel")}
            </Button>
            <Button
              appearance="primary"
              onClick={submit}
              isLoading={saving}
              isDisabled={!userId}
              testId="member-add-submit"
            >
              {t("addDialog.add")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}

/** Edit a human's project roles. Agent rows are read-only. */
export function MemberEditDialog({
  open,
  member,
  ownerUserId,
  onClose,
  onSave,
}: {
  open: boolean;
  member: ProjectMemberRow | null;
  ownerUserId: string | null;
  onClose: () => void;
  onSave: (userId: string, roles: string[]) => Promise<void>;
}) {
  const { t } = useTranslation("members");
  const roleOptions = projectRoleOptions();
  const [roles, setRoles] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const isOwner = !!member && member.id === ownerUserId;

  useEffect(() => {
    // project_owner is mirrored from project.owner_user_id, not a generic role.
    if (open && member) {
      setRoles(member.roles.filter((r) => r !== "project_owner"));
    }
  }, [open, member]);

  const submit = async () => {
    if (!member || saving) return;
    setSaving(true);
    try {
      await onSave(member.id, roles);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && member && (
        <ModalDialog onClose={onClose} testId="member-edit-dialog">
          <ModalHeader>
            <ModalTitle>{t("editDialog.title", { name: member.name })}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.100">
              {isOwner && (
                <Inline space="space.050" alignBlock="center">
                  <Text size="small" color="color.text.subtlest">
                    {t("editDialog.fixedRole")}
                  </Text>
                  <Lozenge appearance="inprogress">{roleLabel("project_owner")}</Lozenge>
                </Inline>
              )}
              <Select
                inputId="edit-member-roles"
                isMulti
                placeholder={t("editDialog.rolePlaceholder")}
                options={roleOptions}
                value={rolesToOptions(roles, roleOptions)}
                onChange={(opts) =>
                  setRoles((opts as readonly { value: string }[]).map((o) => o.value))
                }
                {...portalMenuProps}
              />
              <Text size="small" color="color.text.subtlest">
                {isOwner
                  ? t("editDialog.ownerHintLocked")
                  : t("editDialog.ownerHintOther")}
              </Text>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="member-edit-cancel">
              {t("editDialog.cancel")}
            </Button>
            <Button
              appearance="primary"
              onClick={submit}
              isLoading={saving}
              testId="member-edit-submit"
            >
              {t("editDialog.save")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
