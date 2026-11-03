import { useEffect, useState } from "react";

import { cssMap } from "@atlaskit/css";
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
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";
import { portalMenuProps } from "../lib/portalMenu";

import FormField from "../components/FormField";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorState from "../components/ErrorState";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { formatDate } from "../lib/format";
import { kindLabel } from "../lib/labels";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import { refreshSession, useCurrentUser } from "../lib/auth";
import { beginLogin } from "../lib/oauth";
import { userLabel } from "../lib/users";
import type { OrgUser, Token } from "../types";
import "../styles/table.css";

const styles = cssMap({
  form: {
    maxWidth: "520px"
  },
});

const ACCEPT_KINDS = ["story", "issue", "task"] as const;
const ALL_ACCEPT_KINDS: string[] = [...ACCEPT_KINDS];

// Kind labels are resolved per render so they follow the active language.
function acceptKindOptions() {
  return ACCEPT_KINDS.map((value) => ({ label: kindLabel(value), value }));
}

function defaultAgentForm() {
  return {
    name: "",
    display_name: "",
    // New agents can take every kind unless the user narrows it.
    accept_kinds: [...ALL_ACCEPT_KINDS],
    email: "",
    notify_webhook: "",
    notify_webhook_format: "generic",
  };
}

// Wire-format names are product identifiers and stay untranslated.
function webhookFormatOptions() {
  return [
    { label: "generic", value: "generic" },
    { label: "dingtalk", value: "dingtalk" },
    { label: "feishu", value: "feishu" },
  ];
}

type NotificationPrefs = Record<string, Record<string, boolean>>;

// Matrix rows: wire values are product identifiers and stay untranslated.
const NOTIFICATION_TYPES = [
  { type: "mail", key: "personal.notifications.mail" },
  { type: "assignment", key: "personal.notifications.assignment" },
  { type: "step", key: "personal.notifications.step" },
  { type: "comment", key: "personal.notifications.comment" },
  { type: "mention", key: "personal.notifications.mention" },
  { type: "system", key: "personal.notifications.system" },
] as const;

const NOTIFICATION_CHANNELS = [
  { channel: "inapp", key: "personal.notifications.channels.inapp" },
  { channel: "email", key: "personal.notifications.channels.email" },
  { channel: "webhook", key: "personal.notifications.channels.webhook" },
] as const;

