import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import { monitorForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
import Spinner from "@atlaskit/spinner";
import { Box, Inline } from "@atlaskit/primitives/compiled";

import { Page, PageHeader } from "../components/Page";
import ErrorState from "../components/ErrorState";
import { api, errorCause } from "../lib/api";
import { statusLabel } from "../lib/labels";
import { useNotify } from "../lib/flags";
import { useRestoreScroll } from "../hooks/useRestoreScroll";
import { recall, remember } from "../lib/pageCache";
import { appContentScrollTop, rememberScroll } from "../lib/scrollMemory";
import type { WorkItem, WorkflowDto } from "../types";
import { kindOptions } from "../workitems/constants";
import BoardCard from "./board/BoardCard";
import BoardColumn from "./board/BoardColumn";

interface BoardSnapshot {
  items: WorkItem[];
  workflow: WorkflowDto;
}

const boardCacheKey = (projectKey: string, kind: string) => `board|${projectKey}|${kind}`;

const styles = cssMap({
  board: {
    display: "flex",
    flex: "1",
    minHeight: "0",
    gap: "var(--ds-space-150)",
    overflowX: "auto",
    alignItems: "stretch",
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

  const [searchParams, setSearchParams] = useSearchParams();
  const kind = searchParams.get("kind") ?? "task";
  const showTerminal = searchParams.get("showTerminal") !== "false";
  const setKind = (next: string) => {
    const params = new URLSearchParams(searchParams);
    if (next === "task") params.delete("kind");
    else params.set("kind", next);
    setSearchParams(params, { replace: true });
  };
  const setShowTerminal = (next: boolean) => {
    const params = new URLSearchParams(searchParams);
    if (next) params.delete("showTerminal");
    else params.set("showTerminal", "false");
    setSearchParams(params, { replace: true });
  };
  const initialSnapshot = recall<BoardSnapshot>(boardCacheKey(projectKey, kind));
  const [items, setItems] = useState<WorkItem[]>(initialSnapshot?.items ?? []);
  const [workflow, setWorkflow] = useState<WorkflowDto | null>(
    initialSnapshot?.workflow ?? null,
  );
  const [loading, setLoading] = useState(!initialSnapshot);
  const [error, setError] = useState<unknown>(null);

  // Latest values for the (mount-once) drop monitor.
  const stateRef = useRef({ items, workflow, kind, projectKey });
  stateRef.current = { items, workflow, kind, projectKey };

  const load = useCallback(
    async (nextKind: string, initial = false) => {
      const cacheKey = boardCacheKey(projectKey, nextKind);
      const snapshot = initial ? recall<BoardSnapshot>(cacheKey) : undefined;
      if (snapshot) {
        setWorkflow(snapshot.workflow);
        setItems(snapshot.items);
      }
      setLoading(initial ? !snapshot : true);
      setError(null);
      try {
        const params = new URLSearchParams({ kind: nextKind, limit: "200" });
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
    load(kind, true);
    // load identity is stable; reload when the kind filter changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

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
        await load(stateRef.current.kind);
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

  const columns = useMemo(() => {
    const spec = workflow?.kinds[kind];
    if (!spec) return [];
    const subtypes = kind === "task" ? Object.values(spec.subtypes ?? {}) : [];
    const terminal = new Set([
      ...spec.terminal,
      ...subtypes.flatMap((subtype) => subtype.terminal),
    ]);
    const states =
      subtypes.length > 0
        ? [
            ...new Set([
              ...spec.states,
              ...subtypes.flatMap((subtype) => subtype.states),
            ]),
          ]
        : spec.states;
    const visible = states.filter((s) => showTerminal || !terminal.has(s));
    return visible.map((status) => ({
      status,
      items: items.filter((i) => i.status === status),
    }));
  }, [workflow, kind, showTerminal, items]);

  const openItem = (item: WorkItem) => {
    const from = location.pathname + location.search;
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
            <Inline space="space.050" alignBlock="center" testId="board-kind-filter">
              {kindOptions().map((k) => (
                <Button
                  key={k.value}
                  appearance={kind === k.value ? "primary" : "default"}
                  spacing="compact"
                  testId={`board-kind-${k.value}`}
                  onClick={() => setKind(k.value)}
                >
                  {k.label}
                </Button>
              ))}
            </Inline>
            <Checkbox
              label={t("board.showTerminal")}
              isChecked={showTerminal}
              testId="board-show-terminal"
              onChange={(e) => setShowTerminal(e.currentTarget.checked)}
            />
          </Inline>
        }
      />

      <Box xcss={styles.board} testId="board-columns">
        {error ? (
          <ErrorState error={error} onRetry={() => load(kind, true)} testId="board-error" />
        ) : loading ? (
          <Box xcss={styles.loading} testId="board-loading">
            <Spinner size="large" />
          </Box>
        ) : columns.length === 0 ? (
          <EmptyState header={t("board.empty")} />
        ) : (
          columns.map((col) => (
            <BoardColumn key={col.status} status={col.status} count={col.items.length}>
              {col.items.length === 0 ? null : (
                col.items.map((item) => (
                  <BoardCard key={item.id} item={item} onOpen={openItem} />
                ))
              )}
            </BoardColumn>
          ))
        )}
      </Box>
    </Page>
  );
}
