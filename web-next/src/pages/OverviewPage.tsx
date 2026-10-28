import { useNavigate, useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import { Box, Grid, Inline, Stack, Text, xcss } from "@atlaskit/primitives";
import { token } from "@atlaskit/tokens";

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

const statCard = xcss({
  border: `${token("border.width")} solid ${token("color.border")}`,
  borderRadius: "radius.small",
  padding: "space.250",
  backgroundColor: "elevation.surface",
});

const panel = xcss({
  border: `${token("border.width")} solid ${token("color.border")}`,
  borderRadius: "radius.small",
  padding: "space.250",
  backgroundColor: "elevation.surface",
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
      <Box padding="space.400">
        <Spinner size="large" />
      </Box>
    );
  }

  const stats = [
    { label: "全部工作项", value: data.total_items },
    { label: "未完成", value: data.open_items },
    { label: "我的待办", value: data.my_open_items },
    { label: "成员", value: data.members },
  ];

  return (
    <Box padding="space.300">
      <Inline spread="space-between" alignBlock="center">
        <Heading size="large">{projectKey} 概览</Heading>
        <Inline space="space.100">
          <Button onClick={() => go("board")}>看板</Button>
          <Button onClick={() => go("backlog")}>工作项</Button>
          <Button onClick={() => go("sprints")}>迭代</Button>
          <Button onClick={() => go("mailbox")}>信箱</Button>
        </Inline>
      </Inline>

      <Stack space="space.250">
        <Grid gap="space.200" templateColumns="1fr 1fr 1fr 1fr">
          {stats.map((s) => (
            <Box key={s.label} xcss={statCard}>
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

        <Grid gap="space.200" templateColumns="360px 360px" alignItems="start">
          <Box xcss={panel}>
            <Stack space="space.150">
              <Text weight="semibold">类型分布</Text>
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

          <Box xcss={panel}>
            <Stack space="space.150">
              <Text weight="semibold">状态分布</Text>
              {Object.entries(data.by_status).map(([status, count]) => (
                <Inline key={status} spread="space-between" alignBlock="center">
                  <StatusLozenge status={status} />
                  <Text color="color.text.subtle">{count}</Text>
                </Inline>
              ))}
            </Stack>
          </Box>

          {data.active_sprint && (
            <Box xcss={panel}>
              <Stack space="space.150">
                <Text weight="semibold">进行中迭代 · {data.active_sprint.name}</Text>
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
      </Stack>
    </Box>
  );
}
