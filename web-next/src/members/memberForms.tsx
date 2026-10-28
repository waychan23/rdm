import { useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Textfield from "@atlaskit/textfield";
import Select from "@atlaskit/select";
import Checkbox from "@atlaskit/checkbox";
import { RadioGroup } from "@atlaskit/radio";
import { Stack, Inline } from "@atlaskit/primitives";

import type { Member } from "../types";

export const WEBHOOK_FORMATS = ["generic", "dingtalk", "feishu"].map((v) => ({
  label: v,
  value: v,
}));

const labelStyle = {
  display: "block",
  fontWeight: "var(--ds-font-weight-medium, 500)",
  marginBottom: 4,
} as const;

interface Option {
  label: string;
  value: string;
}

export function MemberEditDialog({
  open,
  member,
  onClose,
  onSave,
}: {
  open: boolean;
  member: Member | null;
  onClose: () => void;
  onSave: (id: string, payload: Record<string, unknown>) => Promise<void> | void;
}) {
  const [rolesText, setRolesText] = useState("");
  const [acceptKinds, setAcceptKinds] = useState<string[]>([]);
  const [email, setEmail] = useState("");
  const [webhook, setWebhook] = useState("");
  const [format, setFormat] = useState<Option>(WEBHOOK_FORMATS[0]);
  const [active, setActive] = useState(true);
  const [saving, setSaving] = useState(false);

  // Sync state when the dialog opens for a member.
  const [syncedId, setSyncedId] = useState<string | null>(null);
  if (open && member && syncedId !== member.id) {
    setSyncedId(member.id);
    setRolesText(member.roles.join(","));
    setAcceptKinds([...(member.accept_kinds ?? [])]);
    setEmail(member.email ?? "");
    setWebhook(member.notify_webhook ?? "");
    setFormat(
      WEBHOOK_FORMATS.find((f) => f.value === member.notify_webhook_format) ??
        WEBHOOK_FORMATS[0],
    );
    setActive(member.is_active);
  }
  if (!open && syncedId !== null) setSyncedId(null);

  return (
    <ModalTransition>
      {open && member && (
        <ModalDialog onClose={onClose} width="480px">
          <ModalHeader>
            <ModalTitle>编辑成员 · {member.name}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Stack space="space.050">
                <label htmlFor="me-roles" style={labelStyle}>
                  角色（逗号分隔）
                </label>
                <Textfield
                  id="me-roles"
                  value={rolesText}
                  onChange={(e) => setRolesText(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <span style={labelStyle}>可接 kinds</span>
                <Inline space="space.150">
                  {["story", "issue", "task"].map((k) => (
                    <Checkbox
                      key={k}
                      label={k}
                      isChecked={acceptKinds.includes(k)}
                      onChange={(e) =>
                        setAcceptKinds((prev) =>
                          e.currentTarget.checked ? [...prev, k] : prev.filter((x) => x !== k),
                        )
                      }
                    />
                  ))}
                </Inline>
              </Stack>
              <Stack space="space.050">
                <label htmlFor="me-email" style={labelStyle}>
                  Email
                </label>
                <Textfield id="me-email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="me-webhook" style={labelStyle}>
                  Webhook URL
                </label>
                <Textfield
                  id="me-webhook"
                  value={webhook}
                  onChange={(e) => setWebhook(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <label style={labelStyle}>Webhook 格式</label>
                <Select
                  options={WEBHOOK_FORMATS}
                  value={format}
                  onChange={(o) => o && setFormat(o as Option)}
                />
              </Stack>
              <Checkbox
                label="启用"
                isChecked={active}
                onChange={(e) => setActive(e.currentTarget.checked)}
              />
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              onClick={async () => {
                setSaving(true);
                await onSave(member.id, {
                  roles: rolesText.split(",").map((r) => r.trim()).filter(Boolean),
                  accept_kinds: acceptKinds,
                  email: email || null,
                  notify_webhook: webhook || null,
                  notify_webhook_format: format.value,
                  is_active: active,
                });
                setSaving(false);
              }}
            >
              保存
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}

export function CreateMemberDialog({
  open,
  humans,
  onClose,
  onCreate,
}: {
  open: boolean;
  humans: Member[];
  onClose: () => void;
  onCreate: (payload: Record<string, unknown>) => Promise<void> | void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState("human");
  const [rolesText, setRolesText] = useState("worker");
  const [managerId, setManagerId] = useState<Option | null>(null);
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [webhook, setWebhook] = useState("");
  const [format, setFormat] = useState<Option>(WEBHOOK_FORMATS[0]);
  const [saving, setSaving] = useState(false);

  const managerOptions: Option[] = humans.map((m) => ({ label: m.name, value: m.id }));

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="480px">
          <ModalHeader>
            <ModalTitle>新增成员</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Stack space="space.050">
                <label htmlFor="mc-name" style={labelStyle}>
                  名称
                </label>
                <Textfield id="mc-name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
              </Stack>
              <Stack space="space.050">
                <span style={labelStyle}>类型</span>
                <RadioGroup
                  options={[
                    { name: "member-type", value: "human", label: "human" },
                    { name: "member-type", value: "agent", label: "agent" },
                  ]}
                  value={type}
                  onChange={(e) => setType(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="mc-roles" style={labelStyle}>
                  角色
                </label>
                <Textfield
                  id="mc-roles"
                  value={rolesText}
                  placeholder="owner,manager,worker（逗号分隔）"
                  onChange={(e) => setRolesText(e.currentTarget.value)}
                />
              </Stack>
              {type === "agent" && (
                <Stack space="space.050">
                  <label style={labelStyle}>Manager（必选）</label>
                  <Select
                    options={managerOptions}
                    value={managerId}
                    onChange={(o) => setManagerId((o as Option) ?? null)}
                    placeholder="选择同项目 human 负责人"
                  />
                </Stack>
              )}
              {type === "human" && (
                <Stack space="space.050">
                  <label htmlFor="mc-password" style={labelStyle}>
                    初始密码
                  </label>
                  <Textfield
                    id="mc-password"
                    type="password"
                    value={password}
                    placeholder="至少 8 位；留空则不能登录（之后可重置）"
                    onChange={(e) => setPassword(e.currentTarget.value)}
                  />
                </Stack>
              )}
              <Stack space="space.050">
                <label htmlFor="mc-email" style={labelStyle}>
                  Email
                </label>
                <Textfield id="mc-email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="mc-webhook" style={labelStyle}>
                  Webhook URL
                </label>
                <Textfield
                  id="mc-webhook"
                  value={webhook}
                  placeholder="https://…"
                  onChange={(e) => setWebhook(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <label style={labelStyle}>Webhook 格式</label>
                <Select
                  options={WEBHOOK_FORMATS}
                  value={format}
                  onChange={(o) => o && setFormat(o as Option)}
                />
              </Stack>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              onClick={async () => {
                if (type === "agent" && !managerId) return;
                setSaving(true);
                await onCreate({
                  name,
                  type,
                  roles: rolesText.split(",").map((r) => r.trim()).filter(Boolean),
                  manager_member_id: type === "agent" ? managerId?.value : null,
                  email: email || null,
                  notify_webhook: webhook || null,
                  notify_webhook_format: format.value,
                  password: type === "human" && password ? password : null,
                });
                setSaving(false);
              }}
            >
              创建
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}

export function ResetPasswordDialog({
  open,
  memberName,
  onClose,
  onReset,
}: {
  open: boolean;
  memberName: string;
  onClose: () => void;
  onReset: (password: string | null) => Promise<string>;
}) {
  const [password, setPassword] = useState("");
  const [plaintext, setPlaintext] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="440px">
          <ModalHeader>
            <ModalTitle>重置登录密码 · {memberName}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            {plaintext ? (
              <Stack space="space.100">
                <span>新密码（只显示一次）：</span>
                <strong data-testid="plain-password">{plaintext}</strong>
              </Stack>
            ) : (
              <Textfield
                placeholder="新密码（留空随机生成，至少 8 位）"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.currentTarget.value)}
              />
            )}
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              {plaintext ? "关闭" : "取消"}
            </Button>
            {!plaintext && (
              <Button
                appearance="primary"
                isLoading={busy}
                onClick={async () => {
                  setBusy(true);
                  setPlaintext(await onReset(password || null));
                  setBusy(false);
                }}
              >
                重置
              </Button>
            )}
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
