import { useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
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
import { Box, Grid, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { useCurrentUser } from "../lib/auth";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Project } from "../types";

const cardStyles = xcss({
  display: "block",
  width: "100%",
  padding: "space.250",
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
  backgroundColor: "elevation.surface",
  color: "color.text",
  font: "inherit",
  textAlign: "start",
  cursor: "pointer",
  ":hover": {
    backgroundColor: "elevation.surface.raised.hovered",
    borderColor: "color.border.focused",
  },
  ":focus-visible": {
    outline: "2px solid",
    outlineColor: "color.border.focused",
    outlineOffset: "space.025",
  },
});

const loadingStyles = xcss({
  display: "flex",
  justifyContent: "center",
  padding: "space.400",
});

const FORM_INITIAL = { key: "", name: "", description_md: "" };

export default function ProjectsPage() {
  const navigate = useNavigate();
  const notify = useNotify();
  const me = useCurrentUser();
  const canCreate =
    !!me && (me.org_roles.includes("org_owner") || me.org_roles.includes("project_director"));
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(FORM_INITIAL);

  const { data: projects, error, loading, reload } = useAsync(
    async () => (await api.get<Project[]>("/projects")).data,
    [],
  );

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      await api.post("/projects", { ...form });
      setDialogOpen(false);
      setForm(FORM_INITIAL);
      reload();
    } catch (e) {
      notify.error("创建失败", errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Page testId="page-projects">
      <PageHeader
        title="项目"
        testId="projects-header"
        actions={
          canCreate ? (
            <Button
              appearance="primary"
              testId="projects-create-button"
              onClick={() => setDialogOpen(true)}
            >
              新建项目
            </Button>
          ) : null
        }
      />

      {loading ? (
        <Box xcss={loadingStyles} testId="projects-loading">
          <Spinner size="large" />
        </Box>
      ) : error ? (
        <SectionMessage appearance="error" title="加载失败">
          无法获取项目列表，请刷新页面重试。
        </SectionMessage>
      ) : (projects ?? []).length === 0 ? (
        <Box testId="projects-empty">
          <EmptyState
            header="还没有可访问的项目"
            description={
              canCreate
                ? "点击右上角「新建项目」创建第一个项目；你会自动成为项目经理。"
                : "请联系 Org Owner 或 project-director 创建项目，并把你加入成员。"
            }
          />
        </Box>
      ) : (
        <Grid
          gap="space.200"
          templateColumns="repeat(auto-fill, minmax(240px, 1fr))"
          testId="projects-grid"
        >
          {(projects ?? []).map((p) => (
            <Box
              key={p.id}
              role="button"
              tabIndex={0}
              xcss={cardStyles}
              testId={`project-card-${p.key}`}
              onClick={() => navigate(`/projects/${p.key}`)}
              onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  navigate(`/projects/${p.key}`);
                }
              }}
            >
              <Stack space="space.150">
                <Text weight="semibold">{p.name}</Text>
                <Inline space="space.100" alignBlock="center">
                  <Text size="small" color="color.link">
                    {p.key}
                  </Text>
                  <Lozenge appearance={p.status === "archived" ? "default" : "success"}>
                    {p.status === "archived" ? "已归档" : "进行中"}
                  </Lozenge>
                  {(p.roles ?? []).includes("project_owner") && (
                    <Lozenge appearance="inprogress">Owner</Lozenge>
                  )}
                </Inline>
              </Stack>
            </Box>
          ))}
        </Grid>
      )}

      <ModalTransition>
        {dialogOpen && (
          <ModalDialog onClose={() => setDialogOpen(false)} testId="project-create-dialog">
            <ModalHeader>
              <ModalTitle>新建项目</ModalTitle>
            </ModalHeader>
            <form onSubmit={create}>
              <ModalBody>
                <Stack space="space.150">
                  <FormField label="Key" htmlFor="project-key">
                    <Textfield
                      id="project-key"
                      value={form.key}
                      placeholder="DEMO"
                      testId="project-create-key"
                      onChange={(e) => setForm({ ...form, key: e.currentTarget.value })}
                    />
                  </FormField>
                  <FormField label="名称" htmlFor="project-name">
                    <Textfield
                      id="project-name"
                      value={form.name}
                      testId="project-create-name"
                      onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
                    />
                  </FormField>
                  <FormField label="描述" htmlFor="project-desc">
                    <TextArea
                      id="project-desc"
                      value={form.description_md}
                      minimumRows={2}
                      testId="project-create-description"
                      onChange={(e) =>
                        setForm({ ...form, description_md: e.currentTarget.value })
                      }
                    />
                  </FormField>
                </Stack>
              </ModalBody>
              <ModalFooter>
                <Button
                  appearance="subtle"
                  testId="project-create-cancel"
                  onClick={() => setDialogOpen(false)}
                >
                  取消
                </Button>
                <Button
                  type="submit"
                  appearance="primary"
                  isLoading={saving}
                  testId="project-create-submit"
                >
                  创建
                </Button>
              </ModalFooter>
            </form>
          </ModalDialog>
        )}
      </ModalTransition>
    </Page>
  );
}
