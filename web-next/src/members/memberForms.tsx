import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Box, Stack, Text } from "@atlaskit/primitives";
import Select from "@atlaskit/select";

import FormField from "../components/FormField";
import type { OrgUser, ProjectMemberRow } from "../types";

export const PROJECT_ROLES = [
  { label: "project_owner", value: "project_owner" },
  { label: "manager", value: "manager" },
  { label: "sprint_manager", value: "sprint_manager" },
  { label: "worker", value: "worker" },
];

function rolesToOptions(roles: string[]) {
  return PROJECT_ROLES.filter((r) => roles.includes(r.value));
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
            <ModalTitle>添加项目成员</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.200">
              <FormField
                label="组织用户"
                htmlFor="add-member-user"
                hint="该用户名下的 agent 会自动加入项目；agent 不需要也不能单独添加。"
              >
                <Select
                  inputId="add-member-user"
                  placeholder="选择组织内的 human 用户"
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
                />
              </FormField>
              <FormField label="项目角色">
                <Select
                  inputId="add-member-roles"
                  isMulti
                  options={PROJECT_ROLES}
                  value={rolesToOptions(roles)}
                  onChange={(opts) =>
                    setRoles((opts as readonly { value: string }[]).map((o) => o.value))
                  }
                />
              </FormField>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="member-add-cancel">
              取消
            </Button>
            <Button
              appearance="primary"
              onClick={submit}
              isLoading={saving}
              isDisabled={!userId}
              testId="member-add-submit"
            >
              添加
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
  onClose,
  onSave,
}: {
  open: boolean;
  member: ProjectMemberRow | null;
  onClose: () => void;
  onSave: (userId: string, roles: string[]) => Promise<void>;
}) {
  const [roles, setRoles] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && member) setRoles([...member.roles]);
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
            <ModalTitle>项目角色 · {member.name}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Box>
              <Select
                inputId="edit-member-roles"
                isMulti
                options={PROJECT_ROLES}
                value={rolesToOptions(roles)}
                onChange={(opts) =>
                  setRoles((opts as readonly { value: string }[]).map((o) => o.value))
                }
              />
              <Text size="small" color="color.text.subtlest">
                项目必须至少保留一个启用的 project_owner。
              </Text>
            </Box>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="member-edit-cancel">
              取消
            </Button>
            <Button
              appearance="primary"
              onClick={submit}
              isLoading={saving}
              testId="member-edit-submit"
            >
              保存
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
