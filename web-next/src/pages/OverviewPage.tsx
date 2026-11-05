import { useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import { token } from "@atlaskit/tokens";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import {
  getProjectOverview,
  type OverviewSprint,
  type ProjectOverview,
} from "../api/projects-api";
import { cardBorder } from "../components/cardBorder";
import ErrorState from "../components/ErrorState";
import { Page, PageHeader } from "../components/Page";
import PriorityMark from "../components/PriorityMark";
import TextButton from "../components/TextButton";
import TruncatedText from "../components/TruncatedText";
import TypeKindIcon from "../components/TypeKindIcon";
import { useAsync } from "../hooks/useAsync";
import { useCurrentUser } from "../lib/auth";
import { formatRelativeTime } from "../lib/format";
import { useOpenWorkItem } from "../lib/itemOverlay";
import { kindLabel } from "../lib/labels";
import { useListProjectKey } from "../lib/originSearch";
import type { WorkItem } from "../types";
import CreateWorkItemDialog from "../workitems/CreateWorkItemDialog";
import { priorityColor, priorityLabel } from "../workitems/priority";
import StatusLozenge, { statusTone, type StatusTone } from "../workitems/status";

// The overview is a dashboard: counters first, then the two things a person
// opens the project for (what is mine, what is late), then distributions and
// activity. Every panel is a live read model from GET /projects/{key}/overview.

const TONE_ORDER: StatusTone[] = ["doing", "todo", "blocked", "done"];

const TONE_COLOR: Record<StatusTone, string> = {
  doing: token("color.background.accent.blue.bolder"),
  todo: token("color.background.accent.blue.subtle"),
  blocked: token("color.background.accent.red.bolder"),
  done: token("color.background.neutral.bold"),
};

const barTrackStyle: CSSProperties = {
  height: token("space.100"),
  borderRadius: token("radius.full"),
  backgroundColor: token("color.background.neutral"),
  overflow: "hidden",
  minWidth: token("space.600"),
};

const titleStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const dotStyle = (color: string): CSSProperties => ({
  width: token("space.100"),
  height: token("space.100"),
  borderRadius: token("radius.full"),
  backgroundColor: color,
  display: "inline-block",
  flexShrink: 0,
});

const styles = cssMap({
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
  card: {
    borderRadius: "var(--ds-radius-small)",
    padding: "var(--ds-space-250)",
    backgroundColor: "var(--ds-surface)",
    minWidth: "0",
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: "var(--ds-space-150)",
    "@media (min-width: 64rem)": {
      gridTemplateColumns: "repeat(5, minmax(0, 1fr))",
    },
  },
  statCard: {
    borderRadius: "var(--ds-radius-small)",
    paddingBlock: "var(--ds-space-200)",
    paddingInline: "var(--ds-space-250)",
    backgroundColor: "var(--ds-surface)",
    minWidth: "0",
  },
  statCardClickable: {
    borderRadius: "var(--ds-radius-small)",
    paddingBlock: "var(--ds-space-200)",
    paddingInline: "var(--ds-space-250)",
    backgroundColor: "var(--ds-surface)",
    minWidth: "0",
    cursor: "pointer",
    "&:hover": {
      backgroundColor: "var(--ds-surface-raised-hovered)",
    },
    "&:focus-visible": {
      outline: "2px solid var(--ds-border-focused)",
    },
  },
  mainGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr)",
    gap: "var(--ds-space-200)",
    alignItems: "start",
    "@media (min-width: 64rem)": {
      gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)",
    },
  },
  distributionGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr)",
    gap: "var(--ds-space-200)",
    alignItems: "start",
    "@media (min-width: 64rem)": {
      gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)",
    },
  },
  column: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--ds-space-200)",
    minWidth: "0",
  },
  list: {
    display: "flex",
    flexDirection: "column",
    minWidth: "0",
  },
  itemRow: {
    display: "flex",
    alignItems: "center",
    gap: "var(--ds-space-100)",
    minWidth: "0",
    paddingBlock: "var(--ds-space-075)",
    paddingInline: "var(--ds-space-100)",
    borderRadius: "var(--ds-radius-small)",
    cursor: "pointer",
    "&:hover": {
      backgroundColor: "var(--ds-background-neutral-subtle-hovered)",
    },
    "&:focus-visible": {
      outline: "2px solid var(--ds-border-focused)",
    },
  },
  releaseRow: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--ds-space-075)",
    padding: "var(--ds-space-100)",
    borderRadius: "var(--ds-radius-small)",
    cursor: "pointer",
    "&:hover": {
      backgroundColor: "var(--ds-background-neutral-subtle-hovered)",
    },
    "&:focus-visible": {
      outline: "2px solid var(--ds-border-focused)",
    },
  },
  metricRow: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) auto auto",
    alignItems: "center",
    gap: "var(--ds-space-150)",
  },
  statusGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr)",
    columnGap: "var(--ds-space-300)",
    rowGap: "var(--ds-space-075)",
    "@media (min-width: 48rem)": {
      gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    },
  },
  hint: {
    paddingBlock: "var(--ds-space-150)",
  },
});

