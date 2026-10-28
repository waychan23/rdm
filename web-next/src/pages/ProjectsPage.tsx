import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import Textfield from "@atlaskit/textfield";
import TextArea from "@atlaskit/textarea";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Project } from "../types";

const pageStyles = xcss({
  padding: "space.300",
});

const gridWrapStyles = xcss({
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
  gap: "space.200",
  marginTop: "space.250",
});

const cardStyles = xcss({
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
  padding: "space.250",
  backgroundColor: "elevation.surface",
  cursor: "pointer",
  ":hover": {
    backgroundColor: "color.background.neutral.subtle.hovered",
    borderColor: "color.border.focused",
  },
});

export default function ProjectsPage() {
  const navigate = useNavigate();
  const notify = useNotify();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ key: "", name: "", description_md: "" });

  const { data: projects, reload } = useAsync(
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
      setForm({ key: "", name: "", description_md: "" });
      await reload();
    } catch (e) {
      notify.error("创建失败", errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box xcss={pageStyles}>
      <Inline spread="space-between" alignBlock="center" space="space.200">
        <Heading size="large">项目</Heading>
        <Button appearance="primary" onClick={() => setDialogOpen(true)}>
          新建项目
        </Button>
      </Inline>

      <Box xcss={gridWrapStyles}>
        {(projects ?? []).map((p) => (
          <Box
            key={p.id}
            xcss={cardStyles}
            padding="space.250"
            onClick={() => navigate(`/projects/${p.key}`)}
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
              </Inline>
            </Stack>
          </Box>
        ))}
      </Box>

      <ModalTransition>
        {dialogOpen && (
          <ModalDialog onClose={() => setDialogOpen(false)}>
            <ModalHeader>
              <ModalTitle>新建项目</ModalTitle>
            </ModalHeader>
            <form onSubmit={create}>
              <ModalBody>
                <Stack space="space.150">
                  <Stack space="space.050">
                    <label htmlFor="project-key">Key</label>
                    <Textfield
                      id="project-key"
                      value={form.key}
                      placeholder="DEMO"
                      onChange={(e) => setForm({ ...form, key: e.currentTarget.value })}
                    />
                  </Stack>
                  <Stack space="space.050">
                    <label htmlFor="project-name">名称</label>
                    <Textfield
                      id="project-name"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
                    />
                  </Stack>
                  <Stack space="space.050">
                    <label htmlFor="project-desc">描述</label>
                    <TextArea
                      id="project-desc"
                      value={form.description_md}
                      minimumRows={2}
                      onChange={(e) =>
                        setForm({ ...form, description_md: e.currentTarget.value })
                      }
                    />
                  </Stack>
                </Stack>
              </ModalBody>
              <ModalFooter>
                <Button appearance="subtle" onClick={() => setDialogOpen(false)}>
                  取消
                </Button>
                <Button type="submit" appearance="primary" isLoading={saving}>
                  创建
                </Button>
              </ModalFooter>
            </form>
          </ModalDialog>
        )}
      </ModalTransition>
    </Box>
  );
}
