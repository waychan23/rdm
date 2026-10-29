import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import { monitorForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
import Spinner from "@atlaskit/spinner";
import { Box, Inline } from "@atlaskit/primitives/compiled";

import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";
import type { WorkItem, WorkflowDto } from "../types";
import { KIND_OPTIONS } from "../workitems/constants";
import BoardCard from "./board/BoardCard";
import BoardColumn from "./board/BoardColumn";

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
  const { key: projectKey = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const notify = useNotify();

  const [kind, setKind] = useState("task");
  const [showTerminal, setShowTerminal] = useState(true);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowDto | null>(null);
  const [loading, setLoading] = useState(true);

  // Latest values for the (mount-once) drop monitor.
  const stateRef = useRef({ items, workflow, kind, projectKey });
  stateRef.current = { items, workflow, kind, projectKey };

  const load = useCallback(
    async (nextKind: string, initial = false) => {
      setLoading(true);
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
      const { items: current, workflow: wf, projectKey: pk } = stateRef.current;
      const item = current.find((i) => i.id === itemId);
      if (!item || item.status === target) return;
      const allowed = wf?.kinds[item.kind]?.transitions[item.status] ?? [];
      if (!allowed.includes(target)) {
        notify.error(
          "非法流转",
          `${item.display_id} 不能从 ${item.status} 流转到 ${target}`,
        );
        return;
      }
      const previous = item.status;
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, status: target } : i)),
      );
      try {
        await api.post(`/work-items/${item.display_id}/transition`, {
          to: target,
          row_version: item.row_version,
          reason: null,
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
          "流转失败",
          blocking ? `${cause?.message}（阻塞: ${blocking}）` : cause?.message,
        );
      }
    },
    [load, notify],
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
    const terminal = new Set(spec.terminal);
    const states = spec.states.filter((s) => showTerminal || !terminal.has(s));
    return states.map((status) => ({
      status,
      items: items.filter((i) => i.status === status),
    }));
  }, [workflow, kind, showTerminal, items]);

  const openItem = (item: WorkItem) =>
    navigate(`/projects/${projectKey}/items/${item.id}`, {
      state: { from: location.pathname + location.search },
    });

  return (
    <Page fill testId="page-board">
      <PageHeader
        title="看板"
        testId="board-header"
        actions={
          <Inline space="space.100" alignBlock="center">
            <Inline space="space.050" alignBlock="center" testId="board-kind-filter">
              {KIND_OPTIONS.map((k) => (
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
              label="显示终态列"
              isChecked={showTerminal}
              testId="board-show-terminal"
              onChange={(e) => setShowTerminal(e.currentTarget.checked)}
            />
          </Inline>
        }
      />

      <Box xcss={styles.board} testId="board-columns">
        {loading ? (
          <Box xcss={styles.loading} testId="board-loading">
            <Spinner size="large" />
          </Box>
        ) : columns.length === 0 ? (
          <EmptyState header="该类型暂无工作流列" />
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