function todayISO(): string {
  // en-CA formats as YYYY-MM-DD in the user's local timezone.
  return new Date().toLocaleDateString("en-CA");
}

function percentOf(count: number, total: number): number {
  return total === 0 ? 0 : Math.round((count * 100) / total);
}

function ProgressBar({ percent, testId }: { percent: number; testId?: string }) {
  const clamped = Math.min(100, Math.max(0, percent));
  return (
    <div style={barTrackStyle} data-testid={testId} role="presentation">
      <div
        style={{
          width: `${clamped}%`,
          height: "100%",
          borderRadius: token("radius.full"),
          backgroundColor: token("color.background.accent.blue.bolder"),
        }}
      />
    </div>
  );
}

function StackedBar({ segments }: { segments: Array<{ count: number; color: string }> }) {
  const total = segments.reduce((sum, segment) => sum + segment.count, 0);
  return (
    <div style={{ ...barTrackStyle, display: "flex" }} role="presentation">
      {total > 0
        ? segments
            .filter((segment) => segment.count > 0)
            .map((segment, index) => (
              <div
                key={index}
                style={{
                  width: `${(segment.count * 100) / total}%`,
                  height: "100%",
                  backgroundColor: segment.color,
                }}
              />
            ))
        : null}
    </div>
  );
}

function CardHeader({
  title,
  count,
  action,
}: {
  title: string;
  count?: number;
  action?: ReactNode;
}) {
  return (
    <Inline spread="space-between" alignBlock="center" space="space.100">
      <Inline space="space.100" alignBlock="center">
        <Heading size="small" as="h2">
          {title}
        </Heading>
        {count !== undefined ? <Lozenge>{count}</Lozenge> : null}
      </Inline>
      {action}
    </Inline>
  );
}

function EmptyHint({ title, description }: { title: string; description?: string }) {
  return (
    <Box xcss={styles.hint}>
      <Stack space="space.050">
        <Text size="small" color="color.text.subtle">
          {title}
        </Text>
        {description ? (
          <Text size="small" color="color.text.subtlest">
            {description}
          </Text>
        ) : null}
      </Stack>
    </Box>
  );
}

function ItemRow({
  item,
  variant,
  onOpen,
}: {
  item: WorkItem;
  variant: "mine" | "overdue" | "recent";
  onOpen: (item: WorkItem) => void;
}) {
  const { t, i18n } = useTranslation("projects");
  const overdue = !!item.planned_end_date && item.planned_end_date < todayISO();
  const assignee = item.assignee?.display_name || item.assignee?.name || null;
  return (
    <Box
      xcss={styles.itemRow}
      role="button"
      tabIndex={0}
      testId={`overview-item-${item.display_id}`}
      onClick={() => onOpen(item)}
      onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(item);
        }
      }}
    >
      <TypeKindIcon kind={item.kind} />
      <Text size="small" color="color.text.subtle">
        {item.display_id}
      </Text>
      <TruncatedText text={item.title} style={titleStyle} />
      <StatusLozenge status={item.status} />
      {variant === "mine" ? (
        <>
          <PriorityMark priority={item.priority} />
          {item.planned_end_date ? (
            <Text
              size="small"
              color={overdue ? "color.text.danger" : "color.text.subtlest"}
            >
              {item.planned_end_date}
            </Text>
          ) : null}
        </>
      ) : null}
      {variant === "overdue" ? (
        <Text size="small" color="color.text.danger">
          {t("overview.due", { date: item.planned_end_date })}
        </Text>
      ) : null}
      {variant === "recent" ? (
        <>
          {assignee ? (
            <Text size="small" color="color.text.subtle">
              {assignee}
            </Text>
          ) : null}
          <Text size="small" color="color.text.subtlest">
            {formatRelativeTime(item.updated_at ?? item.created_at, i18n.language)}
          </Text>
        </>
      ) : null}
    </Box>
  );
}

