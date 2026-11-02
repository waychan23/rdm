import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import EmptyState from "@atlaskit/empty-state";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import { Box } from "@atlaskit/primitives/compiled";

import { Page, PageHeader } from "../components/Page";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useRestoreScroll } from "../hooks/useRestoreScroll";
import { useRememberViewScroll } from "../hooks/useRememberViewScroll";
import {
  useListOrigin,
  useListProjectKey,
  useListSearchParams,
} from "../lib/originSearch";
import { recall, remember } from "../lib/pageCache";
import { appContentScrollTop, rememberScroll } from "../lib/scrollMemory";
import type { WorkItem, WorkflowDto } from "../types";
import { PAGE_SIZE } from "../workitems/constants";
import { buildWorkItemTree } from "../workitems/hierarchy";
import { useWorkItemViewMemory } from "../workitems/viewMemory";
import WorkItemTable, { type WorkItemRowView } from "../workitems/WorkItemTable";
import CreateWorkItemDialog from "../workitems/CreateWorkItemDialog";
import WorkItemToolbar, { type WorkItemView } from "../workitems/WorkItemToolbar";
import {
  applyFilterPatch,
  buildRequestParams,
  DEFAULT_KINDS,
  parseFilters,
  type FilterDefaults,
  type WorkItemFilters,
} from "../workitems/filterState";

/** The tree view needs every filtered item to nest children under parents. */
const TREE_BATCH = 100;
const TREE_LIMIT = 1000;

const VIEW_KEY = (projectKey: string) => `rdm.work-items.view.${projectKey}`;
const COLLAPSED_KEY = (projectKey: string) => `rdm.work-items.collapsed.${projectKey}`;

