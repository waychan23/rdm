import { useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
import SectionMessage from "@atlaskit/section-message";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline } from "@atlaskit/primitives/compiled";

import { Page, PageHeader } from "../components/Page";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import type { ProjectMemberRow, WorkItem, WorkflowDto } from "../types";
import { flattenMembers } from "../lib/members";
import { KIND_OPTIONS, PAGE_SIZE } from "../workitems/constants";
import { buildWorkItemTree } from "../workitems/hierarchy";
import WorkItemTable, { type WorkItemRowView } from "../workitems/WorkItemTable";
import CreateWorkItemDialog from "../workitems/CreateWorkItemDialog";

interface Option {
  label: string;
  value: string;
}

type ViewMode = "flat" | "tree";

/** The tree view needs every filtered item to nest children under parents. */
const TREE_BATCH = 100;
const TREE_LIMIT = 1000;

const VIEW_KEY = (projectKey: string) => `rdm.work-items.view.${projectKey}`;
const COLLAPSED_KEY = (projectKey: string) => `rdm.work-items.collapsed.${projectKey}`;

function readView(projectKey: string): ViewMode {
  try {
    return localStorage.getItem(VIEW_KEY(projectKey)) === "tree" ? "tree" : "flat";
  } catch {
    return "flat";
  }
}

function readCollapsed(projectKey: string): Set<string> {
  try {
    const raw = localStorage.getItem(COLLAPSED_KEY(projectKey));
    const ids: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(ids) ? ids.map(String) : []);
  } catch {
    return new Set();
  }
}

/** UI preferences survive opening an item (the list remounts behind the panel). */
function writeStorage(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Private mode / storage disabled: keep the in-memory state.
  }
}

const pageStyles = cssMap({
  content: {
    display: "flex",
    flexDirection: "column",
    flex: "1",
    minHeight: "0",
  },

  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },

  filterWidth: {
    width: "140px",
  },

  searchWidth: {
    width: "180px",
  },
});

interface ItemsResult {
  items: WorkItem[];
  total: number;
  truncated: boolean;
}

async function loadTreeItems(projectKey: string, filterParams: string): Promise<ItemsResult> {
  const items: WorkItem[] = [];
  let total = 0;
  for (let offset = 0; offset < TREE_LIMIT; offset += TREE_BATCH) {
    const params = new URLSearchParams(filterParams);
    params.set("limit", String(TREE_BATCH));
    params.set("offset", String(offset));
    const res = await api.get<WorkItem[]>(`/projects/${projectKey}/work-items?${params}`);
    total = Number(res.meta?.total ?? res.data.length);
    items.push(...res.data);
    if (items.length >= total || res.data.length === 0) break;
  }
  return { items, total, truncated: items.length < total };
}

export default function BacklogPage() {
  const { key: projectKey = "RDM" } = useParams();
  // Remount per project so the stored view/collapse preferences are re-read
  // when switching projects without a full remount of the route.
  return <BacklogView key={projectKey} projectKey={projectKey} />;
}