export default function PersonalSettingsPage() {
  const { t } = useTranslation("org");
  const kindOptions = acceptKindOptions();
  const webhookFormats = webhookFormatOptions();
  const notify = useNotify();
  const me = useCurrentUser();
  const [nonce, setNonce] = useState(0);
  const reload = () => setNonce((n) => n + 1);

  const { data: tokens, error: tokensError } = useAsync<Token[]>(
     async () => (await api.get<Token[]>("/me/tokens")).data,
     [nonce],
  );
  const { data: agents, error: agentsError } = useAsync<OrgUser[]>(
     async () => (await api.get<OrgUser[]>("/me/agents")).data,
     [nonce],
  );
  const prefsState = useAsync<NotificationPrefs>(
     async () =>
       (await api.get<{ prefs: NotificationPrefs }>("/me/notification-prefs")).data.prefs,
     [nonce],
  );
  const [prefs, setPrefs] = useState<NotificationPrefs>({});
  useEffect(() => {
     if (prefsState.data) setPrefs(prefsState.data);
  }, [prefsState.data]);
  const loadError = tokensError ?? agentsError ?? prefsState.error;

  const prefEnabled = (channel: string, type: string) => prefs[channel]?.[type] ?? true;

  const togglePref = async (channel: string, type: string, enabled: boolean) => {
     setPrefs((prev) => ({
       ...prev,
       [channel]: { ...prev[channel], [type]: enabled },
     }));
     try {
       await api.patch("/me/notification-prefs", { prefs: { [channel]: { [type]: enabled } } });
     } catch (e) {
       setPrefs((prev) => ({
         ...prev,
         [channel]: { ...prev[channel], [type]: !enabled },
       }));
       notify.error(t("personal.notifications.saveFailed"), errorCause(e)?.message);
     }
  };

  // --- profile ---
  const [profileDisplayName, setProfileDisplayName] = useState("");
  const [profileEmail, setProfileEmail] = useState("");
  const [profileWebhook, setProfileWebhook] = useState("");
  const [profileWebhookFormat, setProfileWebhookFormat] = useState("generic");
  const [savingProfile, setSavingProfile] = useState(false);
  useEffect(() => {
     setProfileDisplayName(me?.user.display_name ?? "");
     setProfileEmail(me?.user.email ?? "");
     setProfileWebhook(me?.user.notify_webhook ?? "");
     setProfileWebhookFormat(me?.user.notify_webhook_format ?? "generic");
  }, [
    me?.user.id,
    me?.user.display_name,
    me?.user.email,
    me?.user.notify_webhook,
    me?.user.notify_webhook_format,
  ]);
  const saveProfile = async () => {
     if (savingProfile) return;
     setSavingProfile(true);
     try {
       await api.patch("/me", {
         display_name: profileDisplayName.trim() || null,
         email: profileEmail.trim() || null,
         notify_webhook: profileWebhook.trim() || null,
         notify_webhook_format: profileWebhookFormat,
       });
       await refreshSession();
       notify.success(t("personal.saved"));
     } catch (e) {
       notify.error(t("personal.saveFailed"), errorCause(e)?.message);
     } finally {
       setSavingProfile(false);
     }
  };

  // --- password ---
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const changePassword = async () => {
     try {
       await api.post("/auth/password", { old_password: oldPw, new_password: newPw });
       setOldPw("");
       setNewPw("");
       notify.success(t("personal.password.changed"));
       await beginLogin("/settings");
     } catch (e) {
       notify.error(t("personal.password.failed"), errorCause(e)?.message);
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
       notify.error(t("personal.tokens.issueFailed"), errorCause(e)?.message);
     } finally {
       setSavingToken(false);
     }
  };

  const [revokeTarget, setRevokeTarget] = useState<Token | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [hideRevoked, setHideRevoked] = useState(false);
  const visibleTokens = (tokens ?? []).filter((t) => !hideRevoked || t.is_valid);

  const copyIssuedToken = async () => {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued);
      notify.success(t("personal.tokens.copied"));
    } catch {
      notify.error(t("personal.tokens.copyFailed"), t("personal.tokens.copyHint"));
    }
  };

  const revokeToken = async () => {
     if (!revokeTarget || revoking) return;
     setRevoking(true);
     try {
       await api.del(`/me/tokens/${revokeTarget.id}`);
       setRevokeTarget(null);
       reload();
       notify.success(t("personal.tokens.revokedNotice"));
     } catch (e) {
       notify.error(t("personal.tokens.revokeFailed"), errorCause(e)?.message);
     } finally {
       setRevoking(false);
     }
  };

  // --- agents ---
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentForm, setAgentForm] = useState(defaultAgentForm);
  const [savingAgent, setSavingAgent] = useState(false);

  useEffect(() => {
    if (agentOpen) setAgentForm(defaultAgentForm());
  }, [agentOpen]);

  const createAgent = async () => {
     if (savingAgent) return;
     setSavingAgent(true);
     try {
       const body = {
         name: agentForm.name.trim(),
         display_name: agentForm.display_name.trim() || null,
         accept_kinds: agentForm.accept_kinds,
         email: agentForm.email || null,
         notify_webhook: agentForm.notify_webhook || null,
         notify_webhook_format: agentForm.notify_webhook_format,
       };
       await api.post("/me/agents", body);
       setAgentOpen(false);
       setAgentForm(defaultAgentForm());
       reload();
     } catch (e) {
       notify.error(t("personal.agents.createFailed"), errorCause(e)?.message);
     } finally {
       setSavingAgent(false);
     }
  };

  const toggleAgent = async (agent: OrgUser) => {
     try {
       await api.patch(`/me/agents/${agent.id}`, { is_active: !agent.is_active });
       reload();
     } catch (e) {
       notify.error(t("personal.actionFailed"), errorCause(e)?.message);
     }
  };

  const [editAgent, setEditAgent] = useState<OrgUser | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editHook, setEditHook] = useState("");
  const [editFmt, setEditFmt] = useState("generic");

  useEffect(() => {
     if (editAgent) {
       setEditDisplayName(editAgent.display_name ?? "");
       setEditHook(editAgent.notify_webhook ?? "");
       setEditFmt(editAgent.notify_webhook_format ?? "generic");
     }
  }, [editAgent]);

  const saveAgent = async () => {
     if (!editAgent) return;
     try {
       await api.patch(`/me/agents/${editAgent.id}`, {
         display_name: editDisplayName.trim() || null,
         notify_webhook: editHook || null,
         notify_webhook_format: editFmt,
       });
       setEditAgent(null);
       reload();
       notify.success(t("personal.saved"));
     } catch (e) {
       notify.error(t("personal.saveFailed"), errorCause(e)?.message);
     }
  };

  return (
     <Page testId="page-personal-settings">
       <PageHeader title={t("personal.title")} testId="personal-settings-header" />

       {loadError ? (
         <ErrorState error={loadError} onRetry={reload} testId="personal-settings-error" />
       ) : null}

       <Box testId="personal-profile-section">
        <Stack space="space.150" xcss={styles.form}>
          <Heading size="small">{t("personal.profile.heading")}</Heading>
          <FormField
            label={t("personal.profile.displayName")}
            htmlFor="profile-display-name"
          >
            <Textfield
              id="profile-display-name"
              value={profileDisplayName}
              testId="personal-display-name"
              onChange={(e) => setProfileDisplayName(e.currentTarget.value)}
            />
          </FormField>
          <FormField label={t("personal.profile.email")} htmlFor="profile-email">
            <Textfield
              id="profile-email"
              type="email"
              value={profileEmail}
              testId="personal-email"
              onChange={(e) => setProfileEmail(e.currentTarget.value)}
            />
          </FormField>
          <FormField label={t("personal.profile.webhook")} htmlFor="profile-webhook">
            <Textfield
              id="profile-webhook"
              value={profileWebhook}
              testId="personal-webhook"
              onChange={(e) => setProfileWebhook(e.currentTarget.value)}
            />
          </FormField>
          <FormField
            label={t("personal.profile.webhookFormat")}
            htmlFor="profile-webhook-format"
          >
            <Select
              inputId="profile-webhook-format"
              spacing="compact"
              options={webhookFormats}
              value={webhookFormats.find((o) => o.value === profileWebhookFormat)}
              onChange={(option) => setProfileWebhookFormat(option?.value ?? "generic")}
              testId="personal-webhook-format"
            />
          </FormField>
          <Inline>
            <Button
              appearance="primary"
              onClick={saveProfile}
              isLoading={savingProfile}
              testId="personal-display-name-save"
            >
              {t("personal.profile.save")}
            </Button>
          </Inline>
        </Stack>
      </Box>

      <Box testId="personal-password-section">
         <Stack space="space.150" xcss={styles.form}>
           <Heading size="small">{t("personal.password.heading")}</Heading>
           <FormField label={t("personal.password.old")} htmlFor="old-pw">
             <Textfield
               id="old-pw"
               type="password"
               autoComplete="current-password"
               value={oldPw}
               testId="personal-old-password"
               onChange={(e) => setOldPw(e.currentTarget.value)}
             />
           </FormField>
           <FormField label={t("personal.password.new")} htmlFor="new-pw">
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
               {t("personal.password.submit")}
             </Button>
           </Inline>
           <Text size="small" color="color.text.subtlest">
             {t("personal.password.hint")}
           </Text>
         </Stack>
       </Box>

       <Box testId="personal-notification-section">
         <Stack space="space.150">
           <Heading size="small">{t("personal.notifications.heading")}</Heading>
           <Text size="small" color="color.text.subtle">
             {t("personal.notifications.hint")}
           </Text>
           <table
             className="rdm-table"
             aria-label={t("personal.notifications.tableAria")}
             data-testid="personal-notification-matrix"
           >
             <thead>
               <tr>
                 <th scope="col" className="col-person">
                   {t("personal.notifications.content")}
                 </th>
                 {NOTIFICATION_CHANNELS.map(({ channel, key }) => (
                   <th key={channel} scope="col" className="col-active">
                     {t(key)}
                   </th>
                 ))}
               </tr>
             </thead>
             <tbody>
               {NOTIFICATION_TYPES.map(({ type, key }) => (
                 <tr key={type}>
                   <td>{t(key)}</td>
                   {NOTIFICATION_CHANNELS.map(({ channel }) => (
                     <td key={channel} className="col-active">
                       {channel === "inapp" && type === "mail" ? (
                         <Text size="small" color="color.text.subtlest">
                           {t("personal.notifications.notApplicable")}
                         </Text>
                       ) : (
                         <Checkbox
                           label=""
                           isChecked={prefEnabled(channel, type)}
                           testId={`personal-notification-${channel}-${type}`}
                           onChange={(e) =>
                             void togglePref(channel, type, e.currentTarget.checked)
                           }
                         />
                       )}
                     </td>
                   ))}
                 </tr>
               ))}
             </tbody>
           </table>
           {!profileEmail.trim() || !profileWebhook.trim() ? (
             <Text size="small" color="color.text.subtlest">
               {t("personal.notifications.missingChannelHint")}
             </Text>
           ) : null}
         </Stack>
       </Box>

       <Box testId="personal-tokens-section">
         <Stack space="space.200">
           <Inline spread="space-between" alignBlock="center">
             <Heading size="small">{t("personal.tokens.heading")}</Heading>
             <Inline space="space.100" alignBlock="center">
               <Checkbox
                 label={t("personal.tokens.hideRevoked")}
                 isChecked={hideRevoked}
                 testId="personal-token-hide-revoked"
                 onChange={(e) => setHideRevoked(e.currentTarget.checked)}
               />
               <Button
                 testId="personal-token-create-button"
                 onClick={() => {
                   setIssued("");
                   setTokenOpen(true);
                 }}
               >
                 {t("personal.tokens.createButton")}
               </Button>
             </Inline>
           </Inline>
           {visibleTokens.length === 0 ? (
             <Text size="small" color="color.text.subtlest">
               {(tokens ?? []).length > 0
                 ? t("personal.tokens.emptyValid")
                 : t("personal.tokens.emptyAll")}
             </Text>
           ) : (
             <table className="rdm-table" aria-label={t("personal.tokens.tableAria")} data-testid="personal-token-table">
               <thead>
                 <tr>
                   <th scope="col" className="col-label">
                     {t("personal.tokens.columns.label")}
                   </th>
                   <th scope="col" className="col-label">
                     {t("personal.tokens.columns.identity")}
                   </th>
                   <th scope="col" className="col-created">
                     {t("personal.tokens.columns.created")}
                   </th>
                   <th scope="col" className="col-expires">
                     {t("personal.tokens.columns.expires")}
                   </th>
                   <th scope="col" className="col-active">
                     {t("personal.tokens.columns.status")}
                   </th>
                   <th scope="col" className="col-active">
                     {t("personal.tokens.columns.actions")}
                   </th>
                 </tr>
               </thead>
               <tbody>
                 {visibleTokens.map((token) => (
                   <tr key={token.id} data-testid={`personal-token-row-${token.id}`}>
                     <td className="cell-meta">{token.label ?? "—"}</td>
                     <td className="cell-meta">
                       {token.act_as_user_id
                         ? t("personal.tokens.agentIdentity", {
                             name: userLabel(
                               agents?.find((a) => a.id === token.act_as_user_id),
                             ),
                           })
                         : t("personal.tokens.self")}
                     </td>
                     <td className="cell-meta">{formatDate(token.created_at)}</td>
                     <td className="cell-meta">
                       {token.expires_at
                         ? formatDate(token.expires_at)
                         : t("personal.tokens.permanent")}
                     </td>
                     <td>
                       <Lozenge appearance={token.is_valid ? "success" : "default"}>
                         {token.is_valid
                           ? t("personal.tokens.valid")
                           : t("personal.tokens.revoked")}
                       </Lozenge>
                     </td>
                     <td>
                       {token.is_valid && (
                         <Button
                           spacing="compact"
                           appearance="danger"
                           testId={`personal-token-revoke-${token.id}`}
                           onClick={() => setRevokeTarget(token)}
                         >
                           {t("personal.tokens.revoke")}
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
               <Heading size="small">{t("personal.agents.heading")}</Heading>
               <Text size="small" color="color.text.subtlest">
                 {t("personal.agents.hint")}
               </Text>
             </Stack>
             <Button testId="personal-agent-create-button" onClick={() => setAgentOpen(true)}>
               {t("personal.agents.createButton")}
             </Button>
           </Inline>
           {(agents ?? []).length === 0 ? (
             <Text size="small" color="color.text.subtlest">
               {t("personal.agents.empty")}
             </Text>
           ) : (
             <table
               className="rdm-table"
               aria-label={t("personal.agents.tableAria")}
               data-testid="personal-agent-table"
             >
               <thead>
                 <tr>
                   <th scope="col" className="col-person">
                     {t("personal.agents.columns.name")}
                   </th>
                   <th scope="col">{t("personal.agents.columns.kinds")}</th>
                   <th scope="col">{t("personal.agents.columns.webhook")}</th>
                   <th scope="col" className="col-active">
                     {t("personal.agents.columns.status")}
                   </th>
                   <th scope="col" className="col-date">
                     {t("personal.agents.columns.actions")}
                   </th>
                 </tr>
               </thead>
               <tbody>
                 {(agents ?? []).map((a) => (
                   <tr key={a.id} data-testid={`personal-agent-row-${a.id}`}>
                     <td>
                       <Inline space="space.100" alignBlock="center">
                         <Text>{userLabel(a)}</Text>
                         <Lozenge appearance="warning">agent</Lozenge>
                       </Inline>
                     </td>
                     <td className="cell-meta">{(a.accept_kinds ?? []).join(", ") || "—"}</td>
                     <td className="cell-meta">{a.notify_webhook ?? "—"}</td>
                     <td>
                       <Lozenge appearance={a.is_active ? "success" : "default"}>
                         {a.is_active
                           ? t("users.status.enabled")
                           : t("users.status.disabled")}
                       </Lozenge>
                     </td>
                     <td>
                       <Inline space="space.100">
                         <Button
                           spacing="compact"
                           testId={`personal-agent-notify-${a.id}`}
                           onClick={() => setEditAgent(a)}
                         >
                           {t("personal.agents.notify")}
                         </Button>
                         <Button
                           spacing="compact"
                           appearance={a.is_active ? "danger" : "default"}
                           testId={`personal-agent-toggle-${a.id}`}
                           onClick={() => void toggleAgent(a)}
                         >
                           {a.is_active
                             ? t("users.actions.disable")
                             : t("users.actions.enable")}
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
             label={t("personal.tokenDialog.dialogLabel")}
             testId="personal-token-dialog"
           >
             <ModalHeader>
               <ModalTitle>{t("personal.tokenDialog.title")}</ModalTitle>
             </ModalHeader>
             <ModalBody>
               {issued ? (
                 <SectionMessage appearance="success" title={t("personal.tokenDialog.onceTitle")}>
                   <Stack space="space.100">
                     <code style={{ wordBreak: "break-all" }}>{issued}</code>
                     <Inline>
                       <Button
                         spacing="compact"
                         testId="personal-token-copy"
                         onClick={() => void copyIssuedToken()}
                       >
                         {t("personal.tokenDialog.copy")}
                       </Button>
                     </Inline>
                     <Text size="small">{t("personal.tokenDialog.onceHint")}</Text>
                   </Stack>
                 </SectionMessage>
               ) : (
                 <Stack space="space.150">
                   <FormField label={t("personal.tokenDialog.label")} htmlFor="token-label">
                     <Textfield
                       id="token-label"
                       value={tokenLabel}
                       testId="personal-token-label"
                       onChange={(e) => setTokenLabel(e.currentTarget.value)}
                     />
                   </FormField>
                   <FormField label={t("personal.tokenDialog.days")} htmlFor="token-days">
                     <Textfield
                       id="token-days"
                       type="number"
                       value={tokenDays}
                       testId="personal-token-days"
                       onChange={(e) => setTokenDays(e.currentTarget.value)}
                     />
                   </FormField>
                   <FormField label={t("personal.tokenDialog.identity")}>
                     <Select {...portalMenuProps}
                       inputId="token-act-as"
                       placeholder={t("personal.tokenDialog.identityPlaceholder")}
                       options={(agents ?? []).map((a) => ({
                         label: t("personal.tokenDialog.agentOption", { name: userLabel(a) }),
                         value: a.id,
                       }))}
                       value={
                         actAs
                           ? {
                               label: userLabel(agents?.find((a) => a.id === actAs)),
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
                 </Stack>
               )}
             </ModalBody>
             <ModalFooter>
               {issued ? (
                 <Button
                   appearance="primary"
                   testId="personal-token-dialog-close"
                   onClick={() => setTokenOpen(false)}
                 >
                   {t("personal.tokenDialog.close")}
                 </Button>
               ) : (
                 <>
                   <Button
                     appearance="subtle"
                     testId="personal-token-dialog-close"
                     onClick={() => setTokenOpen(false)}
                   >
                     {t("personal.tokenDialog.close")}
                   </Button>
                   <Button
                     appearance="primary"
                     onClick={createToken}
                     isLoading={savingToken}
                     testId="personal-token-submit"
                   >
                     {t("personal.tokenDialog.create")}
                   </Button>
                 </>
               )}
             </ModalFooter>
           </ModalDialog>
         )}
       </ModalTransition>

       <ModalTransition>
         {agentOpen && (
           <ModalDialog
             onClose={() => setAgentOpen(false)}
             width="520px"
             label={t("personal.agentDialog.dialogLabel")}
             testId="personal-agent-dialog"
           >
             <ModalHeader>
               <ModalTitle>{t("personal.agentDialog.title")}</ModalTitle>
             </ModalHeader>
             <ModalBody>
               <Stack space="space.150">
                 <FormField label={t("personal.agentDialog.name")} htmlFor="agent-name">
                   <Textfield
                     id="agent-name"
                     value={agentForm.name}
                     testId="personal-agent-name"
                     onChange={(e) => setAgentForm({ ...agentForm, name: e.currentTarget.value })}
                   />
                 </FormField>
                 <FormField
                   label={t("personal.agentDialog.displayName")}
                   htmlFor="agent-display-name"
                 >
                   <Textfield
                     id="agent-display-name"
                     value={agentForm.display_name}
                     testId="personal-agent-display-name"
                     onChange={(e) =>
                       setAgentForm({ ...agentForm, display_name: e.currentTarget.value })
                     }
                   />
                 </FormField>
                 <FormField label={t("personal.agentDialog.kinds")}>
                   <Select {...portalMenuProps}
                     inputId="agent-kinds"
                     isMulti
                     options={kindOptions}
                     value={kindOptions.filter((k) =>
                       agentForm.accept_kinds.includes(k.value),
                     )}
                     onChange={(opts) =>
                       setAgentForm({
                         ...agentForm,
                         accept_kinds: (opts as readonly { value: string }[]).map((o) => o.value),
                       })
                     }
                   />
                 </FormField>
                 <FormField label={t("personal.agentDialog.webhook")} htmlFor="agent-hook">
                   <Textfield
                     id="agent-hook"
                     value={agentForm.notify_webhook}
                     testId="personal-agent-hook"
                     onChange={(e) =>
                       setAgentForm({ ...agentForm, notify_webhook: e.currentTarget.value })
                     }
                   />
                 </FormField>
                 <FormField label={t("personal.agentDialog.format")}>
                   <Select {...portalMenuProps}
                     inputId="agent-fmt"
                     options={webhookFormats}
                     value={webhookFormats.find((f) => f.value === agentForm.notify_webhook_format)}
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
                 {t("personal.agentDialog.cancel")}
               </Button>
               <Button
                 appearance="primary"
                 onClick={createAgent}
                 isLoading={savingAgent}
                 isDisabled={!agentForm.name.trim()}
                 testId="personal-agent-submit"
               >
                 {t("personal.agentDialog.create")}
               </Button>
             </ModalFooter>
           </ModalDialog>
         )}
       </ModalTransition>

       <ModalTransition>
         {editAgent && (
           <ModalDialog
             onClose={() => setEditAgent(null)}
             label={t("personal.agentNotify.title", { name: userLabel(editAgent) })}
             testId="personal-agent-notify-dialog"
           >
             <ModalHeader>
               <ModalTitle>{t("personal.agentNotify.title", { name: userLabel(editAgent) })}</ModalTitle>
             </ModalHeader>
             <ModalBody>
               <Stack space="space.150">
                 <FormField
                   label={t("personal.agentNotify.displayName")}
                   htmlFor="edit-display-name"
                 >
                   <Textfield
                     id="edit-display-name"
                     value={editDisplayName}
                     testId="personal-agent-edit-display-name"
                     onChange={(e) => setEditDisplayName(e.currentTarget.value)}
                   />
                 </FormField>
                 <FormField label={t("personal.agentNotify.webhook")} htmlFor="edit-hook">
                   <Textfield
                     id="edit-hook"
                     value={editHook}
                     testId="personal-agent-notify-hook"
                     onChange={(e) => setEditHook(e.currentTarget.value)}
                   />
                 </FormField>
                 <FormField label={t("personal.agentNotify.format")}>
                   <Select {...portalMenuProps}
                     inputId="edit-fmt"
                     options={webhookFormats}
                     value={webhookFormats.find((f) => f.value === editFmt)}
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
                 {t("personal.agentNotify.cancel")}
               </Button>
               <Button
                 appearance="primary"
                 testId="personal-agent-notify-save"
                 onClick={saveAgent}
               >
                 {t("personal.agentNotify.save")}
               </Button>
             </ModalFooter>
           </ModalDialog>
         )}
       </ModalTransition>

       <ConfirmDialog
         open={revokeTarget !== null}
         title={t("personal.revokeDialog.title")}
         confirmLabel={t("personal.revokeDialog.confirm")}
         danger
         busy={revoking}
         testId="personal-token-revoke-dialog"
         onClose={() => {
           if (!revoking) setRevokeTarget(null);
         }}
         onConfirm={() => void revokeToken()}
       >
         {t("personal.revokeDialog.body", { label: revokeTarget?.label ?? "—" })}
       </ConfirmDialog>
     </Page>
  );
}
