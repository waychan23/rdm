import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import { monitorForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Text } from "@atlaskit/primitives/compiled";

import { Page, PageHeader } from "../components/Page";
import ErrorState from "../components/ErrorState";
import TextButton from "../components/TextButton";
import { api, errorCause } from "../lib/api";
import { statusLabel } from "../lib/labels";
import { useNotify } from "../lib/flags";
import { useRestoreScroll } from "../hooks/useRestoreScroll";
import { useListOrigin, useListSearchParams } from "../lib/originSearch";
import { recall, remember } from "../lib/pageCache";
import { appContentScrollTop, rememberScroll } from "../lib/scrollMemory";
import { portalMenuProps } from "../lib/portalMenu";
import type { Sprint, WorkItem, WorkflowDto } from "../types";
import { KIND_VALUES, kindOptions } from "../workitems/constants";
import BoardCard from "./board/BoardCard";
import BoardColumn from "./board/BoardColumn";
import SprintDetailDrawer from "./sprints/SprintDetailDrawer";
import { sprintLozenge } from "./sprints/sprintStatus";

interface BoardSnapshot {
  items: WorkItem[];
  workflow: WorkflowDto;
}

const boardCacheKey = (projectKey: string, kinds: string, sprint: string) =>
  `board|${projectKey}|${kinds}|${sprint}`;

const DEFAULT_BOARD_KINDS = ["story", "issue", "task"];

