import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import TextArea from "@atlaskit/textarea";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

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

export default function SettingsPage() {
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();

  const [nonce, setNonce] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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
      await reload();
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
      await reload();
      notify.success("项目经理已改派");
    } catch (e) {
      notify.error("改派失败", errorCause(e)?.message);
    }
  };

  const archive = async () => {
    if (!window.confirm(`归档项目 ${projectKey}？归档后仍可只读访问。`)) return;
    try {
      await api.post(`/projects/${projectKey}/archive`);
      await reload();
    } catch (e) {
      notify.error("归档失败", errorCause(e)?.message);
    }
  };

  if (loading || !data) {
    return (
      <Box padding="space.400">
        <Spinner size="large" />
      </Box>
    );
  }

  const humans: Array<{ user: OrgUser; roles: string[] }> = data.members.map((m) => ({
    user: m,
    roles: m.roles,
  }));
  const owner = humans.find((h) => h.user.id === data.project.owner_user_id);

  return (
    <Box padding="space.300">
      <Heading size="large">项目设置 · {projectKey}</Heading>

      <Box xcss={infoBlock} style={{ marginTop: 16, marginBottom: 16 }}>
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

      <Box as="form" onSubmit={saveProject} style={{ maxWidth: 520 }}>
        <Stack space="space.150">
          <Text weight="semibold">基本信息</Text>
          <Stack space="space.050">
            <label htmlFor="project-name">名称</label>
            <Textfield
              id="project-name"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
            />
          </Stack>
          <Stack space="space.050">
            <label htmlFor="project-desc">描述</label>
            <TextArea
              id="project-desc"
              value={description}
              minimumRows={3}
              onChange={(e) => setDescription(e.currentTarget.value)}
            />
          </Stack>
          <Inline space="space.100">
            <Button type="submit" appearance="primary" isLoading={saving}>
              保存
            </Button>
            <Button
              appearance="danger"
              onClick={archive}
              isDisabled={data.project.status === "archived"}
            >
              归档项目
            </Button>
          </Inline>
        </Stack>
      </Box>

      <Box style={{ maxWidth: 520, marginTop: 32 }}>
        <Stack space="space.150">
          <Text weight="semibold">项目经理（Project Owner）</Text>
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
    </Box>
  );
}
