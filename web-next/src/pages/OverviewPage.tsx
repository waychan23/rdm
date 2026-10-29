import { useNavigate, useParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import { cardBorder } from "../components/cardBorder";
import { Page, PageHeader } from "../components/Page";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import TypeKindIcon from "../components/TypeKindIcon";
import StatusLozenge from "../workitems/status";
import { KIND_OPTIONS } from "../workitems/constants";

interface Overview {
  total_items: number;
  open_items: number;
  my_open_items: number;
  members: number;
  by_kind: Record<string, number>;
  by_status: Record<string, number>;
  active_sprint: {
    name: string;
    total: number;
    by_status: Record<string, number>;
  } | null;
}

const kindLabel = (k: string) => KIND_OPTIONS.find((o) => o.value === k)?.label ?? k;

const styles = cssMap({
  card: {
    borderRadius: "var(--ds-radius-small)",
    padding: "var(--ds-space-250)",
    backgroundColor: "var(--ds-surface)",
  },
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: "var(--ds-space-200)",
  },
  panelsGrid: {
    display: "grid",
    gridTemplateColumns: "360px 360px",
    gap: "var(--ds-space-200)",
    alignItems: "start",
  },
});

export default function OverviewPage() {
  const { key: projectKey = "" } = useParams();
  const navigate = useNavigate();
  const { data, loading } = useAsync<Overview>(
    async () => (await api.get<Overview>(`/projects/${projectKey}/overview`)).data,
    [projectKey],
  );

  const go = (page: string) => navigate(`/projects/${projectKey}/${page}`);

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
    { label: "全部工作项", value: data.total_items, testId: "overview-stat-total" },
    { label: "未完成", value: data.open_items, testId: "overview-stat-open" },
    { label: "我的待办", value: data.my_open_items, testId: "overview-stat-mine" },
    { label: "成员", value: data.members, testId: "overview-stat-members" },
  ];

  return (
    <Page testId="page-project-overview">
      <PageHeader
        title={`${projectKey} 概览`}
        testId="overview-header"
        actions={
          <>
            <Button testId="overview-go-board" onClick={() => go("board")}>
              看板
            </Button>
            <Button testId="overview-go-backlog" onClick={() => go("backlog")}>
              工作项
            </Button>
            <Button testId="overview-go-sprints" onClick={() => go("sprints")}>
              迭代
            </Button>
            <Button testId="overview-go-mailbox" onClick={() => go("mailbox")}>
              信箱
            </Button>
          </>
        }
      />

      <Box xcss={styles.statsGrid} testId="overview-stats">
        {stats.map((s) => (
          <Box key={s.label} xcss={styles.card} style={cardBorder} testId={s.testId}>
            <Stack space="space.050">
              <Text size="large" weight="bold">
                {s.value}
              </Text>
              <Text size="small" color="color.text.subtlest">
                {s.label}
              </Text>
            </Stack>
          </Box>
        ))}
      </Box>

      <Box xcss={styles.panelsGrid} testId="overview-panels">
        <Box xcss={styles.card} style={cardBorder} testId="overview-by-kind">
          <Stack space="space.150">
            <Heading size="small">类型分布</Heading>
            {Object.entries(data.by_kind).map(([kind, count]) => (
              <Inline key={kind} spread="space-between" alignBlock="center">
                <Inline space="space.100" alignBlock="center">
                  <TypeKindIcon kind={kind} />
                  <Text>{kindLabel(kind)}</Text>
                </Inline>
                <Text color="color.text.subtle">{count}</Text>
              </Inline>
            ))}
          </Stack>
        </Box>

        <Box xcss={styles.card} style={cardBorder} testId="overview-by-status">
          <Stack space="space.150">
            <Heading size="small">状态分布</Heading>
            {Object.entries(data.by_status).map(([status, count]) => (
              <Inline key={status} spread="space-between" alignBlock="center">
                <StatusLozenge status={status} />
                <Text color="color.text.subtle">{count}</Text>
              </Inline>
            ))}
          </Stack>
        </Box>

        {data.active_sprint && (
          <Box xcss={styles.card} style={cardBorder} testId="overview-active-sprint">
            <Stack space="space.150">
              <Heading size="small">进行中迭代 · {data.active_sprint.name}</Heading>
              <Text size="small" color="color.text.subtlest">
                共 {data.active_sprint.total} 项
              </Text>
              {Object.entries(data.active_sprint.by_status).map(([status, count]) => (
                <Inline key={status} spread="space-between" alignBlock="center">
                  <StatusLozenge status={status} />
                  <Text color="color.text.subtle">{count}</Text>
                </Inline>
              ))}
            </Stack>
          </Box>
        )}
      </Box>
    </Page>
  );
}
