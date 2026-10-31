import { useEffect, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
import Lozenge from "@atlaskit/lozenge";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { token } from "@atlaskit/tokens";

import { cardBorder } from "../components/cardBorder";
import ErrorState from "../components/ErrorState";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { reloadSession } from "../lib/auth";
import { useAsync } from "../hooks/useAsync";
import { formatDate } from "../lib/format";
import { useNotify } from "../lib/flags";
import { notificationTypeLabel } from "../lib/labels";
import type { Notification, TodoBundle, TodoStepEntry, WorkItem } from "../types";
import StatusLozenge from "../workitems/status";

interface NotificationResult {
  items: Notification[];
  unread: number;
  total: number;
}

type Tab = "notifications" | "todo";
type Order = "desc" | "asc";

const styles = cssMap({
  card: {
    borderRadius: "var(--ds-radius-small)",
    paddingBlock: "var(--ds-space-150)",
    paddingInline: "var(--ds-space-200)",
    backgroundColor: "var(--ds-surface)",
    cursor: "pointer",
    "&:hover": { backgroundColor: "var(--ds-surface-hovered)" },
  },
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
  sectionTitle: {
    marginBlockStart: "var(--ds-space-200)",
  },
});

function unreadStyle(read: boolean) {
  return read
    ? undefined
    : { borderInlineStart: `3px solid ${token("color.border.selected")}` };
}

export default function InboxPage() {
  const { t } = useTranslation("inbox");
  const navigate = useNavigate();
  const notify = useNotify();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get("tab") === "todo" ? "todo" : "notifications";
  const unreadOnly = searchParams.get("unread") !== "false";
  const order: Order = searchParams.get("order") === "asc" ? "asc" : "desc";
  const patchParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };
  const setTab = (value: Tab) => patchParams({ tab: value === "todo" ? "todo" : null });
  const setUnreadOnly = (value: boolean) =>
    patchParams({ unread: value ? null : "false" });
  const setOrder = (value: Order) =>
    patchParams({ order: value === "desc" ? null : value });
  const sortOptions = [
    { label: t("sort.newest"), value: "desc" },
    { label: t("sort.oldest"), value: "asc" },
  ];

  const notifications = useAsync<NotificationResult>(async () => {
    const res = await api.get<Notification[]>(
      `/notifications?unread_only=${unreadOnly}&order=${order}&limit=100`,
    );
    return {
      items: res.data,
      unread: Number(res.meta?.unread ?? 0),
      total: Number(res.meta?.total ?? res.data.length),
    };
  }, [unreadOnly, order]);

  const todos = useAsync<TodoBundle>(async () => {
    if (tab !== "todo") {
      return { assigned: [], pending_steps: [], approvals: [], overdue: [], mentions: [] };
    }
    return (await api.get<TodoBundle>("/todos")).data;
  }, [tab]);

  useEffect(() => {
    const onChange = () => {
      notifications.reload();
      todos.reload();
    };
    window.addEventListener("rdm:notification", onChange);
    window.addEventListener("rdm:data-changed", onChange);
    return () => {
      window.removeEventListener("rdm:notification", onChange);
      window.removeEventListener("rdm:data-changed", onChange);
    };
  }, [notifications.reload, todos.reload]);

  const openNotification = async (n: Notification) => {
    if (!n.read_at) {
      try {
        await api.post("/notifications/read", { ids: [n.id] });
        await reloadSession();
        notifications.reload();
      } catch (e) {
        notify.error(t("notify.markReadFailed"), errorCause(e)?.message);
      }
    }
    if (n.url) navigate(n.url);
  };

  const markAll = async () => {
    try {
      const res = await api.post<{ updated: number }>("/notifications/read-all", {});
      notify.success(t("notify.markAllSuccess", { count: res.data.updated }));
      await reloadSession();
      notifications.reload();
    } catch (e) {
      notify.error(t("notify.markAllFailed"), errorCause(e)?.message);
    }
  };

  const openItem = (item: WorkItem) => {
    if (!item.project_key) {
      notify.error(t("notify.openItemFailed"), t("notify.openItemMissingProject"));
      return;
    }
    navigate(`/projects/${item.project_key}/items/${item.display_id}`);
  };

  const openStep = (entry: TodoStepEntry) => openItem(entry.item);

  return (
    <Page testId="page-inbox">
      <PageHeader
        title={t("title")}
        testId="inbox-header"
        actions={
          <Inline space="space.150" alignBlock="center">
            <Inline space="space.050">
              <Button
                appearance={tab === "notifications" ? "primary" : "default"}
                testId="inbox-tab-notifications"
                onClick={() => setTab("notifications")}
              >
                {t("tabs.notifications")}
              </Button>
              <Button
                appearance={tab === "todo" ? "primary" : "default"}
                testId="inbox-tab-todo"
                onClick={() => setTab("todo")}
              >
                {t("tabs.todo")}
              </Button>
            </Inline>
            {tab === "notifications" ? (
              <>
                <Box style={{ width: 130 }}>
                  <Select
                    spacing="compact"
                    options={sortOptions}
                    value={sortOptions.find((o) => o.value === order) ?? null}
                    onChange={(opt) =>
                      setOrder(((opt as { value?: string } | null)?.value as Order) ?? "desc")
                    }
                    testId="inbox-sort"
                  />
                </Box>
                <Checkbox
                  label={t("filters.unreadOnly")}
                  isChecked={unreadOnly}
                  onChange={(e) => setUnreadOnly(e.currentTarget.checked)}
                />
                <Button onClick={markAll} testId="inbox-mark-all">
                  {t("actions.markAllRead")}
                </Button>
              </>
            ) : (
              <Button onClick={todos.reload} testId="inbox-todo-refresh">
                {t("actions.refresh")}
              </Button>
            )}
          </Inline>
        }
      />

      {tab === "notifications" ? (
        notifications.error ? (
          <ErrorState
            error={notifications.error}
            onRetry={notifications.reload}
            testId="inbox-error"
          />
        ) : notifications.loading ? (
          <Box xcss={styles.centered} testId="inbox-loading">
            <Spinner size="large" />
          </Box>
        ) : (notifications.data?.items.length ?? 0) === 0 ? (
          <Box testId="inbox-empty">
            <EmptyState
              header={unreadOnly ? t("empty.unreadHeader") : t("empty.header")}
              description={t("empty.description")}
            />
          </Box>
        ) : (
          <Stack space="space.100" testId="inbox-list">
            {notifications.data!.items.map((n) => (
              <Box
                key={n.id}
                xcss={styles.card}
                style={{ ...cardBorder, ...unreadStyle(Boolean(n.read_at)) }}
                testId={`inbox-item-${n.id}`}
                role="button"
                tabIndex={0}
                onClick={() => void openNotification(n)}
                onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
                  if (e.target !== e.currentTarget) return;
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    void openNotification(n);
                  }
                }}
              >
                <Inline space="space.100" alignBlock="center" shouldWrap>
                  <Lozenge appearance={n.read_at ? "default" : "inprogress"}>
                    {notificationTypeLabel(n.type)}
                  </Lozenge>
                  <Text weight="medium">{n.title}</Text>
                  {n.entity_ref ? (
                    <Text color="color.text.subtlest" size="small">
                      {n.entity_ref}
                    </Text>
                  ) : null}
                  <Text color="color.text.subtlest" size="small">
                    {formatDate(n.created_at)}
                  </Text>
                </Inline>
                {n.body ? (
                  <Box paddingBlockStart="space.050">
                    <Text color="color.text.subtle" size="small">
                      {n.body}
                    </Text>
                  </Box>
                ) : null}
              </Box>
            ))}
          </Stack>
        )
      ) : todos.error ? (
        <ErrorState error={todos.error} onRetry={todos.reload} testId="inbox-todo-error" />
      ) : todos.loading ? (
        <Box xcss={styles.centered} testId="inbox-todo-loading">
          <Spinner size="large" />
        </Box>
      ) : (
        <Stack space="space.150" testId="inbox-todo">
          <Box testId="todo-approvals">
            <Text weight="medium">{t("todo.approvals", { count: todos.data?.approvals.length ?? 0 })}</Text>
            <Stack space="space.050">
              {(todos.data?.approvals ?? []).map((entry) => (
                <StepRow key={entry.step.id} entry={entry} onOpen={openStep} />
              ))}
              {(todos.data?.approvals.length ?? 0) === 0 ? (
                <Text size="small" color="color.text.subtlest">
                  {t("todo.approvalsEmpty")}
                </Text>
              ) : null}
            </Stack>
          </Box>

          <Box testId="todo-pending-steps">
            <Text weight="medium">
              {t("todo.pendingSteps", { count: todos.data?.pending_steps.length ?? 0 })}
            </Text>
            <Stack space="space.050">
              {(todos.data?.pending_steps ?? []).map((entry) => (
                <StepRow key={entry.step.id} entry={entry} onOpen={openStep} />
              ))}
              {(todos.data?.pending_steps.length ?? 0) === 0 ? (
                <Text size="small" color="color.text.subtlest">
                  {t("todo.pendingStepsEmpty")}
                </Text>
              ) : null}
            </Stack>
          </Box>

          <Box testId="todo-assigned">
            <Text weight="medium">{t("todo.assigned", { count: todos.data?.assigned.length ?? 0 })}</Text>
            <Stack space="space.050">
              {(todos.data?.assigned ?? []).map((item) => (
                <ItemRow key={item.id} item={item} onOpen={openItem} />
              ))}
              {(todos.data?.assigned.length ?? 0) === 0 ? (
                <Text size="small" color="color.text.subtlest">
                  {t("todo.assignedEmpty")}
                </Text>
              ) : null}
            </Stack>
          </Box>

          <Box testId="todo-overdue">
            <Text weight="medium">{t("todo.overdue", { count: todos.data?.overdue.length ?? 0 })}</Text>
            <Stack space="space.050">
              {(todos.data?.overdue ?? []).map((item) => (
                <ItemRow key={item.id} item={item} onOpen={openItem} />
              ))}
              {(todos.data?.overdue.length ?? 0) === 0 ? (
                <Text size="small" color="color.text.subtlest">
                  {t("todo.overdueEmpty")}
                </Text>
              ) : null}
            </Stack>
          </Box>
        </Stack>
      )}
    </Page>
  );
}

