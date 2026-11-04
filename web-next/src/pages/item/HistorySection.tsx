import { useCallback, useEffect, useState } from "react";

import IconButton from "@atlaskit/button/icon/button";
import ChevronDownIcon from "@atlaskit/icon/core/chevron-down";
import ChevronRightIcon from "@atlaskit/icon/core/chevron-right";
import Spinner from "@atlaskit/spinner";
import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import TextButton from "../../components/TextButton";
import PersonCell from "../../components/PersonCell";
import StatusLozenge from "../../workitems/status";
import { getWorkItemHistory } from "../../api/work-items-api";
import { errorCause } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { useNotify } from "../../lib/flags";
import { userLabel } from "../../lib/users";
import type { HistoryEntry } from "../../types";

function fieldLabel(key: string, t: TFunction<"item">): string {
  const labels: Record<string, string> = {
    title: t("history.field.title"),
    description_md: t("history.field.description_md"),
    priority: t("history.field.priority"),
    planned_start_date: t("history.field.planned_start_date"),
    planned_end_date: t("history.field.planned_end_date"),
    parent_id: t("history.field.parent_id"),
    source_story_id: t("history.field.source_story_id"),
    acceptance_criteria_md: t("history.field.acceptance_criteria_md"),
    severity: t("history.field.severity"),
    environment: t("history.field.environment"),
    repro_steps_md: t("history.field.repro_steps_md"),
    expected_behavior_md: t("history.field.expected_behavior_md"),
    actual_behavior_md: t("history.field.actual_behavior_md"),
    task_type: t("history.field.task_type"),
    est_work_hours: t("history.field.est_work_hours"),
    actual_work_hours: t("history.field.actual_work_hours"),
    code_branch: t("history.field.code_branch"),
    participants: t("history.field.participants"),
    reviewer: t("history.field.reviewer"),
    review_content_md: t("history.field.review_content_md"),
    custom_fields: t("history.field.custom_fields"),
  };
  return labels[key] ?? key;
}

function stepName(entry: HistoryEntry, t: TFunction<"item">): string {
  const step = entry.meta?.step;
  if (step && typeof step === "object") {
    return String((step as { name?: string }).name ?? t("history.step"));
  }
  return t("history.step");
}

function nameOf(ref: unknown, t: TFunction<"item">): string {
  if (ref && typeof ref === "object" && "name" in ref) {
    return String((ref as { name?: string }).name ?? t("history.unassigned"));
  }
  return t("history.unassigned");
}

function describe(entry: HistoryEntry, t: TFunction<"item">) {
  switch (entry.action) {
    case "created":
      return t("history.created");
    case "content_edited":
      return t("history.contentEdited");
    case "updated": {
      const fields = Object.keys(entry.changes);
      const labels = fields.map((f) => fieldLabel(f, t));
      return labels.length > 0
        ? t("history.updated", { fields: labels.join(t("listSeparator")) })
        : t("history.contentEdited");
    }
    case "assigned":
      return t("history.assigned", {
        from: nameOf(entry.changes.assignee?.from, t),
        to: nameOf(entry.changes.assignee?.to, t),
      });
    case "deleted":
      return t("history.deleted");
    case "restored":
      return t("history.restored");
    case "comment_created":
      return t("history.commentCreated");
    case "comment_deleted":
      return t("history.commentDeleted");
    case "step_started":
      return t("history.stepStarted", { name: stepName(entry, t) });
    case "step_executed":
      return t("history.stepExecuted", { name: stepName(entry, t) });
    case "step_completed":
      return t("history.stepCompleted", { name: stepName(entry, t) });
    case "step_blocked":
      return t("history.stepBlocked", { name: stepName(entry, t) });
    case "step_cancelled":
      return t("history.stepCancelled", { name: stepName(entry, t) });
    case "step_reassigned":
      return t("history.stepReassigned", { name: stepName(entry, t) });
    default:
      return entry.event_type;
  }
}

interface Props {
  itemId: string;
  refreshKey: number;
}

export default function HistorySection({ itemId, refreshKey }: Props) {
  const { t } = useTranslation("item");
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
        const res = await getWorkItemHistory(itemId, params);
        setEntries((prev) => (replace ? res.data : [...prev, ...res.data]));
        setHasMore(Boolean(res.meta?.has_more));
        const next = res.meta?.next_before_seq;
        setCursor(typeof next === "number" ? next : null);
      } catch (e) {
        notify.error(t("history.loadFailed"), errorCause(e)?.message);
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
          label={open ? t("history.collapse") : t("history.expand")}
          appearance="subtle"
          spacing="compact"
          testId="item-history-toggle"
          onClick={() => setOpen((value) => !value)}
        />
        <Text size="small" weight="medium" color="color.text.subtle">
          {t("history.title")}
        </Text>
      </Inline>

      {open && (
        <div className="rdm-item-history-list" data-testid="item-history-list">
          {loading && entries.length === 0 ? (
            <Spinner size="small" />
          ) : entries.length === 0 ? (
            <Text size="small" color="color.text.subtlest">
              {t("history.empty")}
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
                    <PersonCell
                      name={
                        entry.actor
                          ? userLabel(entry.actor) || entry.actor.id
                          : t("history.system")
                      }
                    />
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
                            {t("history.reasonWrap", { reason: entry.meta.reason })}
                          </Text>
                        )}
                      </Inline>
                    ) : (
                      <>
                        <Text size="small">{describe(entry, t)}</Text>
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
                  {t("history.loadMore")}
                </TextButton>
              )}
            </Stack>
          )}
        </div>
      )}
    </div>
  );
}