function SprintPanel({ sprint, onOpen }: { sprint: OverviewSprint; onOpen: () => void }) {
  const { t } = useTranslation("projects");
  const range =
    sprint.start_date && sprint.end_date
      ? t("overview.sprintRange", { start: sprint.start_date, end: sprint.end_date })
      : (sprint.end_date ?? "");
  const days = sprint.days_remaining;
  const daysLabel =
    days === null
      ? null
      : days < 0
        ? t("overview.daysOver", { days: Math.abs(days) })
        : t("overview.daysLeft", { days });
  return (
    <Box xcss={styles.card} style={cardBorder} testId="overview-active-sprint">
      <Stack space="space.150">
        <CardHeader title={t("overview.activeSprint")} action={<TextButton onClick={onOpen}>{t("overview.viewAll")}</TextButton>} />
        <Stack space="space.100">
          <Inline spread="space-between" alignBlock="center" space="space.100">
            <Text weight="medium">{sprint.name}</Text>
            {range ? (
              <Text size="small" color="color.text.subtlest">
                {range}
              </Text>
            ) : null}
          </Inline>
          <ProgressBar percent={sprint.percent} testId="overview-sprint-progress" />
          <Inline spread="space-between" alignBlock="center" space="space.100">
            <Text size="small" color="color.text.subtle">
              {t("overview.progress", { done: sprint.done, total: sprint.total })}
            </Text>
            {daysLabel ? (
              <Text size="small" color={days !== null && days < 0 ? "color.text.danger" : "color.text.subtlest"}>
                {daysLabel}
              </Text>
            ) : null}
          </Inline>
        </Stack>
        <Inline space="space.150" shouldWrap>
          {Object.entries(sprint.by_status).map(([status, count]) => (
            <Inline key={status} space="space.050" alignBlock="center">
              <StatusLozenge status={status} />
              <Text size="small" color="color.text.subtle">
                {count}
              </Text>
            </Inline>
          ))}
        </Inline>
      </Stack>
    </Box>
  );
}

