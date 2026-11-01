import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import { monitorForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import EmptyState from "@atlaskit/empty-state";
import Spinner from "@atlaskit/spinner";
import { Box } from "@atlaskit/primitives/compiled";

import { Page, PageHeader } from "../components/Page";
import ErrorState from "../components/ErrorState";
import { api, errorCause } from "../lib/api";
import { statusLabel } from "../lib/labels";
import { useNotify } from "../lib/flags";
import { useRestoreScroll } from "../hooks/useRestoreScroll";
import { useListOrigin, useListSearchParams } from "../lib/originSearch";
import { recall, remember } from "../lib/pageCache";
import { appContentScrollTop, rememberScroll } from "../lib/scrollMemory";
import type { WorkItem, WorkflowDto } from "../types";
import { KIND_VALUES } from "../workitems/constants";
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

interface BoardSnapshot {
  items: WorkItem[];
  workflow: WorkflowDto;
}

const boardCacheKey = (projectKey: string, requestParams: string) =>
  `board|${projectKey}|${requestParams}`;

const DEFAULT_BOARD_KINDS = DEFAULT_KINDS;

const styles = cssMap({
  // Scroll container. The board row inside grows with its tallest column, so
  // the whole board scrolls vertically while every column keeps an equal,
  // content-following height (see boardRow).
  board: {
    display: "flex",
    flexDirection: "column",
    flex: "1",
    minHeight: "0",
    overflow: "auto",
  },
  // `flex: 1 0 auto` fills the viewport when columns are short, and lets the
  // row (so: every stretched column's grey background) grow with the tallest
  // column when its cards overflow. Column widths stay fixed, so the row is
  // max-content wide and the scroll container handles horizontal overflow.
  boardRow: {
    display: "flex",
    flex: "1 0 auto",
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
});

export default function BoardPage() {
  const { t } = useTranslation("projects");
  const { key: projectKey = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const notify = useNotify();
  useRestoreScroll();

  // Reads the item-drawer origin URL when this page renders as its backdrop.
  const [searchParams, setSearchParams] = useListSearchParams();
  const listOrigin = useListOrigin();
  const defaults: FilterDefaults = { kinds: DEFAULT_BOARD_KINDS, rootOnly: true };
  const filters: WorkItemFilters = parseFilters(searchParams, defaults);
  const filterParams = buildRequestParams(filters).toString();
  const kinds = filters.kinds.length > 0 ? filters.kinds : [...KIND_VALUES];
  const kindsKey = kinds.join(",");

  const patchFilters = (patch: Partial<WorkItemFilters>) => {
    setSearchParams(applyFilterPatch(searchParams, patch, defaults), { replace: true });
  };

  const [showCreate, setShowCreate] = useState(false);
  const initialSnapshot = recall<BoardSnapshot>(boardCacheKey(projectKey, filterParams));
  const [items, setItems] = useState<WorkItem[]>(initialSnapshot?.items ?? []);
  const [workflow, setWorkflow] = useState<WorkflowDto | null>(
    initialSnapshot?.workflow ?? null,
  );
  const [loading, setLoading] = useState(!initialSnapshot);
  const [error, setError] = useState<unknown>(null);

  // Latest values for the (mount-once) drop monitor.
  const stateRef = useRef({ items, workflow, filterParams, projectKey });
  stateRef.current = { items, workflow, filterParams, projectKey };

  const load = useCallback(
    async (nextParams: string, initial = false) => {
      const cacheKey = boardCacheKey(projectKey, nextParams);
      const snapshot = initial ? recall<BoardSnapshot>(cacheKey) : undefined;
      if (snapshot) {
        setWorkflow(snapshot.workflow);
        setItems(snapshot.items);
      }
      setLoading(initial ? !snapshot : true);
      setError(null);
      try {
        const params = new URLSearchParams(nextParams);
        params.set("limit", "200");
        const [wf, list] = await Promise.all([
          initial || !stateRef.current.workflow
            ? api.get<WorkflowDto>("/workflow")
            : Promise.resolve({ data: stateRef.current.workflow! }),
          api.get<WorkItem[]>(
            `/projects/${projectKey}/work-items?${params.toString()}`,
          ),
        ]);
        setWorkflow(wf.data);
        setItems(list.data);
        remember(cacheKey, { items: list.data, workflow: wf.data });
      } catch (e) {
        setError(e);
      } finally {
        setLoading(false);
      }
    },
    [projectKey],
  );

  useEffect(() => {
    load(filterParams, true);
    // load identity is stable; reload when the filter/sort request changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterParams]);

  const handleDrop = useCallback(
    async (itemId: string, target: string) => {
      const { items: current, workflow: wf } = stateRef.current;
      const item = current.find((i) => i.id === itemId);
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
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, status: target } : i)),
      );
      try {
        await api.post(`/work-items/${item.display_id}/steps/${step.key}`, {
          row_version: item.row_version,
          note_md: null,
        });
        notify.success(`${item.display_id} → ${target}`);
        await load(stateRef.current.filterParams);
      } catch (e) {
        setItems((prev) =>
          prev.map((i) => (i.id === item.id ? { ...i, status: previous } : i)),
        );
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
    [load, notify, t],
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

  // Columns are the merged state list of every selected kind (first kind
  // first, duplicates collapsed), so a multi-kind board lines items up by
  // their shared status names. Terminal columns are always shown (RDM-63).
  const columns = useMemo(() => {
    if (!workflow) return [];
    const states: string[] = [];
    for (const kind of kinds) {
      const spec = workflow.kinds[kind];
      if (!spec) continue;
      const subtypes = Object.values(spec.subtypes ?? {});
      const collected =
        subtypes.length > 0
          ? [...spec.states, ...subtypes.flatMap((subtype) => subtype.states)]
          : spec.states;
      for (const state of collected) {
        if (!states.includes(state)) states.push(state);
      }
    }
    return states.map((status) => ({
      status,
      items: items.filter((item) => item.status === status),
    }));
  }, [workflow, kindsKey, items]);

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
        onRefresh={() => load(filterParams)}
      />

      <Box xcss={styles.board} testId="board-columns">
        {error ? (
          <ErrorState
            error={error}
            onRetry={() => load(filterParams, true)}
            testId="board-error"
          />
        ) : loading ? (
          <Box xcss={styles.loading} testId="board-loading">
            <Spinner size="large" />
          </Box>
        ) : columns.length === 0 ? (
          <EmptyState header={t("board.empty")} />
        ) : (
          <Box xcss={styles.boardRow}>
            {columns.map((col) => (
              <BoardColumn key={col.status} status={col.status} count={col.items.length}>
                {col.items.length === 0 ? null : (
                  col.items.map((item) => (
                    <BoardCard key={item.id} item={item} onOpen={openItem} />
                  ))
                )}
              </BoardColumn>
            ))}
          </Box>
        )}
      </Box>

      <CreateWorkItemDialog
        open={showCreate}
        projectKey={projectKey}
        onClose={() => setShowCreate(false)}
        onCreated={(item) => {
          void load(filterParams);
          openItem(item);
        }}
      />
    </Page>
  );
}