function parseKinds(value: string | null): string[] {
  if (!value) return [...DEFAULT_BOARD_KINDS];
  const known = KIND_VALUES as readonly string[];
  return value.split(",").filter((kind) => known.includes(kind));
}

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
  sprintFilter: {
    width: "180px",
  },
  kindFilter: {
    width: "260px",
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
  const kinds = parseKinds(searchParams.get("kind"));
  const kindsValue = kinds.join(",");
  const sprint = searchParams.get("sprint") ?? "";
  const showTerminal = searchParams.get("showTerminal") !== "false";
  const rootOnly = searchParams.get("rootOnly") !== "false";
  const setKinds = (next: string[]) => {
    const params = new URLSearchParams(searchParams);
    const ordered = KIND_VALUES.filter((kind) => next.includes(kind));
    if (ordered.join(",") === DEFAULT_BOARD_KINDS.join(",")) params.delete("kind");
    else params.set("kind", ordered.join(","));
    setSearchParams(params, { replace: true });
  };
  const setSprint = (next: string | null) => {
    const params = new URLSearchParams(searchParams);
    if (next) params.set("sprint", next);
    else params.delete("sprint");
    setSearchParams(params, { replace: true });
  };
  const setShowTerminal = (next: boolean) => {
    const params = new URLSearchParams(searchParams);
    if (next) params.delete("showTerminal");
    else params.set("showTerminal", "false");
    setSearchParams(params, { replace: true });
  };
  const setRootOnly = (next: boolean) => {
    const params = new URLSearchParams(searchParams);
    if (next) params.delete("rootOnly");
    else params.set("rootOnly", "false");
    setSearchParams(params, { replace: true });
  };
  const [sprintDrawerOpen, setSprintDrawerOpen] = useState(false);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  useEffect(() => {
    let alive = true;
    api
      .get<Sprint[]>(`/projects/${projectKey}/sprints`)
      .then((res) => {
        if (alive) setSprints(res.data);
      })
      .catch(() => {
        // The filter stays empty; the board itself still works unfiltered.
      });
    return () => {
      alive = false;
    };
  }, [projectKey]);
  const initialSnapshot = recall<BoardSnapshot>(boardCacheKey(projectKey, kindsValue, sprint));
  const [items, setItems] = useState<WorkItem[]>(initialSnapshot?.items ?? []);
  const [workflow, setWorkflow] = useState<WorkflowDto | null>(
    initialSnapshot?.workflow ?? null,
  );
  const [loading, setLoading] = useState(!initialSnapshot);
  const [error, setError] = useState<unknown>(null);

  // Latest values for the (mount-once) drop monitor.
  const stateRef = useRef({ items, workflow, kinds: kindsValue, sprint, projectKey });
  stateRef.current = { items, workflow, kinds: kindsValue, sprint, projectKey };

  const load = useCallback(
    async (nextKinds: string, nextSprint: string, initial = false) => {
      const cacheKey = boardCacheKey(projectKey, nextKinds, nextSprint);
      const snapshot = initial ? recall<BoardSnapshot>(cacheKey) : undefined;
      if (snapshot) {
        setWorkflow(snapshot.workflow);
        setItems(snapshot.items);
      }
      setLoading(initial ? !snapshot : true);
      setError(null);
      try {
        const params = new URLSearchParams({ kind: nextKinds, limit: "200" });
        if (nextSprint) params.set("sprint", nextSprint);
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
    if (kinds.length === 0) {
      setItems([]);
      return;
    }
    load(kindsValue, sprint, true);
    // load identity is stable; reload when the kind/sprint filters change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kindsValue, sprint]);

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
        await load(stateRef.current.kinds, stateRef.current.sprint);
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
  // their shared status names.
  const columns = useMemo(() => {
    if (!workflow) return [];
    const states: string[] = [];
    const terminal = new Set<string>();
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
      spec.terminal.forEach((state) => terminal.add(state));
      subtypes.forEach((subtype) =>
        subtype.terminal.forEach((state) => terminal.add(state)),
      );
    }
    const visible = states.filter((state) => showTerminal || !terminal.has(state));
    const visibleItems = rootOnly ? items.filter((item) => !item.parent_id) : items;
    return visible.map((status) => ({
      status,
      items: visibleItems.filter((item) => item.status === status),
    }));
  }, [workflow, kindsValue, showTerminal, items, rootOnly]);

  const sprintOptions = useMemo(
    () => sprints.map((s) => ({ label: s.name, value: s.id })),
    [sprints],
  );
  const activeSprint = useMemo(
    () => sprints.find((s) => s.id === sprint) ?? null,
    [sprints, sprint],
  );

  const openItem = (item: WorkItem) => {
    // From the drawer backdrop the board URL (not the item route) is the origin.
    const from = listOrigin ?? location.pathname + location.search;
    if (!from.includes("/items/")) rememberScroll(from, appContentScrollTop());
    navigate(`/projects/${projectKey}/items/${item.id}`, { state: { from } });
  };

  return (
    <Page fill testId="page-board">
      <PageHeader
        title={t("board.title")}
        testId="board-header"
        actions={
          <Inline space="space.100" alignBlock="center">
            <Box xcss={styles.sprintFilter} testId="board-sprint-filter">
              <Select<{ label: string; value: string }>
                {...portalMenuProps}
                options={sprintOptions}
                value={sprintOptions.find((o) => o.value === sprint) ?? null}
                onChange={(opt) => setSprint((opt as { value: string } | null)?.value ?? null)}
                isClearable
                spacing="compact"
                placeholder={t("board.sprintFilter")}
                testId="board-sprint-select"
              />
            </Box>
            <Box xcss={styles.kindFilter} testId="board-kind-filter">
              <Select<{ label: string; value: string }, true>
                {...portalMenuProps}
                isMulti
                // Filter-style multi-select: selected kinds stay in the menu
                // so they can be toggled off there, not only via the chips.
                hideSelectedOptions={false}
                options={kindOptions()}
                value={kindOptions().filter((option) => kinds.includes(option.value))}
                onChange={(options) => setKinds(options.map((option) => option.value))}
                spacing="compact"
                placeholder={t("board.kindFilter")}
                testId="board-kind-select"
              />
            </Box>
            <Checkbox
              label={t("board.rootOnly")}
              isChecked={rootOnly}
              testId="board-root-only"
              onChange={(e) => setRootOnly(e.currentTarget.checked)}
            />
            <Checkbox
              label={t("board.showTerminal")}
              isChecked={showTerminal}
              testId="board-show-terminal"
              onChange={(e) => setShowTerminal(e.currentTarget.checked)}
            />
          </Inline>
        }
      />

      {activeSprint && (
        <Inline space="space.150" alignBlock="center" testId="board-sprint-info">
          <TextButton data-testid="board-sprint-open" onClick={() => setSprintDrawerOpen(true)}>
            {activeSprint.name}
          </TextButton>
          <Text size="small" color="color.text.subtle">
            {t("board.sprintDates", {
              start: activeSprint.start_date ?? "—",
              end: activeSprint.end_date ?? "—",
            })}
          </Text>
          {sprintLozenge(activeSprint.status)}
        </Inline>
      )}

      <Box xcss={styles.board} testId="board-columns">
        {error ? (
          <ErrorState
            error={error}
            onRetry={() => load(kindsValue, sprint, true)}
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

      <SprintDetailDrawer
        projectKey={projectKey}
        sprintId={sprintDrawerOpen ? sprint || null : null}
        onClose={() => setSprintDrawerOpen(false)}
        onChanged={() => void load(kindsValue, sprint)}
      />
    </Page>
  );
}
