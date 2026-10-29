import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import { RadioGroup } from "@atlaskit/radio";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import type { OrgUser } from "../types";

interface ConsentInfo {
  client: { client_id: string; client_name: string | null };
  scopes: string[];
  selectable_users: OrgUser[];
}

const wrapStyles = xcss({
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: "elevation.surface.sunken",
  padding: "space.300",
});

const actionsStyles = xcss({ justifyContent: "flex-end" });

const cardStyles = xcss({
  width: "440px",
  maxWidth: "100%",
  padding: "space.300",
  backgroundColor: "elevation.surface",
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
  boxShadow: "elevation.shadow.raised",
});

// Consent is authenticated by the one-shot capability key in the URL (§17);
// it must not use the Bearer-injecting api client.
async function consentFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, init);
  const payload = await res.json();
  if (!res.ok) {
    throw new Error(payload?.error?.message ?? `HTTP ${res.status}`);
  }
  return payload.data as T;
}

export default function ConsentPage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const key = params.get("key") ?? "";
  const [info, setInfo] = useState<ConsentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [userId, setUserId] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const data = await consentFetch<ConsentInfo>(
          `/oauth/consent/${id}?key=${encodeURIComponent(key)}`,
        );
        setInfo(data);
        setUserId(
          data.selectable_users.find((u) => u.type === "human")?.id ??
            data.selectable_users[0]?.id ??
            "",
        );
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [id, key]);

  const decide = async (allow: boolean) => {
    if (loading) return;
    setLoading(true);
    try {
      const body = allow
        ? { decision: "allow", act_as_user_id: userId }
        : { decision: "deny" };
      const result = await consentFetch<{ redirect_to: string }>(
        `/oauth/consent/${id}/decision?key=${encodeURIComponent(key)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      window.location.assign(result.redirect_to);
    } catch (e) {
      setError((e as Error).message);
      setLoading(false);
    }
  };

  return (
    <Box xcss={wrapStyles} testId="page-consent">
      <Box xcss={cardStyles}>
        {error ? (
          <Stack space="space.200" testId="consent-error">
            <Heading size="large" as="h1">授权不可用</Heading>
            <Text>{error}</Text>
            <Text size="small" color="color.text.subtlest">
              授权链接有效期 10 分钟且只能使用一次，请回到终端重新发起登录。
            </Text>
          </Stack>
        ) : !info ? (
          <Inline space="space.150" alignBlock="center" testId="consent-loading">
            <Spinner size="small" />
            <Text color="color.text.subtlest">加载授权请求…</Text>
          </Inline>
        ) : (
          <Stack space="space.200" testId="consent-form">
            <Heading size="large" as="h1">授权访问 rdm</Heading>
            <Text>
              应用 <Text weight="bold">{info.client.client_name || info.client.client_id}</Text>{" "}
              请求访问你的 rdm 工作区（scope: {info.scopes.join(" ")}）。
            </Text>
            {info.selectable_users.length > 0 && (
              <Stack space="space.100">
                <Text size="small" color="color.text.subtlest">
                  以哪个身份授权
                </Text>
                <RadioGroup
                  options={info.selectable_users.map((u) => ({
                    name: "consent-user",
                    value: u.id,
                    label: (
                      <Inline space="space.100" alignBlock="center">
                        <span>{u.name}</span>
                        <Lozenge appearance={u.type === "agent" ? "warning" : "default"}>
                          {u.type}
                        </Lozenge>
                        {u.manager_user_id && (
                          <Text size="small" color="color.text.subtlest">
                            受管于人类账号
                          </Text>
                        )}
                      </Inline>
                    ),
                  }))}
                  value={userId}
                  onChange={(e) => setUserId(e.currentTarget.value)}
                />
              </Stack>
            )}
            <Inline space="space.100" xcss={actionsStyles}>
              <Button testId="consent-deny" onClick={() => decide(false)} isLoading={loading}>
                拒绝
              </Button>
              <Button
                appearance="primary"
                testId="consent-allow"
                onClick={() => decide(true)}
                isLoading={loading}
              >
                允许
              </Button>
            </Inline>
          </Stack>
        )}
      </Box>
    </Box>
  );
}
