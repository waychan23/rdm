import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import EmptyState from "@atlaskit/empty-state";
import Spinner from "@atlaskit/spinner";
import Heading from "@atlaskit/heading";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives";

import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import type { ProjectMemberRow, WorkItem, WorkflowDto } from "../types";
import { flattenMembers } from "../lib/members";
import { KIND_OPTIONS, PAGE_SIZE } from "../workitems/constants";
import WorkItemTable from "../workitems/WorkItemTable";
import CreateWorkItemDialog from "../workitems/CreateWorkItemDialog";

interface Option {
  label: string;
  value: string;
}

export default function BacklogPage() {
  const { key: projectKey = "RDM" } = useParams();
  const navigate = useNavigate();

  const [kinds, setKinds] = useState<string[]>(["epic", "story", "issue", "task"]);
  const [status, setStatus] = useState<Option | null>(null);
  const [assignee, setAssignee] = useState<Option | null>(null);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  const membersState = useAsync<ProjectMemberRow[]>(
    async () => (await api.get<ProjectMemberRow[]>(`/projects/${projectKey}/members`)).data,
    [projectKey],
  );
  const workflowState = useAsync<WorkflowDto>(
    async () => (await api.get<WorkflowDto>("/workflow")).data,
    [projectKey],
  );

  const statusOptions = useMemo<Option[]>(() => {
    const states = new Set<string>();
    Object.values(workflowState.data?.kinds ?? {}).forEach((k) =>
      k.states.forEach((s) => states.add(s)),
    );
    return [...states].map((s) => ({ label: s, value: s }));
  }, [workflowState.data]);

  const assigneeOptions = useMemo<Option[]>(() => {
    return [
      { label: "我的", value: "me" },
      ...flattenMembers(membersState.data ?? []).map((m) => ({ label: m.name, value: m.id })),
    ];
  }, [membersState.data]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String((page - 1) * PAGE_SIZE),
    });
    if (kinds.length === 1) params.set("kind", kinds[0]);
    if (status) params.set("status", status.value);
    if (assignee) params.set("assignee", assignee.value === "me" ? "me" : assignee.value);
    if (q) params.set("q", q);
    return params.toString();
  }, [kinds, status, assignee, q, page]);

  const itemsState = useAsync<{ items: WorkItem[]; total: number }>(
    async () => {
      const res = await api.get<WorkItem[]>(
        `/projects/${projectKey}/work-items?${queryString}`,
      );
      return { items: res.data, total: Number(res.meta?.total ?? res.data.length) };
    },
    [projectKey, queryString, reloadNonce],
  );

  const toggleKind = (value: string, checked: boolean) => {
    // Zero selected kinds means "all" (only exactly one sends kind=).
    setKinds((prev) => (checked ? [...prev, value] : prev.filter((k) => k !== value)));
    setPage(1);
  };

  const openItem = (item: WorkItem) =>
    navigate(`/projects/${projectKey}/items/${item.id}`);

  return (
    <Box padding="space.300" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Stack space="space.150">
        <Heading size="large">工作项</Heading>
        <Inline space="space.150" shouldWrap>
          {KIND_OPTIONS.map((k) => (
            <Checkbox
              key={k.value}
              label={k.label}
              value={k.value}
              isChecked={kinds.includes(k.value)}
              onChange={(e) => toggleKind(k.value, e.currentTarget.checked)}
            />
          ))}
          <Box style={{ width: 140 }}>
            <Select<Option>
              options={statusOptions}
              value={status}
              onChange={(opt) => {
                setStatus(opt as Option | null);
                setPage(1);
              }}
              isClearable
              spacing="compact"
              placeholder="状态"
            />
          </Box>
          <Box style={{ width: 140 }}>
            <Select<Option>
              options={assigneeOptions}
              value={assignee}
              onChange={(opt) => {
                setAssignee(opt as Option | null);
                setPage(1);
              }}
              isClearable
              spacing="compact"
              placeholder="负责人"
            />
          </Box>
          <Textfield
            width={180}
            placeholder="搜索标题"
            value={qInput}
            onChange={(e) => setQInput(e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setQ(qInput.trim());
                setPage(1);
              }
            }}
            onBlur={() => {
              if (q !== qInput.trim()) {
                setQ(qInput.trim());
                setPage(1);
              }
            }}
          />
          <Button appearance="primary" onClick={() => setShowCreate(true)}>
            新建
          </Button>
        </Inline>
      </Stack>

      <Box style={{ flex: 1, minHeight: 0, marginTop: 12 }}>
        {itemsState.loading ? (
          <Box padding="space.400" style={{ display: "flex", justifyContent: "center" }}>
            <Spinner size="large" />
          </Box>
        ) : itemsState.error ? (
          <Text color="color.text.danger">加载失败</Text>
        ) : (itemsState.data?.items.length ?? 0) === 0 ? (
          <EmptyState header="没有符合条件的工作项" description="调整筛选，或点「新建」创建第一个。" />
        ) : (
          <WorkItemTable
            items={itemsState.data!.items}
            total={itemsState.data!.total}
            page={page}
            pageSize={PAGE_SIZE}
            onOpen={openItem}
            onPageChange={setPage}
          />
        )}
      </Box>

      <CreateWorkItemDialog
        open={showCreate}
        projectKey={projectKey}
        onClose={() => setShowCreate(false)}
        onCreated={(item) => {
          setReloadNonce((n) => n + 1);
          setPage(1);
          openItem(item);
        }}
      />
    </Box>
  );
}
