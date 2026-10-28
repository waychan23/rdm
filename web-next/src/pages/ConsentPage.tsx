import { useState } from "react";
import { useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import { RadioGroup } from "@atlaskit/radio";
import Spinner from "@atlaskit/spinner";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";

interface ConsentInfo {
  client: { client_id: string; client_name: string | null };
  scopes: string[];
  selectable_members: {
    id: string;
    name: string;
    type: string;
    project_key: string | null;
  }[];
}

const wrapStyles = xcss({
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: "color.background.neutral.subtle",
  padding: "space.300",
});

const actionsStyles = xcss({
  justifyContent: "flex-end",
});

const cardStyles = xcss({
  width: "440px",
  maxWidth: "100%",
  padding: "space.300",
  backgroundColor: "elevation.surface",
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
});

export default function ConsentPage() {
  const { id = "" } = useParams();
  const notify = useNotify();
  const [memberId, setMemberId] = useState("");
  const [loading, setLoading] = useState(false);

  const { data: info, loading: listLoading } = useAsync(async () => {
    const res = await api.get<ConsentInfo>(`/oauth/consent/${id}`);
    setMemberId(res.data.selectable_members[0]?.id ?? "");
    return res.data;
  }, [id]);

  const decide = async (allow: boolean) => {
    if (loading) return;
    setLoading(true);
    try {
      const body: { decision: "allow" | "deny"; member_id?: string } = {
        decision: allow ? "allow" : "deny",
      };
      if (allow) body.member_id = memberId;
      const redirect = (
        await api.post<{ redirect_to: string }>(`/oauth/consent/${id}/decision`, body)
      ).data.redirect_to;
      window.location.assign(redirect);
    } catch (e) {
      notify.error("授权失败", errorCause(e)?.message);
      setLoading(false);
    }
  };

  return (
    <Box xcss={wrapStyles}>
      <Box xcss={cardStyles}>
        {listLoading || !info ? (
          <Inline space="space.150" alignBlock="center">
            <Spinner size="small" />
            <Text color="color.text.subtlest">加载授权请求…</Text>
          </Inline>
        ) : (
          <Stack space="space.200">
            <Heading size="large">授权访问 rdm</Heading>
            <Text>
              应用{" "}
              <Text weight="bold">{info.client.client_name || info.client.client_id}</Text>{" "}
              请求访问你的 rdm 工作区（scope: {info.scopes.join(" ")}）。
            </Text>
            {info.selectable_members.length > 0 && (
              <Stack space="space.100">
                <Text size="small" color="color.text.subtlest">
                  以哪个身份授权
                </Text>
                <RadioGroup
                  options={info.selectable_members.map((m) => ({
                    name: "consent-member",
                    value: m.id,
                    label: (
                      <Inline space="space.100" alignBlock="center">
                        <span>{m.name}</span>
                        <Lozenge appearance={m.type === "agent" ? "warning" : "default"}>
                          {m.type}
                        </Lozenge>
                        {m.project_key && (
                          <Text size="small" color="color.text.subtlest">
                            {m.project_key}
                          </Text>
                        )}
                      </Inline>
                    ),
                  }))}
                  value={memberId}
                  onChange={(e) => setMemberId(e.currentTarget.value)}
                />
              </Stack>
            )}
            <Inline space="space.100" xcss={actionsStyles}>
              <Button onClick={() => decide(false)} isLoading={loading}>
                拒绝
              </Button>
              <Button appearance="primary" onClick={() => decide(true)} isLoading={loading}>
                允许
              </Button>
            </Inline>
          </Stack>
        )}
      </Box>
    </Box>
  );
}
