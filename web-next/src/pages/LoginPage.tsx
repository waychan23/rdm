import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Stack, Text, xcss } from "@atlaskit/primitives";

import { errorCause } from "../lib/api";
import { submitLogin } from "../lib/auth";
import { useNotify } from "../lib/flags";
import { beginLogin } from "../lib/oauth";

function safeInternalPath(target: string | null): string | null {
  return target && target.startsWith("/") && !target.startsWith("//") ? target : null;
}

const wrapStyles = xcss({
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: "color.background.neutral.subtle",
});

const cardStyles = xcss({
  width: "360px",
  padding: "space.300",
  backgroundColor: "elevation.surface",
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
});

const labelStyles = xcss({
  fontWeight: "font.weight.medium",
  marginBlockEnd: "space.050",
});

export default function LoginPage() {
  const [params] = useSearchParams();
  const notify = useNotify();
  const authKey = params.get("auth_key");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);

  // Direct visits (bookmarks, a 401 bounce) start a fresh authorization
  // request instead of pretending to be a login form without context.
  useEffect(() => {
    if (!authKey) {
      void beginLogin(safeInternalPath(params.get("redirect")) ?? undefined);
    }
  }, [authKey, params]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading || !authKey) return;
    setLoading(true);
    try {
      const result = await submitLogin(authKey, name.trim(), password, remember);
      if (result.must_reset && result.set_password_url) {
        window.location.assign(result.set_password_url);
        return;
      }
      if (result.redirect_to) {
        window.location.assign(result.redirect_to);
        return;
      }
      await beginLogin("/projects");
    } catch (e) {
      notify.error("登录失败", errorCause(e)?.message);
    } finally {
      setLoading(false);
    }
  };

  if (!authKey) {
    return (
      <Box xcss={wrapStyles}>
        <Stack space="space.200" alignInline="center">
          <Spinner size="large" />
          <Text color="color.text.subtlest">正在跳转到登录…</Text>
        </Stack>
      </Box>
    );
  }

  return (
    <Box xcss={wrapStyles}>
      <Box xcss={cardStyles}>
        <Box as="form" onSubmit={submit}>
          <Stack space="space.200">
            <Heading size="large">rd-manager 登录</Heading>
            <Stack space="space.050">
              <Box as="label" xcss={labelStyles} htmlFor="login-name">
                用户名
              </Box>
              <Textfield
                id="login-name"
                value={name}
                placeholder="owner"
                autoComplete="username"
                autoFocus
                onChange={(e) => setName(e.currentTarget.value)}
              />
            </Stack>
            <Stack space="space.050">
              <Box as="label" xcss={labelStyles} htmlFor="login-password">
                密码
              </Box>
              <Textfield
                id="login-password"
                type="password"
                value={password}
                autoComplete="current-password"
                onChange={(e) => setPassword(e.currentTarget.value)}
              />
            </Stack>
            <Checkbox
              label="记住我（7 天内免登录）"
              isChecked={remember}
              onChange={(e) => setRemember(e.currentTarget.checked)}
            />
            <Button type="submit" appearance="primary" isLoading={loading}>
              登录
            </Button>
            <Text size="small" color="color.text.subtlest">
              首次部署请使用服务启动日志中的 bootstrap-url 设置 Org Owner 密码；
              忘记密码可由部署主机执行 rdm account recover-owner 重新生成。
            </Text>
          </Stack>
        </Box>
      </Box>
    </Box>
  );
}