function StepRow({ entry, onOpen }: { entry: TodoStepEntry; onOpen: (e: TodoStepEntry) => void }) {
  const { t } = useTranslation("inbox");
  return (
    <Box
      xcss={styles.card}
      style={cardBorder}
      testId={`todo-step-${entry.step.id}`}
      role="button"
      tabIndex={0}
      onClick={() => onOpen(entry)}
      onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(entry);
        }
      }}
    >
      <Inline space="space.100" alignBlock="center" shouldWrap>
        <Lozenge appearance={entry.step.mode === "approval" ? "moved" : "inprogress"}>
          {entry.step.mode === "approval" ? t("todo.mode.approval") : t("todo.mode.execute")}
        </Lozenge>
        <Text weight="medium">{entry.step.name}</Text>
        <Text color="color.text.subtlest" size="small">
          {entry.item.display_id}
        </Text>
        <Text>{entry.item.title}</Text>
        <StatusLozenge status={entry.item.status} />
      </Inline>
    </Box>
  );
}

function ItemRow({ item, onOpen }: { item: WorkItem; onOpen: (i: WorkItem) => void }) {
  const { t } = useTranslation("inbox");
  return (
    <Box
      xcss={styles.card}
      style={cardBorder}
      testId={`todo-item-${item.id}`}
      role="button"
      tabIndex={0}
      onClick={() => onOpen(item)}
      onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(item);
        }
      }}
    >
      <Inline space="space.100" alignBlock="center" shouldWrap>
        <Text color="color.text.subtlest" size="small">
          {item.display_id}
        </Text>
        <Text weight="medium">{item.title}</Text>
        <StatusLozenge status={item.status} />
        {item.planned_end_date ? (
          <Text color="color.text.subtlest" size="small">
            {t("todo.due", { date: item.planned_end_date })}
          </Text>
        ) : null}
      </Inline>
    </Box>
  );
}