function BacklogView({ projectKey }: { projectKey: string }) {
  const navigate = useNavigate();
  const location = useLocation();

  const [kinds, setKinds] = useState<string[]>(["epic", "story", "issue", "task"]);
  const [status, setStatus] = useState<Option | null>(null);
  const [assignee, setAssignee] = useState<Option | null>(null);
  const [reviewer, setReviewer] = useState<Option | null>(null);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [view, setView] = useState<ViewMode>(() => readView(projectKey));
  const [collapsed, setCollapsed] = useState<Set<string>>(() => readCollapsed(projectKey));
  const treeMode = view === "tree";

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
    Object.values(workflowState.data?.kinds ?? {}).forEach((k) => {
      k.states.forEach((s) => states.add(s));
      Object.values(k.subtypes ?? {}).forEach((subtype) =>
        subtype.states.forEach((s) => states.add(s)),
      );
    });
    return [...states].map((s) => ({ label: s, value: s }));
  }, [workflowState.data]);

  const assigneeOptions = useMemo<Option[]>(() => {
    return [
      { label: "我的", value: "me" },
      ...flattenMembers(membersState.data ?? []).map((m) => ({ label: m.name, value: m.id })),
    ];
  }, [membersState.data]);

  const filterParams = useMemo(() => {
    const params = new URLSearchParams();
    if (kinds.length === 1) params.set("kind", kinds[0]);
    if (status) params.set("status", status.value);
    if (assignee) params.set("assignee", assignee.value === "me" ? "me" : assignee.value);
    if (reviewer) params.set("reviewer", reviewer.value === "me" ? "me" : reviewer.value);
    if (q) params.set("q", q);
    return params.toString();
  }, [kinds, status, assignee, reviewer, q]);

  // Re-fetch only when the request actually changes: the tree loads the whole
  // filtered set once, so paging its roots must not hit the network again.
  const requestKey = treeMode ? `tree:${filterParams}` : `flat:${filterParams}:${page}`;

  const itemsState = useAsync<ItemsResult>(
    async () => {
      if (treeMode) return loadTreeItems(projectKey, filterParams);
      const params = new URLSearchParams(filterParams);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String((page - 1) * PAGE_SIZE));
      const res = await api.get<WorkItem[]>(`/projects/${projectKey}/work-items?${params}`);
      return {
        items: res.data,
        total: Number(res.meta?.total ?? res.data.length),
        truncated: false,
      };
    },
    [projectKey, requestKey, reloadNonce],
  );

  const tree = useMemo(() => {
    if (!treeMode || !itemsState.data) return null;
    return buildWorkItemTree(itemsState.data.items, collapsed, page, PAGE_SIZE);
  }, [treeMode, itemsState.data, collapsed, page]);

  const toggleKind = (value: string, checked: boolean) => {
    // Zero selected kinds means "all" (only exactly one sends kind=).
    setKinds((prev) => (checked ? [...prev, value] : prev.filter((k) => k !== value)));
    setPage(1);
  };

  const changeView = (next: ViewMode) => {
    if (next === view) return;
    setView(next);
    writeStorage(VIEW_KEY(projectKey), next);
    setPage(1);
  };

  const toggleNode = (item: WorkItem) => {
    const next = new Set(collapsed);
    if (next.has(item.id)) next.delete(item.id);
    else next.add(item.id);
    setCollapsed(next);
    writeStorage(COLLAPSED_KEY(projectKey), JSON.stringify([...next]));
  };

  const openItem = (item: WorkItem) =>
    navigate(`/projects/${projectKey}/items/${item.id}`, {
      state: { from: location.pathname + location.search },
    });

  const items = itemsState.data?.items ?? [];
  const total = itemsState.data?.total ?? 0;
  const flatRows: WorkItemRowView[] = items.map((item) => ({ item }));
  const rows: WorkItemRowView[] = tree ? tree.rows : flatRows;
  const pageCount = tree
    ? tree.pageCount
    : Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Page fill testId="page-backlog">
      <PageHeader
        title="工作项"
        testId="backlog-header"
        actions={
          <>
            <Inline space="space.050" alignBlock="center" testId="work-item-view-switch">
              <Button
                spacing="compact"
                isSelected={view === "flat"}
                aria-pressed={view === "flat"}
                testId="work-item-view-flat"
                onClick={() => changeView("flat")}
              >
                扁平
              </Button>
              <Button
                spacing="compact"
                isSelected={view === "tree"}
                aria-pressed={view === "tree"}
                testId="work-item-view-tree"
                onClick={() => changeView("tree")}
              >
                层级
              </Button>
            </Inline>
            <Button
              appearance="primary"
              testId="work-item-create-button"
              onClick={() => setShowCreate(true)}
            >
              新建
            </Button>
          </>
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
        <Box xcss={pageStyles.filterWidth} testId="work-item-filter-status">
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
        <Box xcss={pageStyles.filterWidth} testId="work-item-filter-assignee">
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
        <Box xcss={pageStyles.filterWidth} testId="work-item-filter-reviewer">
          <Select<Option>
            options={assigneeOptions}
            value={reviewer}
            onChange={(opt) => {
              setReviewer(opt as Option | null);
              setPage(1);
            }}
            isClearable
            spacing="compact"
            placeholder="评审人"
          />
        </Box>
        <Box xcss={pageStyles.searchWidth}>
          <Textfield
            placeholder="搜索标题/评审意见"
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

      <Box xcss={pageStyles.content} testId="backlog-content">
        {itemsState.loading ? (
          <Box xcss={pageStyles.centered} testId="work-item-loading">
            <Spinner size="large" />
          </Box>
        ) : itemsState.error ? (
          <SectionMessage appearance="error" title="加载失败">
            无法获取工作项列表，请调整筛选或刷新页面重试。
          </SectionMessage>
        ) : items.length === 0 ? (
          <Box testId="work-item-empty">
            <EmptyState
              header="没有符合条件的工作项"
              description="调整筛选，或点「新建」创建第一个。"
            />
          </Box>
        ) : (
          <>
            {treeMode && itemsState.data?.truncated && (
              <Box paddingBlockEnd="space.150" testId="work-item-tree-truncated">
                <SectionMessage appearance="warning">
                  层级视图最多加载 {TREE_LIMIT} 条工作项；请缩小筛选范围以查看完整层级。
                </SectionMessage>
              </Box>
            )}
            <WorkItemTable
              rows={rows}
              total={total}
              page={page}
              pageCount={pageCount}
              onOpen={openItem}
              onPageChange={setPage}
              onToggle={treeMode ? toggleNode : undefined}
              countNote={tree ? `${tree.rootCount} 个顶层` : undefined}
            />
          </>
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
