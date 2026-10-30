import { useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
import Lozenge from "@atlaskit/lozenge";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { token } from "@atlaskit/tokens";

import ErrorState from "../components/ErrorState";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { reloadSession } from "../lib/auth";
import { useAsync } from "../hooks/useAsync";
import { formatDate } from "../lib/format";
import { useNotify } from "../lib/flags";
import type { Notification } from "../types";

interface Result {
  items: Notification[];
  unread: number;
  total: number;
}

const styles = cssMap({
  card: {
    borderRadius: "var(--ds-radius-small)",
    borderWidth: "var(--ds-border-width)",
    borderStyle: "solid",
    borderColor: "var(--ds-border)",
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
});

const TYPE_LABEL: Record<string, string> = {
  assignment: "指派",
  step: "步骤",
  comment: "评论",
  mention: "提到",
  system: "系统",
};

export default function InboxPage() {
  const navigate = useNavigate();
  const notify = useNotify();
  const [unreadOnly, setUnreadOnly] = useState(true);
  const state = useAsync<Result>(async () => {
    const res = await api.get<Notification[]>(
      `/notifications?unread_only=${unreadOnly}&limit=100`,
    );
    return {
      items: res.data,
      unread: Number(res.meta?.unread ?? 0),
      total: Number(res.meta?.total ?? res.data.length),
    };
  }, [unreadOnly]);

  const open = async (n: Notification) => {
    if (!n.read_at) {
      try {
        await api.post("/notifications/read", { ids: [n.id] });
        await reloadSession();
        state.reload();
      } catch (e) {
        notify.error("标记已读失败", errorCause(e)?.message);
      }
    }
    if (n.url) navigate(n.url);
  };

  const markAll = async () => {
    try {
      const res = await api.post<{ updated: number }>("/notifications/read-all", {});
      notify.success(`已标记 ${res.data.updated} 条为已读`);
      await reloadSession();
      state.reload();
    } catch (e) {
      notify.error("标记失败", errorCause(e)?.message);
    }
  };

  return (
    <Page testId="page-inbox">
      <PageHeader
        title="收件箱"
        testId="inbox-header"
        actions={
          <Inline space="space.150" alignBlock="center">
            <Checkbox
              label="只看未读"
              isChecked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.currentTarget.checked)}
            />
            <Button onClick={markAll} testId="inbox-mark-all">
              全部已读
            </Button>
          </Inline>
        }
      />

      {state.error ? (
        <ErrorState error={state.error} onRetry={state.reload} testId="inbox-error" />
      ) : state.loading ? (
        <Box xcss={styles.centered} testId="inbox-loading">
          <Spinner size="large" />
        </Box>
      ) : (state.data?.items.length ?? 0) === 0 ? (
        <Box testId="inbox-empty">
          <EmptyState
            header={unreadOnly ? "没有未读通知" : "暂无通知"}
            description="指派、步骤与评论通知会出现在这里。"
          />
        </Box>
      ) : (
        <Stack space="space.100" testId="inbox-list">
          {state.data!.items.map((n) => (
            <Box
              key={n.id}
              xcss={styles.card}
              style={
                n.read_at
                  ? undefined
                  : {
                      borderInlineStart: `3px solid ${token("color.border.selected")}`,
                    }
              }
              testId={`inbox-item-${n.id}`}
              role="button"
              tabIndex={0}
              onClick={() => void open(n)}
              onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  void open(n);
                }
              }}
            >
              <Inline space="space.100" alignBlock="center" shouldWrap>
                <Lozenge appearance={n.read_at ? "default" : "inprogress"}>
                  {TYPE_LABEL[n.type] ?? n.type}
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
      )}
    </Page>
  );
}
