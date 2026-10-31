import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

import ConfirmDialog from "../components/ConfirmDialog";
import ErrorState from "../components/ErrorState";
import { cardBorder } from "../components/cardBorder";
import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { statusLabel } from "../lib/labels";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { OrgUser, Project, ProjectMemberRow } from "../types";

const styles = cssMap({
  infoBlock: {
     borderRadius: "var(--ds-radius-small)",
     padding: "var(--ds-space-200)",
     display: "grid",
     gridTemplateColumns: "1fr 1fr",
     gap: "var(--ds-space-200)",
  },
  nameCell: {
    gridColumn: "1 / -1"
  },
  form: {
    maxWidth: "520px"
  },
  centered: {
     display: "flex",
     justifyContent: "center",
     padding: "var(--ds-space-400)",
  },
});

export default function SettingsPage() {
  const { t } = useTranslation("org");
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();

  const [nonce, setNonce] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [pendingOwnerId, setPendingOwnerId] = useState<string | null>(null);
  const [reassigning, setReassigning] = useState(false);

  const { data, loading, error, reload: reloadAsync } = useAsync<{ project: Project; members: ProjectMemberRow[] }>(
     async () => {
       const [p, m] = await Promise.all([
         api.get<Project>(`/projects/${projectKey}`),
         api.get<ProjectMemberRow[]>(`/projects/${projectKey}/members`),
       ]);
       return { project: p.data, members: m.data };
     },
     [projectKey, nonce],
  );

  useEffect(() => {
     if (data) {
       setName(data.project.name);
       setDescription(data.project.description_md ?? "");
       setOwnerId(data.project.owner_user_id ?? null);
     }
  }, [data]);

  const reload = () => setNonce((n) => n + 1);

  const saveProject = async (e: FormEvent) => {
     e.preventDefault();
     if (saving) return;
     setSaving(true);
     try {
       await api.patch(`/projects/${projectKey}`, {
         name,
         description_md: description,
       });
       reload();
       notify.success(t("projectSettings.notices.saved"));
     } catch (e) {
       notify.error(t("projectSettings.errors.saveFailed"), errorCause(e)?.message);
     } finally {
       setSaving(false);
     }
  };

  const reassignOwner = async () => {
    if (!pendingOwnerId || reassigning) return;
    if (pendingOwnerId === data?.project.owner_user_id) {
      setPendingOwnerId(null);
      return;
    }
    setReassigning(true);
    try {
      await api.post(`/projects/${projectKey}/transfer-owner`, {
        user_id: pendingOwnerId,
      });
      setOwnerId(pendingOwnerId);
      setPendingOwnerId(null);
      reload();
      notify.success(t("projectSettings.notices.ownerReassigned"));
    } catch (e) {
      notify.error(t("projectSettings.errors.reassignFailed"), errorCause(e)?.message);
    } finally {
      setReassigning(false);
    }
  };

  const archive = async () => {
     setConfirmArchive(false);
     try {
       await api.post(`/projects/${projectKey}/archive`);
       reload();
     } catch (e) {
       notify.error(t("projectSettings.errors.archiveFailed"), errorCause(e)?.message);
     }
  };

  if (error) {
     return (
       <Page testId="page-project-settings">
         <ErrorState error={error} onRetry={reloadAsync} testId="project-settings-error" />
       </Page>
     );
  }

  if (loading || !data) {
     return (
       <Page testId="page-project-settings">
         <Box xcss={styles.centered} testId="project-settings-loading">
           <Spinner size="large" />
         </Box>
       </Page>
     );
  }

  const humans: Array<{ user: OrgUser; roles: string[] }> = data.members.map((m) => ({
     user: m,
     roles: m.roles,
  }));
  const owner = humans.find((h) => h.user.id === data.project.owner_user_id);
  const pendingOwner = humans.find((h) => h.user.id === pendingOwnerId);

  return (
     <Page testId="page-project-settings">
       <PageHeader title={t("projectSettings.title", { projectKey })} testId="project-settings-header" />

       <Box xcss={styles.infoBlock} style={cardBorder} testId="project-settings-info">
         <Stack space="space.050">
           <Text size="small" color="color.text.subtlest">
             {t("projectSettings.info.projectId")}
           </Text>
           <Text>{data.project.id}</Text>
         </Stack>
         <Stack space="space.050">
           <Text size="small" color="color.text.subtlest">
             {t("projectSettings.info.status")}
           </Text>
           <Lozenge appearance={data.project.status === "archived" ? "default" : "success"}>
             {statusLabel(data.project.status)}
           </Lozenge>
         </Stack>
         <Stack space="space.050" xcss={styles.nameCell}>
           <Text size="small" color="color.text.subtlest">
             {t("projectSettings.info.owner")}
           </Text>
           <Text>{owner?.user.name ?? "—"}</Text>
         </Stack>
       </Box>

       <Box as="form" onSubmit={saveProject} xcss={styles.form} testId="project-settings-form">
         <Stack space="space.150">
           <Heading size="small">{t("projectSettings.basic.heading")}</Heading>
           <FormField label={t("projectSettings.form.name")} htmlFor="project-name">
             <Textfield
               id="project-name"
               value={name}
               testId="project-settings-name"
               onChange={(e) => setName(e.currentTarget.value)}
             />
           </FormField>
           <FormField label={t("projectSettings.form.description")}>
             <MarkdownEditor
               value={description}
               onChange={setDescription}
               projectKey={projectKey}
               minimumRows={3}
               testId="project-settings-description"
             />
           </FormField>
           <Inline space="space.100">
             <Button
               type="submit"
               appearance="primary"
               isLoading={saving}
               testId="project-settings-save"
             >
               {t("projectSettings.form.save")}
             </Button>
             <Button
               appearance="danger"
               testId="project-archive-button"
               onClick={() => setConfirmArchive(true)}
               isDisabled={data.project.status === "archived"}
             >
               {t("projectSettings.form.archive")}
             </Button>
           </Inline>
         </Stack>
       </Box>

       <Box xcss={styles.form} testId="project-owner-section">
         <Stack space="space.150">
           <Heading size="small">{t("projectSettings.owner.heading")}</Heading>
           <Text size="small" color="color.text.subtlest">
             {t("projectSettings.owner.hint")}
           </Text>
           <Select
             inputId="project-owner"
             options={humans.map((h) => ({
               label: `${h.user.name}${
                 h.user.id === data.project.owner_user_id
                   ? t("projectSettings.owner.currentSuffix")
                   : ""
               }`,
               value: h.user.id,
             }))}
             value={
               ownerId
                 ? { label: owner?.user.name ?? "", value: ownerId }
                 : null
             }
             onChange={(opt) => {
               const id = (opt as { value: string } | null)?.value ?? null;
               if (id && id !== data.project.owner_user_id) {
                 setPendingOwnerId(id);
               }
             }}
             isClearable={false}
           />
         </Stack>
       </Box>

       <ConfirmDialog
         open={pendingOwnerId !== null}
         title={t("projectSettings.owner.transferTitle")}
         confirmLabel={t("projectSettings.owner.transferConfirm")}
         busy={reassigning}
         testId="project-owner-transfer-dialog"
         onClose={() => {
           if (!reassigning) setPendingOwnerId(null);
         }}
         onConfirm={() => void reassignOwner()}
       >
         {t("projectSettings.owner.transferBody", {
           from: owner?.user.name ?? "—",
           to: pendingOwner?.user.name ?? "—",
         })}
       </ConfirmDialog>

       <ConfirmDialog
         open={confirmArchive}
         title={t("projectSettings.archive.title")}
         confirmLabel={t("projectSettings.archive.confirm")}
         danger
         testId="project-archive-dialog"
         onClose={() => setConfirmArchive(false)}
         onConfirm={() => void archive()}
       >
         {t("projectSettings.archive.body", { projectKey })}
       </ConfirmDialog>
     </Page>
  );
}
