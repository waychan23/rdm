import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import { monitorForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import EmptyState from "@atlaskit/empty-state";
import Spinner from "@atlaskit/spinner";
import { Box, Inline } from "@atlaskit/primitives/compiled";

import { Page, PageHeader } from "../components/Page";
import ErrorState from "../components/ErrorState";
import { api, errorCause } from "../lib/api";
import { statusLabel } from "../lib/labels";
import { useNotify } from "../lib/flags";
import { useRestoreScroll } from "../hooks/useRestoreScroll";
import { useRememberViewScroll } from "../hooks/useRememberViewScroll";
import { useListOrigin, useListSearchParams } from "../lib/originSearch";
import { recall, remember } from "../lib/pageCache";
import { appContentScrollTop, rememberScroll } from "../lib/scrollMemory";
import type { WorkItem, WorkflowDto } from "../types";
import { KIND_VALUES, PAGE_SIZE } from "../workitems/constants";
import { useWorkItemViewMemory } from "../workitems/viewMemory";
import BoardCard from "./board/BoardCard";
import BoardColumn from "./board/BoardColumn";
import CreateWorkItemDialog from "../workitems/CreateWorkItemDialog";
import WorkItemToolbar from "../workitems/WorkItemToolbar";
import {
  applyFilterPatch,
  buildRequestParams,
  DEFAULT_KINDS,
  parseFilters,
  type FilterDefaults,
  type WorkItemFilters,
} from "../workitems/filterState";

interface ColumnState {
  items: WorkItem[];
  /** Unpaginated match count for the column header. */
  total: number;
  loading: boolean;
  loadingMore: boolean;
  error: unknown;
}

type ColumnMap = Record<string, ColumnState>;

interface BoardSnapshot {
  columns: ColumnMap;
  workflow: WorkflowDto;
}

const boardCacheKey = (projectKey: string, requestParams: string) =>
  `board|${projectKey}|${requestParams}`;

const DEFAULT_BOARD_KINDS = DEFAULT_KINDS;

const styles = cssMap({
  // The board itself only scrolls horizontally; every column owns its
  // vertical scrollbar (RDM-58).
  board: {
    display: "flex",
    flexDirection: "column",
    flex: "1",
    minHeight: "0",
    overflowX: "auto",
    overflowY: "hidden",
  },
  boardRow: {
    display: "flex",
    flex: "1",
    minHeight: "0",
    gap: "var(--ds-space-150)",
    alignItems: "stretch",
    width: "max-content",
    minWidth: "100%",
  },
  loading: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flex: "1",
  },
  columnLoading: {
    display: "flex",
    justifyContent: "center",
    paddingBlock: "var(--ds-space-150)",
  },
});