export default function OverviewPage() {
  const { t } = useTranslation("projects");
  const { key: routeKey = "" } = useParams();
  // The origin URL owns the project while this page is a drawer backdrop.
  const projectKey = useListProjectKey(routeKey);
  const navigate = useNavigate();
  const openItem = useOpenWorkItem();
  const me = useCurrentUser();
  const [showCreate, setShowCreate] = useState(false);
  const { data, loading, error, reload } = useAsync<ProjectOverview>(
    () => getProjectOverview(projectKey),
    [projectKey],
  );

  const go = (page: string) => navigate(`/projects/${projectKey}/${page}`);
  // Open the release drawer directly; its state lives in the releases URL.
  const openRelease = (id: string) =>
    navigate(`/projects/${projectKey}/releases?release=${encodeURIComponent(id)}`);
  const openBacklog = (params: string) =>
    navigate(`/projects/${projectKey}/backlog${params ? `?${params}` : ""}`);
  const myIdentityId = me?.identity.id ?? "";

  if (error) {
    return (
      <Page testId="page-project-overview">
        <ErrorState error={error} onRetry={reload} testId="overview-error" />
      </Page>
    );
  }

  if (loading || !data) {
    return (
      <Page testId="page-project-overview">
        <Box xcss={styles.centered} testId="overview-loading">
          <Spinner size="large" />
        </Box>
      </Page>
    );
  }

  const stats = [
    {
      key: "total",
      label: t("overview.stats.total"),
      value: data.total_items,
      testId: "overview-stat-total",
      onClick: () => openBacklog("kind=all"),
    },
    {
      key: "open",
      label: t("overview.stats.open"),
      value: data.open_items,
      testId: "overview-stat-open",
      onClick: () => openBacklog("kind=all&completed=false"),
    },
    {
      key: "mine",
      label: t("overview.stats.mine"),
      value: data.my_open_items,
      testId: "overview-stat-mine",
      onClick: myIdentityId
        ? () =>
            openBacklog(
              `kind=all&completed=false&assignee=${encodeURIComponent(myIdentityId)}`,
            )
        : undefined,
    },
    {
      key: "overdue",
      label: t("overview.stats.overdue"),
      value: data.overdue_count,
      testId: "overview-stat-overdue",
      danger: data.overdue_count > 0,
    },
    {
      key: "members",
      label: t("overview.stats.members"),
      value: data.members,
      testId: "overview-stat-members",
      onClick: () => go("members"),
    },
  ];

  const statusRows = Object.entries(data.by_status)
    .map(([status, count]) => ({ status, count, tone: statusTone(status) }))
    .sort(
      (a, b) =>
        TONE_ORDER.indexOf(a.tone) - TONE_ORDER.indexOf(b.tone) || b.count - a.count,
    );
  const toneLabels: Record<StatusTone, string> = {
    doing: t("overview.tone.doing"),
    todo: t("overview.tone.todo"),
    blocked: t("overview.tone.blocked"),
    done: t("overview.tone.done"),
  };
  const toneTotals = TONE_ORDER.map((tone) => ({
    tone,
    label: toneLabels[tone],
    count: statusRows
      .filter((row) => row.tone === tone)
      .reduce((sum, row) => sum + row.count, 0),
  }));

  const kindRows = Object.entries(data.by_kind)
    .map(([kind, count]) => ({ kind, count }))
    .sort((a, b) => b.count - a.count);
  const priorityRows = Object.entries(data.by_priority)
    .map(([priority, count]) => ({ priority: Number(priority), count }))
    .sort((a, b) => a.priority - b.priority);
  const priorityTotal = priorityRows.reduce((sum, row) => sum + row.count, 0);

  return (
    <Page testId="page-project-overview">
      <PageHeader
        title={data.project_name || projectKey}
        description={t("overview.subtitle", { key: projectKey })}
        testId="overview-header"
        actions={
          <>
            <Lozenge appearance={data.project_status === "active" ? "success" : "neutral"}>
              {data.project_status === "archived"
                ? t("status.archived")
                : data.project_status === "active"
                  ? t("status.active")
                  : data.project_status}
            </Lozenge>
            <Button testId="overview-refresh" onClick={reload}>
              {t("overview.refresh")}
            </Button>
            <Button
              appearance="primary"
              testId="overview-create"
              onClick={() => setShowCreate(true)}
            >
              {t("overview.create")}
            </Button>
          </>
        }
      />

      {data.total_items === 0 ? (
        <SectionMessage
          appearance="information"
          title={t("overview.empty")}
          testId="overview-empty"
          actions={
            <Button appearance="primary" onClick={() => setShowCreate(true)}>
              {t("overview.create")}
            </Button>
          }
        >
          {t("overview.emptyHint")}
        </SectionMessage>
      ) : null}

      <Box xcss={styles.statsGrid} testId="overview-stats">
        {stats.map((stat) => {
          const content = (
            <Stack space="space.050">
              <Inline space="space.100" alignBlock="center">
                <Heading size="medium" as="div">
                  {stat.value}
                </Heading>
                {stat.danger ? <span style={dotStyle(token("color.icon.danger"))} /> : null}
              </Inline>
              <Text size="small" color="color.text.subtlest">
                {stat.label}
              </Text>
            </Stack>
          );
          return stat.onClick ? (
            <Box
              key={stat.key}
              xcss={styles.statCardClickable}
              style={cardBorder}
              testId={stat.testId}
              role="button"
              tabIndex={0}
              onClick={stat.onClick}
              onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  stat.onClick?.();
                }
              }}
            >
              {content}
            </Box>
          ) : (
            <Box
              key={stat.key}
              xcss={styles.statCard}
              style={cardBorder}
              testId={stat.testId}
            >
              {content}
            </Box>
          );
        })}
      </Box>

      <Box xcss={styles.mainGrid}>
        <Box xcss={styles.card} style={cardBorder} testId="overview-my-items">
          <Stack space="space.150">
            <CardHeader
              title={t("overview.myItems")}
              count={data.my_open_items}
              action={
                myIdentityId ? (
                  <TextButton
                    data-testid="overview-view-my-items"
                    onClick={() =>
                      openBacklog(
                        `kind=all&completed=false&assignee=${encodeURIComponent(myIdentityId)}`,
                      )
                    }
                  >
                    {t("overview.viewAll")}
                  </TextButton>
                ) : null
              }
            />
            {data.my_items.length === 0 ? (
              <EmptyHint
                title={t("overview.myItemsEmpty")}
                description={t("overview.myItemsEmptyHint")}
              />
            ) : (
              <Box xcss={styles.list}>
                {data.my_items.map((item) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    variant="mine"
                    onOpen={(next) => openItem(projectKey, next.display_id)}
                  />
                ))}
              </Box>
            )}
          </Stack>
        </Box>

        <Stack space="space.200">
          {data.active_sprint ? (
            <SprintPanel sprint={data.active_sprint} onOpen={() => go("sprints")} />
          ) : (
            <Box xcss={styles.card} style={cardBorder} testId="overview-active-sprint">
              <Stack space="space.150">
                <CardHeader title={t("overview.activeSprint")} />
                <EmptyHint
                  title={t("overview.noActiveSprint")}
                  description={t("overview.noActiveSprintHint")}
                />
              </Stack>
            </Box>
          )}

          <Box xcss={styles.card} style={cardBorder} testId="overview-releases">
            <Stack space="space.150">
              <CardHeader
                title={t("overview.releases")}
                action={<TextButton onClick={() => go("releases")}>{t("overview.viewAll")}</TextButton>}
              />
              {data.releases.length === 0 ? (
                <EmptyHint
                  title={t("overview.noReleases")}
                  description={t("overview.noReleasesHint")}
                />
              ) : (
                <Box xcss={styles.list}>
                  {data.releases.map((release) => (
                    <Box
                      key={release.id}
                      xcss={styles.releaseRow}
                      role="button"
                      tabIndex={0}
                      testId={`overview-release-${release.id}`}
                      onClick={() => openRelease(release.id)}
                      onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openRelease(release.id);
                        }
                      }}
                    >
                      <Inline spread="space-between" alignBlock="center" space="space.100">
                        <Text weight="medium">{release.name}</Text>
                        <Text size="small" color="color.text.subtlest">
                          {release.target_date
                            ? t("overview.releaseTarget", { date: release.target_date })
                            : ""}
                        </Text>
                      </Inline>
                      <ProgressBar percent={release.stats.percent} />
                      <Text size="small" color="color.text.subtle">
                        {t("overview.progress", {
                          done: release.stats.done,
                          total: release.stats.total,
                        })}
                      </Text>
                    </Box>
                  ))}
                </Box>
              )}
            </Stack>
          </Box>
        </Stack>
      </Box>

      <Box xcss={styles.distributionGrid}>
        <Box xcss={styles.card} style={cardBorder} testId="overview-status-distribution">
          <Stack space="space.150">
            <CardHeader title={t("overview.statusDistribution")} count={data.total_items} />
            <StackedBar
              segments={toneTotals.map((entry) => ({
                count: entry.count,
                color: TONE_COLOR[entry.tone],
              }))}
            />
            <Inline space="space.200" shouldWrap>
              {toneTotals
                .filter((entry) => entry.count > 0)
                .map((entry) => (
                  <Inline
                    key={entry.tone}
                    space="space.050"
                    alignBlock="center"
                    testId={`overview-status-tone-${entry.tone}`}
                  >
                    <span style={dotStyle(TONE_COLOR[entry.tone])} />
                    <Text size="small" color="color.text.subtle">
                      {entry.label}
                    </Text>
                    <Text size="small" weight="medium">
                      {entry.count}
                    </Text>
                  </Inline>
                ))}
            </Inline>
            <Box xcss={styles.statusGrid}>
              {statusRows.map((row) => (
                <Inline key={row.status} spread="space-between" alignBlock="center" space="space.100">
                  <StatusLozenge status={row.status} />
                  <Inline space="space.100" alignBlock="center">
                    <Text size="small" color="color.text.subtlest">
                      {percentOf(row.count, data.total_items)}%
                    </Text>
                    <Text size="small" color="color.text.subtle">
                      {row.count}
                    </Text>
                  </Inline>
                </Inline>
              ))}
            </Box>
          </Stack>
        </Box>

        <Stack space="space.200">
          <Box xcss={styles.card} style={cardBorder} testId="overview-kind-distribution">
            <Stack space="space.150">
              <CardHeader title={t("overview.kindDistribution")} />
              {kindRows.map((row) => (
                <Box key={row.kind} xcss={styles.metricRow}>
                  <Inline space="space.100" alignBlock="center">
                    <TypeKindIcon kind={row.kind} />
                    <Text size="small">{kindLabel(row.kind)}</Text>
                  </Inline>
                  <span style={{ width: token("space.600") }}>
                    <ProgressBar percent={percentOf(row.count, data.total_items)} />
                  </span>
                  <Text size="small" color="color.text.subtle">
                    {row.count}
                  </Text>
                </Box>
              ))}
            </Stack>
          </Box>

          <Box xcss={styles.card} style={cardBorder} testId="overview-priority-distribution">
            <Stack space="space.150">
              <CardHeader title={t("overview.priorityDistribution")} />
              {priorityRows.map((row) => (
                <Box key={row.priority} xcss={styles.metricRow}>
                  <Inline space="space.100" alignBlock="center">
                    <span style={dotStyle(priorityColor(row.priority))} />
                    <Text size="small">{priorityLabel(row.priority)}</Text>
                  </Inline>
                  <span style={{ width: token("space.600") }}>
                    <ProgressBar percent={percentOf(row.count, priorityTotal)} />
                  </span>
                  <Text size="small" color="color.text.subtle">
                    {row.count}
                  </Text>
                </Box>
              ))}
            </Stack>
          </Box>
        </Stack>
      </Box>

      <Box xcss={styles.distributionGrid}>
        <Box xcss={styles.card} style={cardBorder} testId="overview-risk">
          <Stack space="space.150">
            <CardHeader title={t("overview.risk")} />
            <Inline space="space.400" shouldWrap>
              <Inline space="space.100" alignBlock="baseline" testId="overview-risk-overdue">
                <Heading size="medium" as="div">
                  {data.overdue_count}
                </Heading>
                <Text size="small" color="color.text.subtle">
                  {t("overview.overdue")}
                </Text>
              </Inline>
              <Inline space="space.100" alignBlock="baseline" testId="overview-risk-blocked">
                <Heading size="medium" as="div">
                  {data.blocked_count}
                </Heading>
                <Text size="small" color="color.text.subtle">
                  {t("overview.blocked")}
                </Text>
              </Inline>
            </Inline>
            {data.overdue_items.length === 0 ? (
              <EmptyHint title={t("overview.riskEmpty")} />
            ) : (
              <Stack space="space.075">
                <Text size="small" weight="medium" color="color.text.subtle">
                  {t("overview.overdueItems")}
                </Text>
                {data.overdue_items.map((item) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    variant="overdue"
                    onOpen={(next) => openItem(projectKey, next.display_id)}
                  />
                ))}
              </Stack>
            )}
          </Stack>
        </Box>

        <Box xcss={styles.card} style={cardBorder} testId="overview-recent-items">
          <Stack space="space.150">
            <CardHeader title={t("overview.recent")} />
            {data.recent_items.length === 0 ? (
              <EmptyHint title={t("overview.recentEmpty")} />
            ) : (
              <Box xcss={styles.list}>
                {data.recent_items.map((item) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    variant="recent"
                    onOpen={(next) => openItem(projectKey, next.display_id)}
                  />
                ))}
              </Box>
            )}
          </Stack>
        </Box>
      </Box>

      <CreateWorkItemDialog
        open={showCreate}
        projectKey={projectKey}
        onClose={() => setShowCreate(false)}
        onCreated={(item) => {
          reload();
          openItem(projectKey, item.display_id);
        }}
      />
    </Page>
  );
}