function readView(projectKey: string): WorkItemView {
  try {
    return localStorage.getItem(VIEW_KEY(projectKey)) === "flat" ? "flat" : "tree";
  } catch {
    return "tree";
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
  const { key: routeKey = "RDM" } = useParams();
  // The origin URL owns the project while this page is a drawer backdrop.
  const projectKey = useListProjectKey(routeKey);
  // Remount per project so the stored view/collapse preferences are re-read
  // when switching projects without a full remount of the route.
  return <BacklogView key={projectKey} projectKey={projectKey} />;
}

function BacklogView({ projectKey }: { projectKey: string }) {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const location = useLocation();
  // Reads the item-drawer origin URL when this page renders as its backdrop.
  const [searchParams, setSearchParams] = useListSearchParams();
  const listOrigin = useListOrigin();
  useRestoreScroll();
  useRememberViewScroll();

  // `/issues` is the same list pinned to the issue kind, with the kind filter
  // hidden (sidebar "缺陷" entry).
  const pagePath = listOrigin ? listOrigin.split("?")[0] : location.pathname;
  const issuesOnly = pagePath.endsWith("/issues");
  useWorkItemViewMemory(projectKey, issuesOnly ? "issues" : "backlog");
  const defaults: FilterDefaults = {
    kinds: issuesOnly ? ["issue"] : DEFAULT_KINDS,
    rootOnly: false,
  };
  const parsedFilters = parseFilters(searchParams, defaults);
  // The /issues route owns the kind regardless of a stale URL parameter.
  const filters: WorkItemFilters = issuesOnly
    ? { ...parsedFilters, kinds: ["issue"] }
    : parsedFilters;

  const view: WorkItemView =
    searchParams.get("view") === "flat"
      ? "flat"
      : searchParams.get("view") === "tree"
        ? "tree"
        : readView(projectKey);
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const [showCreate, setShowCreate] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => readCollapsed(projectKey));
  const treeMode = view === "tree";

  const patchParams = (patch: Record<string, string | null>, resetPage = true) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    if (resetPage && !("page" in patch)) next.delete("page");
    setSearchParams(next, { replace: true });
  };

  const patchFilters = (patch: Partial<WorkItemFilters>) => {
    setSearchParams(applyFilterPatch(searchParams, patch, defaults), { replace: true });
  };

  const workflowState = useAsync<WorkflowDto>(
    async () => (await api.get<WorkflowDto>(`/workflow?project=${encodeURIComponent(projectKey)}`)).data,
    [projectKey],
  );

  const filterParams = buildRequestParams(filters).toString();

  // Re-fetch only when the request actually changes: the tree loads the whole
  // filtered set once, so paging its roots must not hit the network again.
  const requestKey = treeMode ? `tree:${filterParams}` : `flat:${filterParams}:${page}`;
  // Keep the last rendered page per request so opening/closing the work-item
  // overlay does not remount the list into a spinner.
  const cacheKey = `${projectKey}|${requestKey}`;
  const cachedItems = recall<ItemsResult>(cacheKey);

  const itemsState = useAsync<ItemsResult>(
    async () => {
      let result: ItemsResult;
      if (treeMode) {
        result = await loadTreeItems(projectKey, filterParams);
      } else {
        const params = new URLSearchParams(filterParams);
        params.set("limit", String(PAGE_SIZE));
        params.set("offset", String((page - 1) * PAGE_SIZE));
        const res = await api.get<WorkItem[]>(`/projects/${projectKey}/work-items?${params}`);
        result = {
          items: res.data,
          total: Number(res.meta?.total ?? res.data.length),
          truncated: false,
        };
      }
      remember(cacheKey, result);
      return result;
    },
    [projectKey, requestKey, reloadNonce],
  );

  const itemsData = itemsState.data ?? cachedItems;
  const listLoading = itemsState.loading && !itemsData;

  const tree = useMemo(() => {
    if (!treeMode || !itemsData) return null;
    return buildWorkItemTree(itemsData.items, collapsed, page, PAGE_SIZE);
  }, [treeMode, itemsData, collapsed, page]);

  const changeView = (next: WorkItemView) => {
    if (next === view) return;
    writeStorage(VIEW_KEY(projectKey), next);
    patchParams({ view: next });
  };

  const toggleNode = (item: WorkItem) => {
    const next = new Set(collapsed);
    if (next.has(item.id)) next.delete(item.id);
    else next.add(item.id);
    setCollapsed(next);
    writeStorage(COLLAPSED_KEY(projectKey), JSON.stringify([...next]));
  };

  const openItem = (item: WorkItem) => {
    // From the drawer backdrop the list URL (not the item route) is the origin.
    const from = listOrigin ?? location.pathname + location.search;
    // The backdrop copy receives the item path; only a real list route owns
    // the shell scroll position.
    if (!from.includes("/items/")) rememberScroll(from, appContentScrollTop());
    navigate(`/projects/${projectKey}/items/${item.id}`, { state: { from } });
  };

  const items = itemsData?.items ?? [];
  const total = itemsData?.total ?? 0;
  const flatRows: WorkItemRowView[] = items.map((item) => ({ item }));
  const rows: WorkItemRowView[] = tree ? tree.rows : flatRows;
  const pageCount = tree
    ? tree.pageCount
    : Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Page fill testId="page-backlog">
      <PageHeader
        title={issuesOnly ? t("issues.title") : t("backlog.title")}
        testId="backlog-header"
      />

      <WorkItemToolbar
        projectKey={projectKey}
        filters={filters}
        workflow={workflowState.data}
        onFilterChange={patchFilters}
        kindFixed={issuesOnly}
        view={view}
        onViewChange={changeView}
        onCreate={() => setShowCreate(true)}
        onRefresh={() => setReloadNonce((n) => n + 1)}
      />

      <Box xcss={pageStyles.content} testId="backlog-content">
        {listLoading ? (
          <Box xcss={pageStyles.centered} testId="work-item-loading">
            <Spinner size="large" />
          </Box>
        ) : itemsState.error ? (
          <SectionMessage appearance="error" title={t("backlog.loadFailed")}>
            {t("backlog.loadFailedDescription")}
          </SectionMessage>
        ) : items.length === 0 ? (
          <Box testId="work-item-empty">
            <EmptyState
              header={t("backlog.empty")}
              description={t("backlog.emptyDescription")}
            />
          </Box>
        ) : (
          <>
            {treeMode && itemsData?.truncated && (
              <Box paddingBlockEnd="space.150" testId="work-item-tree-truncated">
                <SectionMessage appearance="warning">
                  {t("backlog.treeTruncated", { limit: TREE_LIMIT })}
                </SectionMessage>
              </Box>
            )}
            <WorkItemTable
              rows={rows}
              total={total}
              page={page}
              pageCount={pageCount}
              onOpen={openItem}
              onPageChange={(p) => patchParams({ page: String(p) }, false)}
              onToggle={treeMode ? toggleNode : undefined}
              countNote={tree ? t("backlog.rootCount", { n: tree.rootCount }) : undefined}
              order={filters.order}
              onOrderChange={(next) => patchFilters({ order: next })}
            />
          </>
        )}
      </Box>

      <CreateWorkItemDialog
        open={showCreate}
        projectKey={projectKey}
        allowedKinds={issuesOnly ? ["issue"] : undefined}
        onClose={() => setShowCreate(false)}
        onCreated={(item) => {
          setReloadNonce((n) => n + 1);
          patchParams({ page: null });
          openItem(item);
        }}
      />
    </Page>
  );
}
