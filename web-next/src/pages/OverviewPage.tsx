import { useNavigate, useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import { Box, Grid, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

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

const cardStyles = xcss({
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
  padding: "space.250",
  backgroundColor: "elevation.surface",
});

const centeredStyles = xcss({
  display: "flex",
  justifyContent: "center",
  padding: "space.400",
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
        <Box xcss={centeredStyles} testId="overview-loading">
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

      <Grid
        gap="space.200"
        templateColumns="1fr 1fr 1fr 1fr"
        testId="overview-stats"
      >
        {stats.map((s) => (
          <Box key={s.label} xcss={cardStyles} testId={s.testId}>
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
      </Grid>

      <Grid
        gap="space.200"
        templateColumns="360px 360px"
        alignItems="start"
        testId="overview-panels"
      >
        <Box xcss={cardStyles} testId="overview-by-kind">
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

        <Box xcss={cardStyles} testId="overview-by-status">
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
          <Box xcss={cardStyles} testId="overview-active-sprint">
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
      </Grid>
    </Page>
  );
}
