import { useCallback, useEffect, useState } from "react";

import IconButton from "@atlaskit/button/icon/button";
import ChevronDownIcon from "@atlaskit/icon/core/chevron-down";
import ChevronRightIcon from "@atlaskit/icon/core/chevron-right";
import Spinner from "@atlaskit/spinner";
import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import TextButton from "../../components/TextButton";
import PersonCell from "../../components/PersonCell";
import StatusLozenge from "../../workitems/status";
import { api, errorCause } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { useNotify } from "../../lib/flags";
import type { HistoryEntry } from "../../types";

const FIELD_LABELS: Record<string, string> = {
  title: "标题",
  description_md: "描述",
  priority: "优先级",
  planned_start_date: "计划开始日期",
  planned_end_date: "计划完成日期",
  parent_id: "父项",
  source_story_id: "来源 story",
  acceptance_criteria_md: "验收标准",
  severity: "严重度",
  environment: "环境",
  repro_steps_md: "复现步骤",
  expected_behavior_md: "期望行为",
  actual_behavior_md: "实际行为",
  task_type: "任务类型",
  est_work_hours: "预估工时",
  actual_work_hours: "实际工时",
  code_branch: "代码分支",
  participants: "参与人",
  reviewer: "评审人",
  review_content_md: "评审意见",
  custom_fields: "自定义字段",
};

function stepName(entry: HistoryEntry): string {
  const step = entry.meta?.step;
  if (step && typeof step === "object") {
    return String((step as { name?: string }).name ?? "步骤");
  }
  return "步骤";
}

function nameOf(ref: unknown): string {
  if (ref && typeof ref === "object" && "name" in ref) {
    return String((ref as { name?: string }).name ?? "未指派");
  }
  return "未指派";
}

function describe(entry: HistoryEntry) {
  switch (entry.action) {
    case "created":
      return "创建了工作项";
    case "content_edited":
      return "编辑了内容";
    case "updated": {
      const fields = Object.keys(entry.changes);
      const labels = fields.map((f) => FIELD_LABELS[f] ?? f);
      return labels.length > 0 ? `修改了${labels.join("、")}` : "编辑了内容";
    }
    case "assigned":
      return `负责人从 ${nameOf(entry.changes.assignee?.from)} 改为 ${nameOf(
        entry.changes.assignee?.to,
      )}`;
    case "deleted":
      return "删除了工作项";
    case "restored":
      return "恢复了工作项";
    case "comment_created":
      return "评论了工作项";
    case "comment_deleted":
      return "删除了评论";
    case "step_started":
      return `发起了步骤「${stepName(entry)}」`;
    case "step_executed":
      return `执行了步骤「${stepName(entry)}」`;
    case "step_completed":
      return `步骤「${stepName(entry)}」完成并流转`;
    case "step_blocked":
      return `步骤「${stepName(entry)}」被 gate 阻塞`;
    case "step_cancelled":
      return `取消了步骤「${stepName(entry)}」`;
    case "step_reassigned":
      return `改派了步骤「${stepName(entry)}」的执行人`;
    default:
      return entry.event_type;
  }
}

interface Props {
  itemId: string;
  refreshKey: number;
}

export default function HistorySection({ itemId, refreshKey }: Props) {
  const notify = useNotify();
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [cursor, setCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (before: number | null, replace: boolean) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ limit: "30" });
        if (before !== null) params.set("before_seq", String(before));
        const res = await api.get<HistoryEntry[]>(
          `/work-items/${encodeURIComponent(itemId)}/history?${params.toString()}`,
        );
        setEntries((prev) => (replace ? res.data : [...prev, ...res.data]));
        setHasMore(Boolean(res.meta?.has_more));
        const next = res.meta?.next_before_seq;
        setCursor(typeof next === "number" ? next : null);
      } catch (e) {
        notify.error("历史加载失败", errorCause(e)?.message);
      } finally {
        setLoading(false);
      }
    },
    [itemId, notify],
  );

  useEffect(() => {
    if (!open) return;
    void load(null, true);
  }, [open, refreshKey, load]);

  return (
    <div className="rdm-item-history" data-testid="item-history">
      <Inline space="space.050" alignBlock="center">
        <IconButton
          icon={(p) =>
            open ? <ChevronDownIcon {...p} /> : <ChevronRightIcon {...p} />
          }
          label={open ? "收起操作历史" : "展开操作历史"}
          appearance="subtle"
          spacing="compact"
          testId="item-history-toggle"
          onClick={() => setOpen((value) => !value)}
        />
        <Text size="small" weight="medium" color="color.text.subtle">
          操作历史
        </Text>
      </Inline>

      {open && (
        <div className="rdm-item-history-list" data-testid="item-history-list">
          {loading && entries.length === 0 ? (
            <Spinner size="small" />
          ) : entries.length === 0 ? (
            <Text size="small" color="color.text.subtlest">
              还没有操作记录
            </Text>
          ) : (
            <Stack space="space.100">
              {entries.map((entry) => (
                <div
                  key={entry.id}
                  className="rdm-history-entry"
                  data-testid={`item-history-entry-${entry.id}`}
                >
                  <div className="rdm-history-head">
                    <PersonCell name={entry.actor?.name ?? entry.actor?.id ?? "系统"} />
                    <Text size="small" color="color.text.subtlest">
                      {formatDate(entry.occurred_at)}
                    </Text>
                  </div>
                  <div className="rdm-history-body">
                    {entry.action === "status_changed" ? (
                      <Inline space="space.050" alignBlock="center" shouldWrap>
                        <StatusLozenge
                          status={String(entry.changes.status?.from ?? "")}
                        />
                        <Text size="small">→</Text>
                        <StatusLozenge status={String(entry.changes.status?.to ?? "")} />
                        {typeof entry.meta?.reason === "string" && (
                          <Text size="small" color="color.text.subtlest">
                            （{entry.meta.reason}）
                          </Text>
                        )}
                      </Inline>
                    ) : (
                      <>
                        <Text size="small">{describe(entry)}</Text>
                        {entry.comment?.excerpt && (
                          <Text size="small" color="color.text.subtlest">
                            “{entry.comment.excerpt}”
                          </Text>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
              {hasMore && (
                <TextButton
                  onClick={() => void load(cursor, false)}
                  data-testid="item-history-more"
                >
                  加载更多
                </TextButton>
              )}
            </Stack>
          )}
        </div>
      )}
    </div>
  );
}