export default function BoardPage() {
  const { t } = useTranslation("projects");
  const { key: projectKey = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const notify = useNotify();
  useRestoreScroll();
  useRememberViewScroll();
  useWorkItemViewMemory(projectKey, "board");

  // Reads the item-drawer origin URL when this page renders as its backdrop.
  const [searchParams, setSearchParams] = useListSearchParams();
  const listOrigin = useListOrigin();
  const defaults: FilterDefaults = { kinds: DEFAULT_BOARD_KINDS, rootOnly: true };
  const filters: WorkItemFilters = parseFilters(searchParams, defaults);
  const filterParams = buildRequestParams(filters).toString();
  const cacheKey = boardCacheKey(projectKey, filterParams);
  const kindsKey = filters.kinds.join(",");
  const kinds = useMemo(
    () => (kindsKey ? kindsKey.split(",") : [...KIND_VALUES]),
    [kindsKey],
  );
  const patchFilters = (patch: Partial<WorkItemFilters>) => {
    setSearchParams(applyFilterPatch(searchParams, patch, defaults), { replace: true });
  };

  const [showCreate, setShowCreate] = useState(false);
  const initialSnapshot = recall<BoardSnapshot>(cacheKey);
  const [columns, setColumns] = useState<ColumnMap>(initialSnapshot?.columns ?? {});
  // Cache key the current `columns` belong to (guards the snapshot write).
  const [columnsKey, setColumnsKey] = useState(cacheKey);
  const [workflow, setWorkflow] = useState<WorkflowDto | null>(
    initialSnapshot?.workflow ?? null,
  );
  const [workflowError, setWorkflowError] = useState<unknown>(null);
  const [workflowNonce, setWorkflowNonce] = useState(0);

  // Latest values for the (mount-once) drop monitor and load-more handlers.
  const stateRef = useRef({ columns, workflow, filterParams, projectKey });
  stateRef.current = { columns, workflow, filterParams, projectKey };
  // Bumped on every filter change so stale column responses are dropped.
  const generationRef = useRef(0);

  useEffect(() => {
    let alive = true;
    api
      .get<WorkflowDto>(`/workflow?project=${encodeURIComponent(projectKey)}`)
      .then((res) => {
        if (alive) {
          setWorkflow(res.data);
          setWorkflowError(null);
        }
      })
      .catch((e) => {
        if (alive) setWorkflowError(e);
      });
    return () => {
      alive = false;
    };
  }, [projectKey, workflowNonce]);

  // Columns are the merged state list of every selected kind (first kind
  // first, duplicates collapsed). Terminal columns are always shown (RDM-63).
  const statuses = useMemo(() => {
    if (!workflow) return [];
    const out: string[] = [];
    for (const kind of kinds) {
      const spec = workflow.kinds[kind];
      if (!spec) continue;
      const subtypes = Object.values(spec.subtypes ?? {});
      const collected =
        subtypes.length > 0
          ? [...spec.states, ...subtypes.flatMap((subtype) => subtype.states)]
          : spec.states;
      for (const state of collected) {
        if (!out.includes(state)) out.push(state);
      }
    }
    return out;
    // kindsKey stands in for the kinds array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow, kindsKey]);

  const loadColumn = useCallback(
    async (status: string, offset: number, generation: number, silent = false) => {
      const params = new URLSearchParams(stateRef.current.filterParams);
      params.set("status", status);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));
      setColumns((prev) => {
        const current = prev[status];
        if (!current) return prev;
        return {
          ...prev,
          [status]: {
            ...current,
            loading: !silent && offset === 0,
            loadingMore: !silent && offset > 0,
            error: null,
          },
        };
      });
      try {
        const res = await api.get<WorkItem[]>(
          `/projects/${projectKey}/work-items?${params.toString()}`,
        );
        if (generationRef.current !== generation) return;
        const total = Number(res.meta?.total ?? res.data.length);
        setColumns((prev) => {
          const current = prev[status];
          if (!current) return prev;
          const items =
            offset === 0
              ? res.data
              : [
                  ...current.items,
                  ...res.data.filter(
                    (item) => !current.items.some((existing) => existing.id === item.id),
                  ),
                ];
          return {
            ...prev,
            [status]: { items, total, loading: false, loadingMore: false, error: null },
          };
        });
      } catch (e) {
        if (generationRef.current !== generation) return;
        setColumns((prev) => {
          const current = prev[status];
          if (!current) return prev;
          return {
            ...prev,
            [status]: { ...current, loading: false, loadingMore: false, error: e },
          };
        });
      }
    },
    [projectKey],
  );

  // Reset/populate the columns whenever the filter request or workflow
  // changes, then revalidate the first page of every column.
  useEffect(() => {
    if (!workflow) return;
    const generation = ++generationRef.current;
    const snapshot = recall<BoardSnapshot>(cacheKey);
    const next: ColumnMap = {};
    for (const status of statuses) {
      next[status] =
        snapshot?.columns[status] ?? {
          items: [],
          total: 0,
          loading: true,
          loadingMore: false,
          error: null,
        };
    }
    setColumns(next);
    setColumnsKey(cacheKey);
    const hasSnapshot = snapshot !== null;
    for (const status of statuses) {
      void loadColumn(status, 0, generation, hasSnapshot);
    }
    // statuses is derived from workflow + kindsKey.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, workflow, kindsKey, loadColumn]);

  // Persist fully-settled columns so reopening the board behind the item
  // drawer renders immediately instead of remounting into a spinner.
  const statusesJoined = statuses.join(",");
  useEffect(() => {
    // Only persist columns that were loaded for this request; when the filter
    // just changed, `columns` still holds the previous request's data.
    if (!workflow || statuses.length === 0 || columnsKey !== cacheKey) return;
    const settled = statuses.every((status) => {
      const column = columns[status];
      return column && !column.loading && !column.loadingMore;
    });
    if (settled) remember(cacheKey, { columns, workflow });
    // statusesJoined stands in for the statuses identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columns, columnsKey, workflow, cacheKey, statusesJoined]);

  const refreshAll = useCallback(() => {
    const generation = generationRef.current;
    statuses.forEach((status) => void loadColumn(status, 0, generation, true));
    // statusesJoined stands in for the statuses identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadColumn, statusesJoined]);

  const loadMore = useCallback(
    (status: string) => {
      const current = stateRef.current.columns[status];
      if (
        !current ||
        current.loading ||
        current.loadingMore ||
        current.items.length >= current.total
      ) {
        return;
      }
      void loadColumn(status, current.items.length, generationRef.current);
    },
    [loadColumn],
  );

  const handleDrop = useCallback(
    async (itemId: string, target: string) => {
      const { columns: current, workflow: wf } = stateRef.current;
      const item = Object.values(current)
        .flatMap((column) => column.items)
        .find((candidate) => candidate.id === itemId);
      if (!item || item.status === target) return;
      const base = wf?.kinds[item.kind];
      const spec =
        item.kind === "task" && item.task_type
          ? base?.subtypes?.[item.task_type] ?? base
          : base;
      const matching = (spec?.steps?.[item.status] ?? []).filter(
        (step) => step.to === target,
      );
      const step = matching.length === 1 ? matching[0] : undefined;
      const direct =
        step !== undefined &&
        step.mode === "direct" &&
        step.note === "optional" &&
        Object.keys(step.gates ?? {}).length === 0;
      if (!direct) {
        notify.error(
          t("board.stepRequiredTitle"),
          t("board.stepRequiredBody", {
            id: item.display_id,
            from: statusLabel(item.status),
            to: statusLabel(target),
          }),
        );
        return;
      }
      const previous = item.status;
      const generation = generationRef.current;
      // Optimistic move between the two column buckets.
      setColumns((prev) => {
        const next = { ...prev };
        const source = next[previous];
        if (source) {
          next[previous] = {
            ...source,
            items: source.items.filter((candidate) => candidate.id !== item.id),
            total: Math.max(0, source.total - 1),
          };
        }
        const destination = next[target];
        if (destination) {
          next[target] = {
            ...destination,
            items: [{ ...item, status: target }, ...destination.items],
            total: destination.total + 1,
          };
        }
        return next;
      });
      try {
        await api.post(`/work-items/${item.display_id}/steps/${step.key}`, {
          row_version: item.row_version,
          note_md: null,
        });
        notify.success(`${item.display_id} → ${target}`);
        void loadColumn(previous, 0, generation, true);
        void loadColumn(target, 0, generation, true);
      } catch (e) {
        void loadColumn(previous, 0, generation, true);
        void loadColumn(target, 0, generation, true);
        const cause = errorCause(e);
        // Engine emits display-id strings in details.blocking_children.
        const blocking = ((cause?.details?.blocking_children as unknown) as
          | string[]
          | undefined)
          ?.filter(Boolean)
          .join(", ");
        notify.error(
          t("board.transitionFailed"),
          blocking
            ? t("board.transitionFailedBlocking", { message: cause?.message, blocking })
            : cause?.message,
        );
      }
    },
    [loadColumn, notify, t],
  );

  useEffect(() => {
    return monitorForElements({
      onDrop({ source, location }) {
        const target = location.current.dropTargets[0]?.data as
          | { status?: string }
          | undefined;
        const src = source.data as { itemId?: string };
        if (target?.status && src.itemId) void handleDrop(src.itemId, target.status);
      },
    });
  }, [handleDrop]);

  // Surface a single board-level error when every column's first page failed.
  const firstColumnError = statuses
    .map((status) => columns[status]?.error)
    .find((error) => Boolean(error));
  const allColumnsFailed =
    statuses.length > 0 &&
    statuses.every((status) => {
      const column = columns[status];
      return column?.error && column.items.length === 0;
    });

  const openItem = (item: WorkItem) => {
    // From the drawer backdrop the board URL (not the item route) is the origin.
    const from = listOrigin ?? location.pathname + location.search;
    if (!from.includes("/items/")) rememberScroll(from, appContentScrollTop());
    navigate(`/projects/${projectKey}/items/${item.id}`, { state: { from } });
  };

  return (
    <Page fill testId="page-board">
      <PageHeader title={t("board.title")} testId="board-header" />

      <WorkItemToolbar
        projectKey={projectKey}
        filters={filters}
        workflow={workflow}
        onFilterChange={patchFilters}
        onCreate={() => setShowCreate(true)}
        onRefresh={refreshAll}
      />

      <Box xcss={styles.board} testId="board-columns">
        {workflowError || (allColumnsFailed && firstColumnError) ? (
          <ErrorState
            error={workflowError ?? firstColumnError}
            onRetry={() => {
              if (workflowError) setWorkflowNonce((nonce) => nonce + 1);
              else refreshAll();
            }}
            testId="board-error"
          />
        ) : !workflow || statuses.length === 0 ? (
          <Box xcss={styles.loading} testId="board-loading">
            {workflow ? <EmptyState header={t("board.empty")} /> : <Spinner size="large" />}
          </Box>
        ) : (
          <Box xcss={styles.boardRow}>
            {statuses.map((status) => {
              const column = columns[status];
              const items = column?.items ?? [];
              return (
                <BoardColumn
                  key={status}
                  status={status}
                  scrollKey={`${projectKey}|${filterParams}|${status}`}
                  count={column?.total ?? 0}
                  hasMore={items.length < (column?.total ?? 0)}
                  loadingMore={column?.loadingMore ?? false}
                  loadFailed={Boolean(column?.error)}
                  onLoadMore={() => loadMore(status)}
                >
                  {column?.loading && items.length === 0 ? (
                    <Inline alignBlock="center" xcss={styles.columnLoading}>
                      <Spinner size="small" />
                    </Inline>
                  ) : (
                    items.map((item) => (
                      <BoardCard key={item.id} item={item} onOpen={openItem} />
                    ))
                  )}
                </BoardColumn>
              );
            })}
          </Box>
        )}
      </Box>

      <CreateWorkItemDialog
        open={showCreate}
        projectKey={projectKey}
        onClose={() => setShowCreate(false)}
        onCreated={(item) => {
          refreshAll();
          openItem(item);
        }}
      />
    </Page>
  );
}
