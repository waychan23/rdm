import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import TextArea from "@atlaskit/textarea";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import ConfirmDialog from "../components/ConfirmDialog";
import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { OrgUser, Project, ProjectMemberRow } from "../types";

const infoBlock = xcss({
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
  padding: "space.200",
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: "space.200",
});

const nameCellStyles = xcss({ gridColumn: "1 / -1" });

const formStyles = xcss({ maxWidth: "520px" });

const centeredStyles = xcss({
  display: "flex",
  justifyContent: "center",
  padding: "space.400",
});

export default function SettingsPage() {
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();

  const [nonce, setNonce] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);

  const { data, loading } = useAsync<{ project: Project; members: ProjectMemberRow[] }>(
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
      notify.success("项目已保存");
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  const saveOwner = async (userId: string | null) => {
    if (!userId || userId === data?.project.owner_user_id) return;
    try {
      await api.post(`/projects/${projectKey}/transfer-owner`, { user_id: userId });
      reload();
      notify.success("项目经理已改派");
    } catch (e) {
      notify.error("改派失败", errorCause(e)?.message);
    }
  };

  const archive = async () => {
    setConfirmArchive(false);
    try {
      await api.post(`/projects/${projectKey}/archive`);
      reload();
    } catch (e) {
      notify.error("归档失败", errorCause(e)?.message);
    }
  };

  if (loading || !data) {
    return (
      <Page testId="page-project-settings">
        <Box xcss={centeredStyles} testId="project-settings-loading">
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

  return (
    <Page testId="page-project-settings">
      <PageHeader title={`项目设置 · ${projectKey}`} testId="project-settings-header" />

      <Box xcss={infoBlock} testId="project-settings-info">
        <Stack space="space.050">
          <Text size="small" color="color.text.subtlest">
            项目 ID
          </Text>
          <Text>{data.project.id}</Text>
        </Stack>
        <Stack space="space.050">
          <Text size="small" color="color.text.subtlest">
            状态
          </Text>
          <Lozenge appearance={data.project.status === "archived" ? "default" : "success"}>
            {data.project.status}
          </Lozenge>
        </Stack>
        <Stack space="space.050" xcss={nameCellStyles}>
          <Text size="small" color="color.text.subtlest">
            项目经理
          </Text>
          <Text>{owner?.user.name ?? "—"}</Text>
        </Stack>
      </Box>

      <Box as="form" onSubmit={saveProject} xcss={formStyles} testId="project-settings-form">
        <Stack space="space.150">
          <Heading size="small">基本信息</Heading>
          <FormField label="名称" htmlFor="project-name">
            <Textfield
              id="project-name"
              value={name}
              testId="project-settings-name"
              onChange={(e) => setName(e.currentTarget.value)}
            />
          </FormField>
          <FormField label="描述" htmlFor="project-desc">
            <TextArea
              id="project-desc"
              value={description}
              minimumRows={3}
              testId="project-settings-description"
              onChange={(e) => setDescription(e.currentTarget.value)}
            />
          </FormField>
          <Inline space="space.100">
            <Button
              type="submit"
              appearance="primary"
              isLoading={saving}
              testId="project-settings-save"
            >
              保存
            </Button>
            <Button
              appearance="danger"
              testId="project-archive-button"
              onClick={() => setConfirmArchive(true)}
              isDisabled={data.project.status === "archived"}
            >
              归档项目
            </Button>
          </Inline>
        </Stack>
      </Box>

      <Box xcss={formStyles} testId="project-owner-section">
        <Stack space="space.150">
          <Heading size="small">项目经理（Project Owner）</Heading>
          <Text size="small" color="color.text.subtlest">
            project-director / Org Owner 或现任项目经理可以改派；目标必须是项目内启用的 human。
          </Text>
          <Select
            inputId="project-owner"
            options={humans.map((h) => ({
              label: `${h.user.name}${h.roles.includes("project_owner") ? "（Owner）" : ""}`,
              value: h.user.id,
            }))}
            value={
              ownerId
                ? { label: owner?.user.name ?? "", value: ownerId }
                : null
            }
            onChange={(opt) => {
              const id = (opt as { value: string } | null)?.value ?? null;
              setOwnerId(id);
              void saveOwner(id);
            }}
            isClearable={false}
          />
        </Stack>
      </Box>

      <ConfirmDialog
        open={confirmArchive}
        title="归档项目"
        confirmLabel="归档"
        danger
        testId="project-archive-dialog"
        onClose={() => setConfirmArchive(false)}
        onConfirm={() => void archive()}
      >
        归档项目 {projectKey}？归档后仍可只读访问。
      </ConfirmDialog>
    </Page>
  );
}
