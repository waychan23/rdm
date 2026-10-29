import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
import SectionMessage from "@atlaskit/section-message";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, xcss } from "@atlaskit/primitives";

import { Page, PageHeader } from "../components/Page";
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

const contentStyles = xcss({
  display: "flex",
  flexDirection: "column",
  flex: "1",
  minHeight: "0",
});

const centeredStyles = xcss({
  display: "flex",
  justifyContent: "center",
  padding: "space.400",
});

const filterWidthStyles = xcss({
  width: "140px",
});

const searchWidthStyles = xcss({
  width: "180px",
});

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
    <Page fill testId="page-backlog">
      <PageHeader
        title="工作项"
        testId="backlog-header"
        actions={
          <Button
            appearance="primary"
            testId="work-item-create-button"
            onClick={() => setShowCreate(true)}
          >
            新建
          </Button>
        }
      />

      <Inline
        space="space.150"
        alignBlock="center"
        shouldWrap
        testId="work-item-filters"
      >
        {KIND_OPTIONS.map((k) => (
          <Checkbox
            key={k.value}
            label={k.label}
            value={k.value}
            isChecked={kinds.includes(k.value)}
            testId={`work-item-filter-kind-${k.value}`}
            onChange={(e) => toggleKind(k.value, e.currentTarget.checked)}
          />
        ))}
        <Box xcss={filterWidthStyles} testId="work-item-filter-status">
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
        <Box xcss={filterWidthStyles} testId="work-item-filter-assignee">
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
        <Box xcss={searchWidthStyles}>
          <Textfield
            placeholder="搜索标题"
            value={qInput}
            testId="work-item-search"
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
        </Box>
      </Inline>

      <Box xcss={contentStyles} testId="backlog-content">
        {itemsState.loading ? (
          <Box xcss={centeredStyles} testId="work-item-loading">
            <Spinner size="large" />
          </Box>
        ) : itemsState.error ? (
          <SectionMessage appearance="error" title="加载失败">
            无法获取工作项列表，请调整筛选或刷新页面重试。
          </SectionMessage>
        ) : (itemsState.data?.items.length ?? 0) === 0 ? (
          <Box testId="work-item-empty">
            <EmptyState
              header="没有符合条件的工作项"
              description="调整筛选，或点「新建」创建第一个。"
            />
          </Box>
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
    </Page>
  );
}
